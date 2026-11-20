"""Tier 1 Greenhouse direct schema & submission adapter."""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

from apply.models import DistilledElement, DistilledPage, ElementRole, FieldActionPlan, SubmitResult
from apply.submitters.base import BaseSubmitter, plan_to_dict
from scraper.boards.base import make_session

GREENHOUSE_JOB_API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{job_id}"


def parse_greenhouse_url(job_url: str) -> tuple[str, str]:
    """Extract (board_token, job_id) from a Greenhouse job posting URL."""
    parsed = urlparse(job_url)
    parts = [p for p in parsed.path.split("/") if p]
    # Typical: https://boards.greenhouse.io/<token>/jobs/<id>
    # Or: https://job-boards.greenhouse.io/<token>/jobs/<id>
    if "jobs" in parts:
        idx = parts.index("jobs")
        if idx >= 1 and idx + 1 < len(parts):
            return parts[idx - 1], parts[idx + 1]
    m = re.search(r"gh_jid=(\d+)", parsed.query)
    if m and parts:
        return parts[0], m.group(1)
    raise ValueError(f"Cannot parse Greenhouse board token and job_id from {job_url}")


class GreenhouseSubmitter(BaseSubmitter):
    source = "greenhouse"

    def fetch_form_schema(self, job_url: str) -> DistilledPage:
        token, job_id = parse_greenhouse_url(job_url)
        session = make_session()
        resp = session.get(
            GREENHOUSE_JOB_API.format(token=token, job_id=job_id),
            params={"questions": "true"},
            timeout=25,
        )
        resp.raise_for_status()
        data = cast(dict[str, object], resp.json())
        raw_questions = cast(list[dict[str, object]], data.get("questions") or [])

        elements: list[DistilledElement] = []
        for idx, q in enumerate(raw_questions, start=1):
            label = str(q.get("label") or f"Question {idx}")
            required = bool(q.get("required", False))
            fields = cast(list[dict[str, object]], q.get("fields") or [])
            if not fields:
                continue
            first_field = fields[0]
            field_name = str(first_field.get("name") or f"q_{idx}")
            ftype = str(first_field.get("type") or "input_text")
            role: ElementRole = "textbox"
            if ftype == "input_file":
                role = "file_input"
            elif ftype == "textarea":
                role = "textarea"
            elif ftype in ("multi_value_single_select", "multi_value_multi_select"):
                role = "select"

            raw_vals = cast(list[dict[str, object]], first_field.get("values") or [])
            options = [str(v.get("label") or v.get("value") or "") for v in raw_vals if v]

            el: DistilledElement = {
                "uid": field_name,
                "role": role,
                "label": label,
                "required": required,
                "current_value": None,
            }
            if options:
                el["options"] = options
            elements.append(el)

        elements.append(
            {
                "uid": "gh_submit",
                "role": "button",
                "label": "Submit Application",
                "required": False,
                "current_value": None,
            }
        )
        return {
            "page_url": job_url,
            "detected_step": "greenhouse:single_page",
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

        token, job_id = parse_greenhouse_url(job_url)
        session = make_session()
        form_data: dict[str, str] = {}
        files: dict[str, tuple[str, bytes, str]] = {}
        for action in plan["field_actions"]:
            if action["action"] == "upload_file" and resume_path and resume_path.is_file():
                files[action["uid"]] = (
                    resume_path.name,
                    resume_path.read_bytes(),
                    "application/pdf",
                )
            else:
                form_data[action["uid"]] = str(action["value"])

        resp = session.post(
            GREENHOUSE_JOB_API.format(token=token, job_id=job_id),
            data=form_data,
            files=files or None,
            timeout=30,
        )
        if resp.status_code in (200, 201):
            return {
                "ok": True,
                "status": "submitted",
                "message": "Submitted via Greenhouse API.",
                "filled_payload": readable,
            }
        return {
            "ok": False,
            "status": "failed",
            "message": f"Greenhouse submission returned HTTP {resp.status_code}: {resp.text[:250]}",
            "filled_payload": readable,
        }
