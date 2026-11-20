"""Tests for Tier 1 submitters, AnswerBank, and ApplicationEngine routing."""

from __future__ import annotations

from pathlib import Path

import responses

from apply.answer_bank import find_best_answer, record_user_answer
from apply.db import create_apply_engine, get_or_create_default_user, update_user_profile
from apply.engine import ApplicationEngine
from apply.models import CandidateProfile
from apply.submitters.greenhouse import GREENHOUSE_JOB_API, parse_greenhouse_url
from apply.vault import Vault


def test_parse_greenhouse_url() -> None:
    token, job_id = parse_greenhouse_url("https://boards.greenhouse.io/stripe/jobs/123456")
    assert token == "stripe"
    assert job_id == "123456"


def test_answer_bank_matching() -> None:
    engine = create_apply_engine("sqlite:///:memory:")
    user = get_or_create_default_user(engine)
    record_user_answer(
        engine,
        user.id,
        question_text="Are you legally authorized to work in Canada?",
        question_type="boolean",
        answer_value="Yes",
    )
    from apply.db import list_answers

    entries = list_answers(engine, user.id)
    hit = find_best_answer(entries, "Are you authorized to work in Canada?")
    assert hit is not None
    assert hit.answer_value == "Yes"


@responses.activate
def test_engine_tier1_greenhouse_copilot_and_approve(tmp_path: Path) -> None:
    responses.add(
        responses.GET,
        GREENHOUSE_JOB_API.format(token="acme", job_id="999"),
        json={
            "id": 999,
            "title": "Backend Engineer",
            "questions": [
                {
                    "label": "First Name",
                    "required": True,
                    "fields": [{"name": "first_name", "type": "input_text"}],
                },
                {
                    "label": "Email",
                    "required": True,
                    "fields": [{"name": "email", "type": "input_text"}],
                },
            ],
        },
        status=200,
    )

    engine = create_apply_engine("sqlite:///:memory:")
    user = get_or_create_default_user(engine)
    profile: CandidateProfile = {
        "full_name": "Alex Rivera",
        "first_name": "Alex",
        "last_name": "Rivera",
        "email": "alex@example.com",
        "skills": ["python", "fastapi"],
    }
    update_user_profile(
        engine,
        user.id,
        display_name="Alex Rivera",
        primary_email="alex@example.com",
        profile=profile,
    )

    app_engine = ApplicationEngine(engine, vault=Vault(key_file=tmp_path / "k.key"))
    rec = app_engine.prepare_application(
        {
            "id": "acme:999",
            "company": "Acme",
            "title": "Backend Engineer",
            "url": "https://boards.greenhouse.io/acme/jobs/999",
            "source": "greenhouse",
            "description": "Looking for Python and FastAPI experience.",
        }
    )
    assert rec.status == "ready_for_review"
    assert rec.filled_payload["First Name"] == "Alex"
    assert rec.filled_payload["Email"] == "alex@example.com"

    submitted = app_engine.approve_and_submit(rec.id)
    assert submitted.status == "submitted"
    assert submitted.submitted_at != ""


def test_engine_tier2_workday_auto_create_and_otp(tmp_path: Path) -> None:
    engine = create_apply_engine("sqlite:///:memory:")
    user = get_or_create_default_user(engine)
    update_user_profile(
        engine,
        user.id,
        display_name="Alex Rivera",
        primary_email="alex@gmail.com",
        email_alias_strategy="plus_address",
        profile={
            "full_name": "Alex Rivera",
            "first_name": "Alex",
            "last_name": "Rivera",
            "email": "alex@gmail.com",
            "skills": ["python"],
        },
    )

    app_engine = ApplicationEngine(engine, vault=Vault(key_file=tmp_path / "k.key"))
    rec = app_engine.prepare_application(
        {
            "id": "cae:R42",
            "company": "CAE",
            "title": "Systems Engineer",
            "url": "https://cae.wd3.myworkdayjobs.com/en-US/career/job/R42",
            "source": "workday",
            "description": "Python systems engineering.",
        }
    )
    assert rec.status == "awaiting_email_otp"
    assert rec.filled_payload["email_used"] == "alex+cae@gmail.com"

    resumed = app_engine.submit_otp_or_answer(rec.id, otp_code="123456")
    assert resumed.status == "ready_for_review"


@responses.activate
def test_ashby_submit_post() -> None:
    from apply.submitters.ashby import AshbySubmitter

    responses.add(
        responses.POST,
        "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiSubmitApplication",
        json={"data": {"applicationFormSubmit": {"success": True}}},
        status=200,
    )
    sub = AshbySubmitter()
    res = sub.submit(
        "https://jobs.ashbyhq.com/linear/abc-123",
        {
            "page_url": "https://jobs.ashbyhq.com/linear/abc-123",
            "detected_step": "ashby:single_page",
            "elements": [
                {
                    "uid": "_systemfield_name",
                    "role": "textbox",
                    "label": "Full Name",
                    "required": True,
                    "current_value": None,
                }
            ],
        },
        {
            "field_actions": [
                {
                    "uid": "_systemfield_name",
                    "action": "fill_text",
                    "value": "Alex Rivera",
                    "confidence": 0.99,
                }
            ],
            "missing_info_questions": [],
            "next_action": None,
        },
        dry_run=False,
    )
    assert res["ok"] is True
    assert res["status"] == "submitted"


def test_generic_playbook_registry() -> None:
    from apply.playbooks import PLAYBOOKS

    for board in ("bamboohr", "rippling", "workable", "smartrecruiters"):
        assert board in PLAYBOOKS
        pb = PLAYBOOKS[board]()
        assert pb.detect_auth_gate("https://example.com", "<html>Apply</html>") == "authenticated"
        assert (
            pb.detect_step("https://example.com", "<html>Thank you</html>") == "generic:submitted"
        )
