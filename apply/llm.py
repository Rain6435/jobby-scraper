"""Structured LLM router for resume parsing, job matching, and form planning.

Follows scraper/summarize.py's provider pattern (Anthropic primary, Ollama Cloud
fallback with scraper/ollama_keys.py rotation), with deterministic heuristic
fallbacks when no API keys are configured.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import cast

import anthropic
import requests

from apply.models import (
    ActionType,
    AnswerBankEntry,
    CandidateProfile,
    DistilledElement,
    DistilledPage,
    FieldAction,
    FieldActionPlan,
    MatchResult,
    MissingInfoQuestion,
    NextAction,
    QuestionType,
)
from scraper import ollama_keys
from scraper.summarize import ANTHROPIC_MODEL, OLLAMA_ENDPOINT, OLLAMA_MODEL

log = logging.getLogger("apply.llm")


def _complete_json(prompt: str, max_tokens: int = 1500) -> str:
    """Call Anthropic or Ollama Cloud and return raw completion text (or '')."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN")
    if api_key or auth_token:
        try:
            client = (
                anthropic.Anthropic(api_key=api_key)
                if api_key
                else anthropic.Anthropic(auth_token=auth_token)
            )
            resp = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                timeout=45,
            )
            text = next((b.text for b in resp.content if b.type == "text"), "")
            if text.strip():
                return text.strip()
        except Exception as exc:
            log.warning("Anthropic call failed, falling back to Ollama: %s", exc)

    keys = ollama_keys.parse_keys(os.environ.get("OLLAMA_API_KEY", ""))
    if not keys:
        return ""

    for key in ollama_keys.usable_keys(keys):
        try:
            resp_http = requests.post(
                OLLAMA_ENDPOINT,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
                timeout=60,
            )
            if ollama_keys.is_hourly_limit_error(resp_http.status_code, resp_http.text):
                ollama_keys.mark_exhausted(key)
                continue
            resp_http.raise_for_status()
            payload = cast(dict[str, object], resp_http.json())
            msg = cast(dict[str, object], payload.get("message") or {})
            content = str(msg.get("content") or "").strip()
            if content:
                return content
        except Exception as exc:
            log.warning("Ollama call failed: %s", exc)
    return ""


def _extract_json_block(raw: str) -> dict[str, object] | None:
    if not raw:
        return None
    cleaned = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end > start:
            cleaned = cleaned[start : end + 1]
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return cast(dict[str, object], parsed) if isinstance(parsed, dict) else None


def extract_profile_from_resume(resume_text: str) -> CandidateProfile:
    """Parse resume text into a structured CandidateProfile via LLM or regex fallback."""
    prompt = (
        "Extract a structured JSON CandidateProfile from this resume text. "
        "Return ONLY valid JSON with keys: full_name, first_name, last_name, email, "
        "phone, location, linkedin_url, github_url, portfolio_url, summary, skills (list), "
        "languages (list), work_experience (list of {company, title, start_date, end_date, highlights}), "
        "education (list of {institution, degree, field_of_study, graduation_year}).\n\n"
        f"RESUME:\n{resume_text[:12000]}"
    )
    raw = _complete_json(prompt, max_tokens=2000)
    parsed = _extract_json_block(raw)
    if parsed and parsed.get("full_name"):
        return cast(CandidateProfile, parsed)

    return _heuristic_profile_from_text(resume_text)


def _heuristic_profile_from_text(text: str) -> CandidateProfile:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    full_name = lines[0] if lines else ""
    parts = full_name.split()
    first_name = parts[0] if parts else ""
    last_name = parts[-1] if len(parts) > 1 else ""

    email_m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    phone_m = re.search(r"(\+?\d[\d\s\-().]{7,}\d)", text)
    linkedin_m = re.search(r"https?://(?:www\.)?linkedin\.com/in/[A-Za-z0-9_-]+", text)
    github_m = re.search(r"https?://(?:www\.)?github\.com/[A-Za-z0-9_-]+", text)

    profile: CandidateProfile = {
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "email": email_m.group(0) if email_m else "",
    }
    if phone_m:
        profile["phone"] = phone_m.group(1).strip()
    if linkedin_m:
        profile["linkedin_url"] = linkedin_m.group(0)
    if github_m:
        profile["github_url"] = github_m.group(0)
    return profile


def score_job_match(
    profile: CandidateProfile,
    job_title: str,
    job_description: str,
    min_threshold: float = 55.0,
) -> MatchResult:
    """Compute a 0-100 match score between candidate profile and job description."""
    skills = [s.lower() for s in profile.get("skills", [])]
    desc_lower = f"{job_title}\n{job_description}".lower()
    if not job_description.strip():
        return {
            "score": 65.0,
            "rationale": "No job description available; defaulting to neutral match.",
            "matched_skills": [],
            "missing_skills": [],
            "recommended": 65.0 >= min_threshold,
        }

    prompt = (
        "Score how well this candidate matches the job from 0 to 100. "
        'Return ONLY JSON: {"score": number, "rationale": string, '
        '"matched_skills": [string], "missing_skills": [string]}.\n\n'
        f"CANDIDATE: {json.dumps(profile)[:4000]}\n\n"
        f"JOB TITLE: {job_title}\nDESCRIPTION:\n{job_description[:6000]}"
    )
    raw = _complete_json(prompt, max_tokens=500)
    parsed = _extract_json_block(raw)
    if parsed and isinstance(parsed.get("score"), (int, float)):
        score = float(cast(int | float, parsed["score"]))
        return {
            "score": max(0.0, min(100.0, score)),
            "rationale": str(parsed.get("rationale", "")),
            "matched_skills": [
                str(x) for x in cast(list[object], parsed.get("matched_skills") or [])
            ],
            "missing_skills": [
                str(x) for x in cast(list[object], parsed.get("missing_skills") or [])
            ],
            "recommended": score >= min_threshold,
        }

    matched = [s for s in skills if s in desc_lower]
    base = 60.0 if not skills else min(95.0, 40.0 + (len(matched) / max(len(skills), 1)) * 60.0)
    return {
        "score": round(base, 1),
        "rationale": f"Keyword overlap matched {len(matched)} profile skills.",
        "matched_skills": matched,
        "missing_skills": [],
        "recommended": base >= min_threshold,
    }


def plan_form_actions(
    distilled: DistilledPage,
    profile: CandidateProfile,
    qa_hits: dict[str, AnswerBankEntry],
    *,
    resume_path: str = "",
    job_context: str = "",
) -> FieldActionPlan:
    """Map distilled page elements to profile values, answer bank hits, or LLM answers."""
    actions: list[FieldAction] = []
    missing: list[MissingInfoQuestion] = []
    unresolved: list[DistilledElement] = []
    submit_btn: NextAction | None = None

    for el in distilled["elements"]:
        uid = el["uid"]
        role = el["role"]
        label = el["label"].strip()
        label_l = label.lower()

        if role == "button":
            is_submit = any(w in label_l for w in ("submit", "send application", "apply now"))
            if is_submit or any(w in label_l for w in ("continue", "next", "save")):
                submit_btn = {"uid": uid, "action": "click", "is_final_submit": is_submit}
            continue

        if role == "file_input":
            if resume_path and any(w in label_l for w in ("resume", "cv", "curriculum")):
                actions.append(
                    {
                        "uid": uid,
                        "action": "upload_file",
                        "value": resume_path,
                        "confidence": 1.0,
                        "source": "profile.master_resume_path",
                    }
                )
            continue

        mapped = _deterministic_profile_lookup(label_l, profile)
        if mapped is not None:
            val, src = mapped
            action_name = _action_for_role(role)
            actions.append(
                {
                    "uid": uid,
                    "action": action_name,
                    "value": val,
                    "confidence": 0.98,
                    "source": src,
                }
            )
            continue

        if uid in qa_hits:
            entry = qa_hits[uid]
            actions.append(
                {
                    "uid": uid,
                    "action": _action_for_role(role),
                    "value": entry.answer_value,
                    "confidence": 0.92,
                    "source": f"answer_bank:{entry.id}",
                }
            )
            continue

        unresolved.append(el)

    if unresolved:
        llm_actions, llm_missing = _resolve_with_llm(unresolved, profile, job_context)
        actions.extend(llm_actions)
        missing.extend(llm_missing)

    return {
        "field_actions": actions,
        "missing_info_questions": missing,
        "next_action": submit_btn,
    }


def _action_for_role(role: str) -> ActionType:
    if role == "select":
        return "select_option"
    if role == "typeahead_select":
        return "select_typeahead"
    if role == "radio_group":
        return "select_radio"
    if role == "checkbox":
        return "toggle_checkbox"
    return "fill_text"


def _deterministic_profile_lookup(
    label_l: str, profile: CandidateProfile
) -> tuple[str | bool, str] | None:
    if "first name" in label_l and profile.get("first_name"):
        return profile["first_name"], "profile.first_name"
    if "last name" in label_l and profile.get("last_name"):
        return profile["last_name"], "profile.last_name"
    if ("full name" in label_l or label_l == "name") and profile.get("full_name"):
        return profile["full_name"], "profile.full_name"
    if "email" in label_l and profile.get("email"):
        return profile["email"], "profile.email"
    if "phone" in label_l and profile.get("phone"):
        return profile.get("phone", ""), "profile.phone"
    if "linkedin" in label_l and profile.get("linkedin_url"):
        return profile.get("linkedin_url", ""), "profile.linkedin_url"
    if "github" in label_l and profile.get("github_url"):
        return profile.get("github_url", ""), "profile.github_url"
    if ("portfolio" in label_l or "website" in label_l) and profile.get("portfolio_url"):
        return profile.get("portfolio_url", ""), "profile.portfolio_url"
    if "location" in label_l or "city" in label_l:
        loc = profile.get("location", "")
        if loc:
            return loc, "profile.location"
    if "sponsor" in label_l and "requires_sponsorship" in profile:
        req = profile.get("requires_sponsorship", False)
        return ("Yes" if req else "No"), "profile.requires_sponsorship"
    return None


def _resolve_with_llm(
    unresolved: list[DistilledElement],
    profile: CandidateProfile,
    job_context: str,
) -> tuple[list[FieldAction], list[MissingInfoQuestion]]:
    prompt = (
        "Map these job application form fields using the candidate profile. "
        "If you cannot answer a required field with >=0.75 confidence without inventing facts, "
        "put it in missing_info_questions instead of field_actions. "
        'Return ONLY JSON: {"field_actions": [{"uid": str, "action": str, "value": str|bool, '
        '"confidence": float}], "missing_info_questions": [{"uid": str, "question_text": str, '
        '"question_type": "boolean"|"select"|"number"|"short_text"|"long_text"}]}.\n\n'
        f"PROFILE: {json.dumps(profile)[:4000]}\n"
        f"JOB: {job_context[:1500]}\n"
        f"FIELDS: {json.dumps(unresolved)}"
    )
    raw = _complete_json(prompt, max_tokens=1200)
    parsed = _extract_json_block(raw)
    if parsed:
        raw_actions = cast(list[FieldAction], parsed.get("field_actions") or [])
        raw_missing = cast(list[MissingInfoQuestion], parsed.get("missing_info_questions") or [])
        return raw_actions, raw_missing

    missing: list[MissingInfoQuestion] = []
    for el in unresolved:
        if el["required"]:
            qtype: QuestionType = "short_text"
            if el["role"] == "radio_group":
                qtype = "boolean"
            elif el["role"] in ("select", "typeahead_select"):
                qtype = "select"
            elif el["role"] == "textarea":
                qtype = "long_text"
            q: MissingInfoQuestion = {
                "uid": el["uid"],
                "question_text": el["label"],
                "question_type": qtype,
            }
            if "options" in el:
                q["options"] = el["options"]
            missing.append(q)
    return [], missing
