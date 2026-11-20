"""Tier 1 Lever direct schema & submission adapter."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from urllib.parse import urlparse

from apply.models import DistilledElement, DistilledPage, FieldActionPlan, SubmitResult
from apply.submitters.base import BaseSubmitter, plan_to_dict
from scraper.boards.base import make_session

LEVER_POSTING_API = "https://api.lever.co/v0/postings/{company}/{posting_id}"


def parse_lever_url(job_url: str) -> tuple[str, str]:
    """Extract (company_slug, posting_id) from a Lever job posting URL."""
    parsed = urlparse(job_url)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2:
        return parts[0], parts[1]
    raise ValueError(f"Cannot parse Lever company and posting_id from {job_url}")


class LeverSubmitter(BaseSubmitter):
    source = "lever"

    def fetch_form_schema(self, job_url: str) -> DistilledPage:
        company, posting_id = parse_lever_url(job_url)
        session = make_session()
        resp = session.get(
            LEVER_POSTING_API.format(company=company, posting_id=posting_id),
            timeout=25,
        )
        resp.raise_for_status()
        _ = cast(dict[str, object], resp.json())

        elements: list[DistilledElement] = [
            {
                "uid": "name",
                "role": "textbox",
                "label": "Full Name",
                "required": True,
                "current_value": None,
            },
            {
                "uid": "email",
                "role": "textbox",
                "label": "Email",
                "required": True,
                "current_value": None,
            },
            {
                "uid": "phone",
                "role": "textbox",
                "label": "Phone",
                "required": False,
                "current_value": None,
            },
            {
                "uid": "resume",
                "role": "file_input",
                "label": "Resume/CV",
                "required": True,
                "current_value": None,
            },
            {
                "uid": "urls[LinkedIn]",
                "role": "textbox",
                "label": "LinkedIn URL",
                "required": False,
                "current_value": None,
            },
            {
                "uid": "urls[GitHub]",
                "role": "textbox",
                "label": "GitHub URL",
                "required": False,
                "current_value": None,
            },
            {
                "uid": "lever_submit",
                "role": "button",
                "label": "Submit Application",
                "required": False,
                "current_value": None,
            },
        ]
        return {
            "page_url": job_url,
            "detected_step": "lever:single_page",
            "elements": elements,
        }

    def submit(
        self,
        job_url: str,
        distilled: DistilledPage,
        plan: FieldActionPlan,
        *,
        resume_path: Path | None = None,
        dry_run: bool = True,
    ) -> SubmitResult:
        readable = plan_to_dict(distilled, plan)
        if plan["missing_info_questions"]:
            return {
                "ok": False,
                "status": "awaiting_user_qa",
                "message": f"{len(plan['missing_info_questions'])} required question(s) need user input.",
                "filled_payload": readable,
            }
        if dry_run:
            return {
                "ok": True,
                "status": "ready_for_review",
                "message": "Copilot dry-run complete; ready for 1-click approval.",
                "filled_payload": readable,
            }

        company, posting_id = parse_lever_url(job_url)
        session = make_session()
        form_data: dict[str, str] = {}
        files: dict[str, tuple[str, bytes, str]] = {}
        for action in plan["field_actions"]:
            if action["action"] == "upload_file" and resume_path and resume_path.is_file():
                files["resume"] = (resume_path.name, resume_path.read_bytes(), "application/pdf")
            else:
                form_data[action["uid"]] = str(action["value"])

        resp = session.post(
            LEVER_POSTING_API.format(company=company, posting_id=posting_id),
            data=form_data,
            files=files or None,
            timeout=30,
        )
        if resp.status_code in (200, 201):
            return {
                "ok": True,
                "status": "submitted",
                "message": "Submitted via Lever API.",
                "filled_payload": readable,
            }
        return {
            "ok": False,
            "status": "failed",
            "message": f"Lever submission returned HTTP {resp.status_code}: {resp.text[:250]}",
            "filled_payload": readable,
        }
