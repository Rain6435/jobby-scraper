"""Main ApplicationEngine orchestrator: match, route, auth check, plan, and submit."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from sqlalchemy.engine import Engine

from apply.answer_bank import match_page_questions, record_user_answer
from apply.browser.runner import run_playwright_wizard
from apply.db import (
    count_submitted_today,
    create_application,
    get_application,
    get_auth_credential,
    get_inbox_integration,
    get_or_create_default_user,
    update_application,
    upsert_auth_credential,
)
from apply.email_bridge import poll_imap_for_verification
from apply.llm import plan_form_actions, score_job_match
from apply.models import ApplicationRecord, JobSnapshot, QuestionType
from apply.playbooks import PLAYBOOKS
from apply.profile import resolve_application_email
from apply.submitters import SUBMITTERS
from apply.vault import Vault, generate_strong_password
from scraper.boards.base import slugify


class ApplicationEngine:
    """Coordinates Tier 1 API, Tier 2 Playbook, and Tier 3 HITL application flows."""

    def __init__(self, engine: Engine, vault: Vault | None = None) -> None:
        self.engine = engine
        self.vault = vault or Vault()

    def prepare_application(self, job: JobSnapshot) -> ApplicationRecord:
        """Run match gate, route by board tier, and prepare or pause an application."""
        user = get_or_create_default_user(self.engine)
        settings = user.settings
        company_slug = slugify(job["company"])

        if job["company"] in settings["blocked_companies"]:
            app = create_application(
                self.engine,
                user_id=user.id,
                job_snapshot=job,
                status="skipped",
                current_step="blocked_company",
            )
            return update_application(
                self.engine, app.id, error_detail="Company is in user blocklist."
            )

        if count_submitted_today(self.engine, user.id) >= settings["daily_limit"]:
            app = create_application(
                self.engine,
                user_id=user.id,
                job_snapshot=job,
                status="skipped",
                current_step="daily_limit_reached",
            )
            return update_application(
                self.engine, app.id, error_detail="Daily application limit reached."
            )

        match = score_job_match(
            user.profile,
            job["title"],
            job.get("description", ""),
            min_threshold=settings["min_match_score"],
        )
        app = create_application(
            self.engine,
            user_id=user.id,
            job_snapshot=job,
            match_score=match["score"],
            tailored_resume_path=user.master_resume_path,
            status="matching" if match["recommended"] else "skipped",
            current_step="match_gate",
        )
        if not match["recommended"]:
            return update_application(
                self.engine,
                app.id,
                error_detail=f"Match score {match['score']:.1f} below threshold {settings['min_match_score']:.1f}.",
            )

        board = job["source"].lower()
        if board in SUBMITTERS:
            return self._run_tier1(
                app.id,
                user.id,
                board,
                job,
                company_slug,
                user.master_resume_path,
                settings["execution_mode"] == "copilot",
            )

        if board in PLAYBOOKS:
            return self._prepare_tier2_auth(
                app.id,
                user.id,
                board,
                job,
                company_slug,
                user.primary_email,
                user.email_alias_strategy,
                settings["auto_create_accounts"],
            )

        return update_application(
            self.engine,
            app.id,
            status="awaiting_auth",
            current_step=f"tier3:{board}:handoff",
            error_detail="Custom portal requires interactive browser handoff.",
        )

    def _run_tier1(
        self,
        app_id: int,
        user_id: int,
        board: str,
        job: JobSnapshot,
        company_slug: str,
        resume_path: str,
        copilot_mode: bool,
    ) -> ApplicationRecord:
        user = get_or_create_default_user(self.engine)
        submitter = SUBMITTERS[board]()
        distilled = submitter.fetch_form_schema(job["url"])
        qa_hits = match_page_questions(self.engine, user_id, distilled, company_slug=company_slug)
        plan = plan_form_actions(
            distilled,
            user.profile,
            qa_hits,
            resume_path=resume_path,
            job_context=f"{job['title']} at {job['company']}\n{job.get('description', '')[:1200]}",
        )
        res_path = Path(resume_path) if resume_path else None
        result = submitter.submit(
            job["url"],
            distilled,
            plan,
            resume_path=res_path,
            dry_run=copilot_mode,
        )
        submitted_at = datetime.now(UTC).isoformat() if result["status"] == "submitted" else ""
        return update_application(
            self.engine,
            app_id,
            status=result["status"],
            current_step=distilled["detected_step"],
            filled_payload=result.get("filled_payload") or {},
            error_detail="" if result["ok"] else result["message"],
            submitted_at=submitted_at,
        )

    def _prepare_tier2_auth(
        self,
        app_id: int,
        user_id: int,
        board: str,
        job: JobSnapshot,
        company_slug: str,
        primary_email: str,
        alias_strategy: str,
        auto_create: bool,
    ) -> ApplicationRecord:
        playbook = PLAYBOOKS[board]()
        domain_key = playbook.domain_key(job["url"])
        cred = get_auth_credential(self.engine, user_id, domain_key)

        if cred is not None and cred.status == "active" and cred.encrypted_storage_state:
            user = get_or_create_default_user(self.engine)
            wiz = run_playwright_wizard(
                job_url=job["url"],
                app_id=app_id,
                playbook=playbook,
                qa_matcher=lambda d: match_page_questions(
                    self.engine, user_id, d, company_slug=company_slug
                ),
                planner=lambda d, hits: plan_form_actions(
                    d,
                    user.profile,
                    hits,
                    resume_path=user.master_resume_path,
                    job_context=f"{job['title']} at {job['company']}\n{job.get('description', '')[:1200]}",
                ),
                vault=self.vault,
                encrypted_storage_state=cred.encrypted_storage_state,
                copilot_mode=user.settings["execution_mode"] == "copilot",
            )
            submitted_at = datetime.now(UTC).isoformat() if wiz["status"] == "submitted" else ""
            return update_application(
                self.engine,
                app_id,
                status=wiz["status"],
                current_step=wiz["current_step"],
                filled_payload=wiz["filled_payload"],
                screenshot_paths=wiz["screenshot_paths"],
                error_detail=wiz["error_detail"],
                submitted_at=submitted_at,
            )

        if auto_create and primary_email:
            app_email = resolve_application_email(
                primary_email,
                "plus_address" if alias_strategy == "plus_address" else "direct",
                company_slug,
            )
            enc_pw = self.vault.encrypt(generate_strong_password())
            upsert_auth_credential(
                self.engine,
                user_id=user_id,
                auth_scope="tenant",
                domain_key=domain_key,
                board=board,
                email_used=app_email,
                encrypted_password=enc_pw,
                encrypted_storage_state=None,
                provision_method="auto_created",
                status="needs_verification",
            )
            inbox = get_inbox_integration(self.engine, user_id)
            if inbox is not None and inbox.provider == "imap" and inbox.encrypted_config:
                try:
                    cfg = cast(
                        dict[str, str], json.loads(self.vault.decrypt(inbox.encrypted_config))
                    )
                    hit = poll_imap_for_verification(
                        host=cfg.get("host", ""),
                        username=cfg.get("username", ""),
                        password=cfg.get("password", ""),
                        port=int(cfg.get("port", "993")),
                        sender_allowlist=inbox.poll_sender_allowlist,
                    )
                    if hit is not None and (hit["otp_code"] or hit["verification_url"]):
                        upsert_auth_credential(
                            self.engine,
                            user_id=user_id,
                            auth_scope="tenant",
                            domain_key=domain_key,
                            board=board,
                            email_used=app_email,
                            encrypted_password=enc_pw,
                            encrypted_storage_state=None,
                            provision_method="auto_created",
                            status="active",
                        )
                        return update_application(
                            self.engine,
                            app_id,
                            status="ready_for_review",
                            current_step=f"{board}:imap_verified",
                            filled_payload={
                                "auth_domain": domain_key,
                                "email_used": app_email,
                                "otp_verified": hit["otp_code"] or "link",
                            },
                            error_detail="",
                        )
                except Exception:
                    pass
            return update_application(
                self.engine,
                app_id,
                status="awaiting_email_otp",
                current_step=f"{board}:verify_signup_email",
                filled_payload={"auth_domain": domain_key, "email_used": app_email},
                error_detail=f"Account provisioned for {app_email}; enter verification OTP sent by {domain_key}.",
            )

        return update_application(
            self.engine,
            app_id,
            status="awaiting_auth",
            current_step=f"{board}:login_required",
            filled_payload={"auth_domain": domain_key},
            error_detail=f"Sign in to {domain_key} via Interactive Live Browser.",
        )

    def approve_and_submit(self, app_id: int) -> ApplicationRecord:
        """Approve a Copilot-paused application and mark/execute final submission."""
        app = update_application(
            self.engine,
            app_id,
            status="submitted",
            current_step="copilot_approved",
            submitted_at=datetime.now(UTC).isoformat(),
            error_detail="",
        )
        return app

    def submit_otp_or_answer(
        self,
        app_id: int,
        *,
        otp_code: str = "",
        question_text: str = "",
        question_type: QuestionType = "short_text",
        answer_value: str = "",
    ) -> ApplicationRecord:
        """Resume a paused application with a user-supplied OTP or Q&A answer."""
        user = get_or_create_default_user(self.engine)
        if otp_code:
            existing_app = get_application(self.engine, app_id)
            if existing_app is not None:
                domain_key = existing_app.filled_payload.get("auth_domain", "")
                if domain_key:
                    cred = get_auth_credential(self.engine, user.id, domain_key)
                    if cred is not None:
                        upsert_auth_credential(
                            self.engine,
                            user_id=user.id,
                            auth_scope=cred.auth_scope,
                            domain_key=cred.domain_key,
                            board=cred.board,
                            email_used=cred.email_used,
                            encrypted_password=cred.encrypted_password,
                            encrypted_storage_state=cred.encrypted_storage_state,
                            provision_method=cred.provision_method,
                            status="active",
                        )
            return update_application(
                self.engine,
                app_id,
                status="ready_for_review",
                current_step="otp_verified",
                error_detail="",
            )
        if question_text and answer_value:
            record_user_answer(
                self.engine,
                user.id,
                question_text=question_text,
                question_type=question_type,
                answer_value=answer_value,
            )
            return update_application(
                self.engine,
                app_id,
                status="ready_for_review",
                current_step="qa_answered",
                error_detail="",
            )
        return update_application(self.engine, app_id, error_detail="No OTP or answer provided.")
