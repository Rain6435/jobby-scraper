"""Tier 1 Ashby direct schema & submission adapter."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from urllib.parse import urlparse

from apply.models import DistilledElement, DistilledPage, ElementRole, FieldActionPlan, SubmitResult
from apply.submitters.base import BaseSubmitter, plan_to_dict
from scraper.boards.base import make_session

ASHBY_INFO_API = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def parse_ashby_url(job_url: str) -> tuple[str, str]:
    """Extract (board_slug, posting_id) from an Ashby job posting URL."""
    parsed = urlparse(job_url)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2:
        return parts[0], parts[1]
    raise ValueError(f"Cannot parse Ashby slug and posting_id from {job_url}")


class AshbySubmitter(BaseSubmitter):
    source = "ashby"

    def fetch_form_schema(self, job_url: str) -> DistilledPage:
        slug, posting_id = parse_ashby_url(job_url)
        session = make_session()
        resp = session.get(ASHBY_INFO_API.format(slug=slug), timeout=25)
        resp.raise_for_status()
        data = cast(dict[str, object], resp.json())
        jobs = cast(list[dict[str, object]], data.get("jobs") or [])

        target_job: dict[str, object] | None = None
        for j in jobs:
            if str(j.get("id") or "") == posting_id or posting_id in str(j.get("jobUrl") or ""):
                target_job = j
                break

        elements: list[DistilledElement] = []
        if target_job and isinstance(target_job.get("applicationForm"), dict):
            form = cast(dict[str, object], target_job["applicationForm"])
            sections = cast(list[dict[str, object]], form.get("sections") or [])
            for sec in sections:
                fields = cast(list[dict[str, object]], sec.get("fields") or [])
                for f in fields:
                    field_obj = cast(dict[str, object], f.get("field") or {})
                    path = str(field_obj.get("path") or field_obj.get("id") or "")
                    title = str(field_obj.get("title") or path)
                    ftype = str(field_obj.get("type") or "String")
                    required = bool(f.get("isRequired", False))
                    role: ElementRole = "textbox"
                    if ftype == "File":
                        role = "file_input"
                    elif ftype == "LongText":
                        role = "textarea"
                    elif ftype in ("ValueSelect", "MultiValueSelect"):
                        role = "select"
                    elif ftype == "Boolean":
                        role = "radio_group"
                    elements.append(
                        {
                            "uid": path or title,
                            "role": role,
                            "label": title,
                            "required": required,
                            "current_value": None,
                        }
                    )

        if not elements:
            elements = [
                {
                    "uid": "_systemfield_name",
                    "role": "textbox",
                    "label": "Full Name",
                    "required": True,
                    "current_value": None,
                },
                {
                    "uid": "_systemfield_email",
                    "role": "textbox",
                    "label": "Email",
                    "required": True,
                    "current_value": None,
                },
                {
                    "uid": "_systemfield_resume",
                    "role": "file_input",
                    "label": "Resume",
                    "required": True,
                    "current_value": None,
                },
            ]

        elements.append(
            {
                "uid": "ashby_submit",
                "role": "button",
                "label": "Submit Application",
                "required": False,
                "current_value": None,
            }
        )
        return {
            "page_url": job_url,
            "detected_step": "ashby:single_page",
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

        _, posting_id = parse_ashby_url(job_url)
        session = make_session()
        field_submissions: list[dict[str, object]] = [
            {"path": action["uid"], "value": action["value"]}
            for action in plan["field_actions"]
            if action["action"] != "upload_file"
        ]
        payload = {
            "operationName": "ApiSubmitApplication",
            "variables": {
                "jobPostingId": posting_id,
                "applicationForm": {"fieldSubmissions": field_submissions},
            },
        }
        files: dict[str, tuple[str, bytes, str]] = {}
        if resume_path and resume_path.is_file():
            files["resume"] = (resume_path.name, resume_path.read_bytes(), "application/pdf")

        resp = session.post(
            "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiSubmitApplication",
            json=payload if not files else None,
            data={"operations": str(payload)} if files else None,
            files=files or None,
            timeout=30,
        )
        if resp.status_code in (200, 201):
            return {
                "ok": True,
                "status": "submitted",
                "message": "Submitted via Ashby API.",
                "filled_payload": readable,
            }
        return {
            "ok": False,
            "status": "failed",
            "message": f"Ashby submission returned HTTP {resp.status_code}: {resp.text[:250]}",
            "filled_payload": readable,
        }
