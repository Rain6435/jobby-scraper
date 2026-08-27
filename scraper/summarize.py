"""AI-generated role summaries and company blurbs.

Tries the Anthropic API first (ANTHROPIC_API_KEY, or ANTHROPIC_AUTH_TOKEN e.g.
a Claude Code OAuth token — ANTHROPIC_API_KEY takes precedence if both are
set). If neither is configured, or the Anthropic call fails, falls back to
Ollama Cloud (OLLAMA_API_KEY, model gemma4:31b — a free-tier, non-reasoning
model chosen for this low-stakes task instead of a paid/reasoning model).

OLLAMA_API_KEY may hold several comma-separated keys, rotated automatically
when one hits Ollama Cloud's free-tier hourly usage limit — see
scraper/ollama_keys.py for the rotation state protocol (shared with the
parent pipeline's job_pipeline/utils/ollama_keys.py when this repo is
checked out nested inside it, which is the normal case here).

Both providers are best-effort: any failure (missing credentials, network
error, API error, empty response) logs a warning and moves on to the next
fallback (or returns "" if none are left) rather than raising — the scrape
pipeline must never fail because of the AI layer, matching main.py's
philosophy for board-scrape failures.

Set LLM_PROVIDER=anthropic or LLM_PROVIDER=ollama (or pass main.py's
--llm-provider) to pin to a single provider — the other is never attempted,
so a "success" is unambiguously from the one you asked for and a failure
returns "" instead of silently falling back. Unset/"auto" (the default) keeps
the try-Anthropic-then-Ollama fallback behavior described above.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Literal, NotRequired, TypedDict

import anthropic
import requests

from scraper import ollama_keys

log = logging.getLogger("scraper.summarize")

PROVIDERS = ("anthropic", "ollama")

ANTHROPIC_MODEL = "claude-haiku-4-5"
ANTHROPIC_MAX_TOKENS = 200  # short outputs only; plenty of headroom for 1-2 sentences
ANTHROPIC_TIMEOUT = 30

# gemma4:31b is a non-reasoning model on Ollama Cloud's free tier (unlike
# nemotron-3-nano:30b/gpt-oss, which emit a "thinking" block even for short
# prompts — unnecessary latency/tokens for a 1-2 sentence summary). Most other
# catalog models (qwen3.5, kimi-k*, glm-5.*, deepseek-v4-pro, mistral-large-3,
# minimax-*) 403 on the free tier ("requires a subscription").
OLLAMA_MODEL = "gemma4:31b"
OLLAMA_ENDPOINT = "https://ollama.com/api/chat"
OLLAMA_TIMEOUT = 60
# Free tier is concurrency-limited (x-ratelimit-max-concurrent: 2, queue
# limit 5, confirmed via live probing), not a simple requests/min counter —
# irrelevant here since summaries are generated one job at a time in a
# sequential loop (main.py), never concurrently. One retry (on the SAME
# key) is still cheap insurance against a transient 429 from other tenants
# sharing the service — distinct from the hourly-limit 429, which rotates
# to the next key instead (see ollama_keys.is_hourly_limit_error below).
OLLAMA_MAX_RETRIES = 1

class OllamaMessage(TypedDict):
    role: str
    content: str


class OllamaChatResponse(TypedDict):
    message: NotRequired[OllamaMessage]


_anthropic_client: anthropic.Anthropic | Literal[False] | None = None  # lazily constructed; False if unavailable/unset


def _get_anthropic_client() -> anthropic.Anthropic | None:
    """Returns an Anthropic client, or None if no credentials are configured.

    Cached at module level so repeated calls in one run don't reconstruct it.
    Absence of both ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN is a normal,
    expected state — not an error — so this returns None quietly rather than
    raising.
    """
    global _anthropic_client
    if _anthropic_client is not None:
        return _anthropic_client or None
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN")
    if api_key:
        log.debug("Using ANTHROPIC_API_KEY for AI summaries")
        _anthropic_client = anthropic.Anthropic(api_key=api_key)
    elif auth_token:
        log.debug("Using ANTHROPIC_AUTH_TOKEN for AI summaries")
        _anthropic_client = anthropic.Anthropic(auth_token=auth_token)
    else:
        log.debug("No ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN set")
        _anthropic_client = False
        return None
    return _anthropic_client


def _call_anthropic(prompt: str, label: str) -> str:
    """Returns the completion text, or "" if unavailable/failed."""
    client = _get_anthropic_client()
    if client is None:
        return ""
    log.debug("Requesting %s via Anthropic (model=%s)", label, ANTHROPIC_MODEL)
    try:
        resp = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=ANTHROPIC_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
            timeout=ANTHROPIC_TIMEOUT,
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        log.debug("%s succeeded via Anthropic (%d chars)", label, len(text))
        return text.strip()
    except Exception:
        log.warning("%s failed via Anthropic", label)
        return ""


def _call_ollama(prompt: str, label: str) -> str:
    """Returns the completion text, or "" if unavailable/failed.

    OLLAMA_API_KEY may hold several comma-separated keys. Each usable one
    (not currently marked exhausted in the shared rotation state — see
    scraper/ollama_keys.py) is tried in order: an hourly-limit 429 marks
    that key exhausted and immediately moves to the next one (no wait,
    unlike the transient-429 retry below); any other failure — including
    every key being exhausted — stops and returns "" rather than trying
    further, matching this module's best-effort contract.
    """
    keys = ollama_keys.parse_keys(os.environ.get("OLLAMA_API_KEY", ""))
    if not keys:
        log.debug("No OLLAMA_API_KEY set")
        return ""
    endpoint = os.environ.get("OLLAMA_API_ENDPOINT", "https://ollama.com").rstrip("/") + "/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }

    usable = ollama_keys.usable_keys(keys)
    if not usable:
        log.warning(
            "%s: all %d OLLAMA_API_KEY entries are exhausted (hourly limit)",
            label, len(keys),
        )
        return ""

    for api_key in usable:
        headers = {"Authorization": f"Bearer {api_key}"}
        log.debug("Requesting %s via Ollama (model=%s)", label, OLLAMA_MODEL)
        for attempt in range(OLLAMA_MAX_RETRIES + 1):
            try:
                resp = requests.post(endpoint, json=payload, headers=headers, timeout=OLLAMA_TIMEOUT)
                if resp.status_code == 429 and ollama_keys.is_hourly_limit_error(
                    resp.status_code, resp.text
                ):
                    ollama_keys.mark_exhausted(api_key)
                    log.debug("%s: Ollama key exhausted (hourly limit), rotating", label)
                    break  # inner retry loop — move to the next key
                if resp.status_code == 429 and attempt < OLLAMA_MAX_RETRIES:
                    wait = float(resp.headers.get("Retry-After", 2))
                    log.debug("%s: Ollama rate-limited, retrying in %.0fs", label, wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                chat_resp: OllamaChatResponse = resp.json()
                text = chat_resp.get("message", {}).get("content", "")
                log.debug("%s succeeded via Ollama (%d chars)", label, len(text))
                return text.strip()
            except Exception:
                log.warning("%s failed via Ollama", label)
                return ""
    log.warning("%s: exhausted every usable OLLAMA_API_KEY this call", label)
    return ""


def _forced_provider() -> str | None:
    """LLM_PROVIDER env var, validated. None (or "auto") means the normal
    try-Anthropic-then-Ollama fallback; any other value is a config error
    caught here rather than silently ignored."""
    value = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if not value or value == "auto":
        return None
    if value not in PROVIDERS:
        log.warning("Ignoring unrecognized LLM_PROVIDER=%r (expected one of %s or unset)",
                    value, ", ".join(PROVIDERS))
        return None
    return value


def _complete(prompt: str, label: str) -> str:
    """Anthropic first, falling back to Ollama if unavailable or it failed —
    unless LLM_PROVIDER pins to one, in which case only that one is tried."""
    forced = _forced_provider()
    if forced == "anthropic":
        return _call_anthropic(prompt, label)
    if forced == "ollama":
        return _call_ollama(prompt, label)
    text = _call_anthropic(prompt, label)
    if text:
        return text
    return _call_ollama(prompt, label)


def summarize_role(title: str, company: str, description: str) -> str:
    """1-2 sentence summary of what this specific role involves.

    Returns "" if no provider is configured, the description is empty, or
    every configured provider's call fails.
    """
    if not description:
        log.debug("Skipping role summary for %s @ %s: empty description", title, company)
        return ""
    prompt = (
        f"Job title: {title}\nCompany: {company}\n\n"
        f"Posting text:\n{description}\n\n"
        "Write a 1-2 sentence summary of what this role actually "
        "involves day to day. Be concrete and specific to this "
        "posting, not generic. No preamble, just the summary. "
        "Write the summary in the same language as the posting "
        "text above (e.g. French posting -> French summary)."
    )
    return _complete(prompt, f"Role summary for {title} @ {company}")


def summarize_company(company_name: str, careers_url: str = "") -> str:
    """1-2 sentence blurb about what the company does, for the "one blurb per
    company" cache in config.json. Called only by backfill_blurbs.py / the
    new-company-onboarding path, never per-job.

    Returns "" if no provider is configured or every configured provider's
    call fails.
    """
    prompt = (
        f"Company name: {company_name}\n"
        + (f"Careers page: {careers_url}\n" if careers_url else "")
        + "\nWrite a 1-2 sentence blurb describing what this company "
        "does, for a job seeker skimming listings. If you are not "
        "confident what this company does, give your best concise "
        "guess based on the name — do not say you don't know."
    )
    return _complete(prompt, f"Company blurb for {company_name}")
