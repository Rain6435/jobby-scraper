"""Ollama Cloud API key rotation — standalone port for this repo.

OLLAMA_API_KEY may hold several comma-separated keys instead of one — set
this way specifically to survive Ollama Cloud's free-tier hourly usage limit
("you've reached your hourly usage limit, please wait or upgrade to
continue", distinct from the transient "too many concurrent requests" 429
already handled by scraper/summarize.py's ordinary retry-with-backoff).
Ollama's own docs describe this as a session limit on a ~5-hour clock, not
literally every 60 minutes — see EXHAUSTION_COOLDOWN_SECONDS below.

This is a standalone port of job_pipeline/utils/ollama_keys.py (this repo's
CLAUDE.md is explicit that JobScraper must run independently — its own
GitHub Actions cron, its own config/requirements, no import of the parent
pipeline's code), but both write the SAME state file when this repo is
checked out nested inside the parent pipeline (the normal case here — see
main.py's --run-jobscraper), so a key one process learns is exhausted is
respected by the other immediately. Falls back to a local file when run via
this repo's own standalone GitHub Actions workflow instead (no parent
pipeline present) — rotation still works, just isn't cross-process-shared,
which is fine since there's no "other process" to share with in that setup.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path

log = logging.getLogger("scraper.ollama_keys")

EXHAUSTION_COOLDOWN_SECONDS = 5 * 60 * 60

# Three distinct observed wordings for the same quota-exhaustion condition,
# each replacing the last as Ollama's own error text changed over time —
# "hourly usage limit" per Ollama's docs, a live 429 body observed
# 2026-08-14 read "you (schedulopro) have reached your session usage limit,
# upgrade for higher limits", and one observed 2026-08-22 read "you
# (schedulopro) have reached your weekly usage limit, upgrade for higher
# limits". All three must be checked, or a genuinely exhausted key is never
# recognized as such and rotation never moves past it — kept in sync with
# the parent pipeline's own copy at job_pipeline/utils/ollama_keys.py (see
# this file's module docstring for why both copies exist). If Ollama
# changes this text again, add the new marker rather than replacing one —
# nothing indicates old wordings stop appearing once a new one starts.
HOURLY_LIMIT_MARKER = "hourly usage limit"
SESSION_LIMIT_MARKER = "session usage limit"
WEEKLY_LIMIT_MARKER = "weekly usage limit"
CONCURRENCY_MARKER = "too many concurrent requests"

ROOT = Path(__file__).resolve().parent.parent


def _default_state_path() -> Path:
    """../data/ (the parent pipeline's shared data dir) if it exists — this
    repo is normally checked out nested inside it — else a local fallback
    so this repo still works run fully standalone."""
    parent_data_dir = ROOT.parent / "data"
    if parent_data_dir.is_dir():
        return parent_data_dir / "ollama_key_rotation.json"
    return ROOT / ".ollama_key_rotation.json"


def _state_path() -> Path:
    override = os.environ.get("OLLAMA_KEY_ROTATION_STATE_FILE")
    return Path(override) if override else _default_state_path()


def _key_id(key: str) -> str:
    """Short, non-reversible identifier for a key — never store the raw secret."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def parse_keys(raw: str) -> list[str]:
    """OLLAMA_API_KEY, comma-separated, trimmed, empties dropped. A single
    key with no commas returns a one-element list — same rotation code path
    whether there's 1 key or several."""
    return [k.strip() for k in raw.split(",") if k.strip()]


def _load_state() -> dict[str, float]:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: float(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (json.JSONDecodeError, ValueError, OSError):
        log.warning("Corrupt Ollama key rotation state at %s — treating as empty", path)
        return {}


def _save_state(state: dict[str, float]) -> None:
    path = _state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        log.warning("Failed to persist Ollama key rotation state to %s", path)


def is_hourly_limit_error(status_code: int, body_text: str) -> bool:
    """True for the hourly/session/weekly-quota 429 specifically — not the
    momentary concurrency 429, which should keep using ordinary
    retry-with-backoff on the SAME key rather than burning through the
    rotation."""
    text = (body_text or "").lower()
    return status_code == 429 and (
        HOURLY_LIMIT_MARKER in text
        or SESSION_LIMIT_MARKER in text
        or WEEKLY_LIMIT_MARKER in text
    )


def is_concurrency_error(status_code: int, body_text: str) -> bool:
    return status_code == 429 and CONCURRENCY_MARKER in (body_text or "").lower()


def usable_keys(keys: list[str], now: float | None = None) -> list[str]:
    """`keys` filtered to those not currently marked exhausted, in the same
    order — so callers rotate deterministically starting from key #1 each
    time, skipping only what's actually known-bad right now."""
    now = now if now is not None else time.time()
    state = _load_state()
    return [k for k in keys if state.get(_key_id(k), 0.0) <= now]


def mark_exhausted(key: str, now: float | None = None) -> None:
    """Record that `key` hit the hourly limit — skipped by usable_keys()
    until the cooldown window passes."""
    now = now if now is not None else time.time()
    state = _load_state()
    state[_key_id(key)] = now + EXHAUSTION_COOLDOWN_SECONDS
    _save_state(state)
    log.warning(
        "Ollama key %s hit its hourly limit — cooling down for %.0fh",
        _key_id(key), EXHAUSTION_COOLDOWN_SECONDS / 3600,
    )
