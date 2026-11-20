"""FastAPI application for jobby-scraper's Automated Application Engine UI."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import cast

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from apply.db import (
    create_apply_engine,
    delete_auth_credential,
    get_inbox_integration,
    get_or_create_default_user,
    list_answers,
    list_applications,
    list_auth_credentials,
    load_jobs_from_pool,
    update_user_profile,
    upsert_inbox_integration,
)
from apply.engine import ApplicationEngine
from apply.models import (
    ApplySettings,
    CandidateProfile,
    EmailAliasStrategy,
    ExecutionMode,
    JobSnapshot,
    QuestionType,
    VerificationProvider,
)
from apply.profile import onboard_resume
from apply.vault import Vault
from web.screencast import run_cdp_screencast_session

STATIC_DIR = Path(__file__).resolve().parent / "static"
DATA_DIR = Path("data") if Path("data").is_dir() else Path(".apply_data")
UPLOAD_DIR = DATA_DIR / "resumes"
SCREENSHOT_DIR = DATA_DIR / "screenshots"


class ProfileUpdateBody(BaseModel):
    display_name: str
    primary_email: str
    email_alias_strategy: EmailAliasStrategy
    profile: dict[str, object]


class SettingsUpdateBody(BaseModel):
    execution_mode: ExecutionMode
    daily_limit: int
    min_match_score: float
    auto_create_accounts: bool
    blocked_companies: list[str]
    email_alias_strategy: EmailAliasStrategy
    primary_email: str = ""
    verification_provider: VerificationProvider = "manual_prompt"
    imap_host: str = ""
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""


class PrepareApplicationBody(BaseModel):
    id: str
    company: str
    title: str
    url: str
    source: str
    description: str = ""


class AnswerOrOtpBody(BaseModel):
    otp_code: str = ""
    question_text: str = ""
    question_type: QuestionType = "short_text"
    answer_value: str = ""


def create_app(
    *,
    apply_db_url: str | None = None,
    jobs_db_url: str | None = None,
) -> FastAPI:
    default_apply_db = f"sqlite:///{DATA_DIR / 'apply.db'}"
    resolved_apply_db = apply_db_url or os.environ.get("APPLY_DB_URL", default_apply_db)
    resolved_jobs_db = jobs_db_url or os.environ.get("JOBS_DB_URL", "sqlite:///jobs.db")

    if resolved_apply_db.startswith("sqlite:///") and not resolved_apply_db.endswith(":memory:"):
        db_file = Path(resolved_apply_db.removeprefix("sqlite:///"))
        if not db_file.parent.is_dir():
            db_file.parent.mkdir(parents=True, exist_ok=True)

    engine = create_apply_engine(resolved_apply_db)
    vault = Vault()
    app_engine = ApplicationEngine(engine, vault=vault)

    app = FastAPI(title="jobby-scraper Apply Engine", version="0.1.0")
    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/screenshots/{filename}")
    def get_screenshot(filename: str) -> FileResponse:
        safe_name = Path(filename).name
        target = SCREENSHOT_DIR / safe_name
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Screenshot not found")
        return FileResponse(target, media_type="image/png")

    @app.get("/api/profile")
    def get_profile() -> dict[str, object]:
        user = get_or_create_default_user(engine)
        inbox = get_inbox_integration(engine, user.id)
        return {
            "id": user.id,
            "display_name": user.display_name,
            "primary_email": user.primary_email,
            "email_alias_strategy": user.email_alias_strategy,
            "profile": user.profile,
            "master_resume_path": user.master_resume_path,
            "settings": user.settings,
            "verification_provider": inbox.provider if inbox else "manual_prompt",
            "has_imap_config": bool(inbox and inbox.encrypted_config),
        }

    @app.put("/api/profile")
    def put_profile(body: ProfileUpdateBody) -> dict[str, object]:
        user = get_or_create_default_user(engine)
        updated = update_user_profile(
            engine,
            user.id,
            display_name=body.display_name,
            primary_email=body.primary_email,
            email_alias_strategy=body.email_alias_strategy,
            profile=cast(CandidateProfile, body.profile),
        )
        return asdict(updated)

    @app.post("/api/profile/resume")
    async def upload_resume(file: UploadFile = File(...)) -> dict[str, object]:
        user = get_or_create_default_user(engine)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        filename = Path(file.filename or "resume.pdf").name
        dest = UPLOAD_DIR / filename
        dest.write_bytes(await file.read())
        parsed = onboard_resume(dest)
        updated = update_user_profile(
            engine,
            user.id,
            display_name=parsed.get("full_name") or user.display_name,
            primary_email=user.primary_email or parsed.get("email", ""),
            profile=parsed,
            master_resume_path=str(dest),
        )
        return {"profile": updated.profile, "master_resume_path": updated.master_resume_path}

    @app.put("/api/settings")
    def put_settings(body: SettingsUpdateBody) -> dict[str, object]:
        user = get_or_create_default_user(engine)
        new_settings: ApplySettings = {
            "execution_mode": body.execution_mode,
            "daily_limit": body.daily_limit,
            "min_match_score": body.min_match_score,
            "auto_create_accounts": body.auto_create_accounts,
            "blocked_companies": body.blocked_companies,
            "email_alias_strategy": body.email_alias_strategy,
        }
        updated = update_user_profile(
            engine,
            user.id,
            primary_email=body.primary_email or user.primary_email,
            email_alias_strategy=body.email_alias_strategy,
            settings=new_settings,
        )
        enc_imap: str | None = None
        if body.verification_provider == "imap" and body.imap_host and body.imap_username:
            enc_imap = vault.encrypt(
                json.dumps(
                    {
                        "host": body.imap_host,
                        "port": str(body.imap_port),
                        "username": body.imap_username,
                        "password": body.imap_password,
                    }
                )
            )
        upsert_inbox_integration(
            engine,
            user_id=user.id,
            provider=body.verification_provider,
            encrypted_config=enc_imap,
        )
        return {
            "settings": updated.settings,
            "primary_email": updated.primary_email,
            "has_imap_config": enc_imap is not None,
        }

    @app.get("/api/credentials")
    def get_credentials() -> list[dict[str, object]]:
        user = get_or_create_default_user(engine)
        creds = list_auth_credentials(engine, user.id)
        return [
            {
                "id": c.id,
                "auth_scope": c.auth_scope,
                "domain_key": c.domain_key,
                "board": c.board,
                "email_used": c.email_used,
                "provision_method": c.provision_method,
                "status": c.status,
                "has_session": bool(c.encrypted_storage_state),
                "last_verified_at": c.last_verified_at,
            }
            for c in creds
        ]

    @app.delete("/api/credentials/{cred_id}")
    def remove_credential(cred_id: int) -> dict[str, bool]:
        ok = delete_auth_credential(engine, cred_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Credential not found")
        return {"deleted": True}

    @app.get("/api/jobs")
    def get_jobs(
        limit: int = Query(default=40, le=200),
        company: str = Query(default=""),
        search: str = Query(default=""),
    ) -> list[JobSnapshot]:
        try:
            return load_jobs_from_pool(
                resolved_jobs_db,
                limit=limit,
                company=company or None,
                search=search or None,
            )
        except Exception:
            return []

    @app.get("/api/applications")
    def get_applications() -> list[dict[str, object]]:
        user = get_or_create_default_user(engine)
        return [asdict(a) for a in list_applications(engine, user.id)]

    @app.post("/api/applications/prepare")
    def prepare_application(body: PrepareApplicationBody) -> dict[str, object]:
        snap: JobSnapshot = {
            "id": body.id,
            "company": body.company,
            "title": body.title,
            "url": body.url,
            "source": body.source,
            "description": body.description,
        }
        rec = app_engine.prepare_application(snap)
        return asdict(rec)

    @app.post("/api/applications/{app_id}/approve")
    def approve_application(app_id: int) -> dict[str, object]:
        rec = app_engine.approve_and_submit(app_id)
        return asdict(rec)

    @app.post("/api/applications/{app_id}/answer")
    def answer_application(app_id: int, body: AnswerOrOtpBody) -> dict[str, object]:
        rec = app_engine.submit_otp_or_answer(
            app_id,
            otp_code=body.otp_code,
            question_text=body.question_text,
            question_type=body.question_type,
            answer_value=body.answer_value,
        )
        return asdict(rec)

    @app.get("/api/answers")
    def get_answers() -> list[dict[str, object]]:
        user = get_or_create_default_user(engine)
        return [asdict(a) for a in list_answers(engine, user.id)]

    @app.websocket("/ws/browser/{domain_key}")
    async def ws_browser(
        websocket: WebSocket,
        domain_key: str,
        url: str = Query(...),
        board: str = Query(default="workday"),
    ) -> None:
        await run_cdp_screencast_session(
            websocket,
            target_url=url,
            domain_key=domain_key,
            board=board,
            engine=engine,
            vault=vault,
        )

    return app


app = create_app()
