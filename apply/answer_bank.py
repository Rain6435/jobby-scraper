"""Self-learning Q&A answer bank matching and persistence."""

from __future__ import annotations

import re

from sqlalchemy.engine import Engine

from apply.db import increment_answer_reuse, list_answers, save_answer
from apply.models import AnswerBankEntry, DistilledPage, QuestionType


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 1}


def find_best_answer(
    entries: list[AnswerBankEntry],
    question_text: str,
    *,
    company_slug: str = "",
    min_jaccard: float = 0.55,
) -> AnswerBankEntry | None:
    """Find the best matching AnswerBankEntry by exact or token Jaccard similarity."""
    norm_q = question_text.strip().lower()
    if not norm_q:
        return None

    company_scope = f"company:{company_slug}" if company_slug else ""
    scoped = [
        e for e in entries if e.scope == "global" or (company_scope and e.scope == company_scope)
    ]

    for entry in scoped:
        if entry.question_text.strip().lower() == norm_q:
            return entry

    q_tokens = _tokenize(norm_q)
    if not q_tokens:
        return None

    best_entry: AnswerBankEntry | None = None
    best_score = 0.0
    for entry in scoped:
        e_tokens = _tokenize(entry.question_text)
        if not e_tokens:
            continue
        inter = len(q_tokens & e_tokens)
        union = len(q_tokens | e_tokens)
        score = inter / union if union else 0.0
        if entry.scope == company_scope:
            score += 0.05
        if score >= min_jaccard and score > best_score:
            best_score = score
            best_entry = entry
    return best_entry


def match_page_questions(
    engine: Engine,
    user_id: int,
    distilled: DistilledPage,
    *,
    company_slug: str = "",
) -> dict[str, AnswerBankEntry]:
    """Match distilled page elements against stored AnswerBankEntry records."""
    entries = list_answers(engine, user_id)
    hits: dict[str, AnswerBankEntry] = {}
    for el in distilled["elements"]:
        if el["role"] in ("button", "file_input"):
            continue
        match = find_best_answer(entries, el["label"], company_slug=company_slug)
        if match is not None:
            hits[el["uid"]] = match
            increment_answer_reuse(engine, match.id)
    return hits


def record_user_answer(
    engine: Engine,
    user_id: int,
    question_text: str,
    question_type: QuestionType,
    answer_value: str,
    *,
    scope: str = "global",
) -> AnswerBankEntry:
    """Persist a user-provided Q&A answer for automatic reuse in future applications."""
    return save_answer(
        engine,
        user_id=user_id,
        question_text=question_text,
        question_type=question_type,
        answer_value=answer_value,
        scope=scope,
    )
