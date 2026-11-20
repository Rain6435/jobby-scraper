"""Persistent SQLAlchemy 2.0 store for apply.db (decoupled from jobs.db full-replace)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    func,
    select,
)
from sqlalchemy.engine import Engine

from apply.models import (
    AnswerBankEntry,
    ApplicationRecord,
    ApplicationStatus,
    ApplySettings,
    AuthCredentialRecord,
    AuthScope,
    CandidateProfile,
    CredentialStatus,
    EmailAliasStrategy,
    InboxIntegrationRecord,
    JobSnapshot,
    ProvisionMethod,
    QuestionType,
    UserProfileRecord,
    VerificationProvider,
)

apply_metadata = MetaData()

user_profiles_table = Table(
    "user_profiles",
    apply_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("display_name", String, nullable=False, server_default=""),
    Column("primary_email", String, nullable=False, server_default=""),
    Column("email_alias_strategy", String, nullable=False, server_default="direct"),
    Column("profile_json", Text, nullable=False, server_default="{}"),
    Column("master_resume_path", String, nullable=False, server_default=""),
    Column("settings_json", Text, nullable=False, server_default="{}"),
    Column("updated_at", String, nullable=False),
)

auth_credentials_table = Table(
    "auth_credentials",
    apply_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("user_profiles.id"), nullable=False),
    Column("auth_scope", String, nullable=False),
    Column("domain_key", String, nullable=False),
    Column("board", String, nullable=False),
    Column("email_used", String, nullable=False),
    Column("encrypted_password", Text, nullable=True),
    Column("encrypted_storage_state", Text, nullable=True),
    Column("provision_method", String, nullable=False),
    Column("status", String, nullable=False),
    Column("last_verified_at", String, nullable=False, server_default=""),
    UniqueConstraint("user_id", "domain_key", name="uq_auth_user_domain"),
)

inbox_integrations_table = Table(
    "inbox_integrations",
    apply_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("user_profiles.id"), nullable=False, unique=True),
    Column("provider", String, nullable=False),
    Column("encrypted_config", Text, nullable=True),
    Column("poll_sender_allowlist", Text, nullable=False, server_default="[]"),
)

answer_bank_table = Table(
    "answer_bank",
    apply_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("user_profiles.id"), nullable=False),
    Column("question_text", Text, nullable=False),
    Column("question_type", String, nullable=False),
    Column("answer_value", Text, nullable=False),
    Column("scope", String, nullable=False, server_default="global"),
    Column("times_reused", Integer, nullable=False, server_default="0"),
    Column("last_used_at", String, nullable=False, server_default=""),
)

applications_table = Table(
    "applications",
    apply_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("user_profiles.id"), nullable=False),
    Column("job_id", String, nullable=False, index=True),
    Column("job_snapshot_json", Text, nullable=False),
    Column("match_score", Float, nullable=False, server_default="0.0"),
    Column("tailored_resume_path", String, nullable=False, server_default=""),
    Column("status", String, nullable=False, index=True),
    Column("current_step", String, nullable=False, server_default=""),
    Column("filled_payload_json", Text, nullable=False, server_default="{}"),
    Column("screenshot_paths_json", Text, nullable=False, server_default="[]"),
    Column("error_detail", Text, nullable=False, server_default=""),
    Column("created_at", String, nullable=False),
    Column("submitted_at", String, nullable=False, server_default=""),
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def default_settings() -> ApplySettings:
    return {
        "execution_mode": "copilot",
        "daily_limit": 15,
        "min_match_score": 55.0,
        "auto_create_accounts": True,
        "blocked_companies": [],
        "email_alias_strategy": "direct",
    }


def default_profile() -> CandidateProfile:
    return {
        "full_name": "",
        "first_name": "",
        "last_name": "",
        "email": "",
    }


def create_apply_engine(db_url: str = "sqlite:///data/apply.db") -> Engine:
    engine = create_engine(db_url, future=True)
    apply_metadata.create_all(engine)
    return engine


def get_or_create_default_user(engine: Engine) -> UserProfileRecord:
    with engine.begin() as conn:
        row = conn.execute(select(user_profiles_table).limit(1)).mappings().first()
        if row is not None:
            return _row_to_user_profile(dict(row))
        now = _now_iso()
        res = conn.execute(
            user_profiles_table.insert().values(
                display_name="Default Candidate",
                primary_email="",
                email_alias_strategy="direct",
                profile_json=json.dumps(default_profile()),
                master_resume_path="",
                settings_json=json.dumps(default_settings()),
                updated_at=now,
            )
        )
        assert res.inserted_primary_key is not None
        user_id = int(str(res.inserted_primary_key[0]))
        created = (
            conn.execute(select(user_profiles_table).where(user_profiles_table.c.id == user_id))
            .mappings()
            .one()
        )
        return _row_to_user_profile(dict(created))


def update_user_profile(
    engine: Engine,
    user_id: int,
    *,
    display_name: str | None = None,
    primary_email: str | None = None,
    email_alias_strategy: EmailAliasStrategy | None = None,
    profile: CandidateProfile | None = None,
    master_resume_path: str | None = None,
    settings: ApplySettings | None = None,
) -> UserProfileRecord:
    values: dict[str, object] = {"updated_at": _now_iso()}
    if display_name is not None:
        values["display_name"] = display_name
    if primary_email is not None:
        values["primary_email"] = primary_email
    if email_alias_strategy is not None:
        values["email_alias_strategy"] = email_alias_strategy
    if profile is not None:
        values["profile_json"] = json.dumps(profile)
    if master_resume_path is not None:
        values["master_resume_path"] = master_resume_path
    if settings is not None:
        values["settings_json"] = json.dumps(settings)

    with engine.begin() as conn:
        conn.execute(
            user_profiles_table.update().where(user_profiles_table.c.id == user_id).values(**values)
        )
        row = (
            conn.execute(select(user_profiles_table).where(user_profiles_table.c.id == user_id))
            .mappings()
            .one()
        )
        return _row_to_user_profile(dict(row))


def upsert_auth_credential(
    engine: Engine,
    *,
    user_id: int,
    auth_scope: AuthScope,
    domain_key: str,
    board: str,
    email_used: str,
    encrypted_password: str | None,
    encrypted_storage_state: str | None,
    provision_method: ProvisionMethod,
    status: CredentialStatus,
    last_verified_at: str | None = None,
) -> AuthCredentialRecord:
    verified = last_verified_at if last_verified_at is not None else _now_iso()
    with engine.begin() as conn:
        existing = (
            conn.execute(
                select(auth_credentials_table).where(
                    auth_credentials_table.c.user_id == user_id,
                    auth_credentials_table.c.domain_key == domain_key,
                )
            )
            .mappings()
            .first()
        )
        if existing is None:
            res = conn.execute(
                auth_credentials_table.insert().values(
                    user_id=user_id,
                    auth_scope=auth_scope,
                    domain_key=domain_key,
                    board=board,
                    email_used=email_used,
                    encrypted_password=encrypted_password,
                    encrypted_storage_state=encrypted_storage_state,
                    provision_method=provision_method,
                    status=status,
                    last_verified_at=verified,
                )
            )
            assert res.inserted_primary_key is not None
            cred_id = int(str(res.inserted_primary_key[0]))
        else:
            cred_id = int(existing["id"])
            conn.execute(
                auth_credentials_table.update()
                .where(auth_credentials_table.c.id == cred_id)
                .values(
                    auth_scope=auth_scope,
                    board=board,
                    email_used=email_used,
                    encrypted_password=encrypted_password,
                    encrypted_storage_state=encrypted_storage_state,
                    provision_method=provision_method,
                    status=status,
                    last_verified_at=verified,
                )
            )
        row = (
            conn.execute(
                select(auth_credentials_table).where(auth_credentials_table.c.id == cred_id)
            )
            .mappings()
            .one()
        )
        return _row_to_auth_credential(dict(row))


def get_auth_credential(
    engine: Engine, user_id: int, domain_key: str
) -> AuthCredentialRecord | None:
    with engine.connect() as conn:
        row = (
            conn.execute(
                select(auth_credentials_table).where(
                    auth_credentials_table.c.user_id == user_id,
                    auth_credentials_table.c.domain_key == domain_key,
                )
            )
            .mappings()
            .first()
        )
        return _row_to_auth_credential(dict(row)) if row is not None else None


def list_auth_credentials(engine: Engine, user_id: int) -> list[AuthCredentialRecord]:
    with engine.connect() as conn:
        rows = (
            conn.execute(
                select(auth_credentials_table)
                .where(auth_credentials_table.c.user_id == user_id)
                .order_by(auth_credentials_table.c.domain_key)
            )
            .mappings()
            .all()
        )
        return [_row_to_auth_credential(dict(r)) for r in rows]


def delete_auth_credential(engine: Engine, cred_id: int) -> bool:
    with engine.begin() as conn:
        res = conn.execute(
            delete(auth_credentials_table).where(auth_credentials_table.c.id == cred_id)
        )
        return res.rowcount > 0


def upsert_inbox_integration(
    engine: Engine,
    *,
    user_id: int,
    provider: VerificationProvider,
    encrypted_config: str | None,
    poll_sender_allowlist: list[str] | None = None,
) -> InboxIntegrationRecord:
    allowlist = poll_sender_allowlist or [
        "myworkday.com",
        "successfactors.com",
        "oraclecloud.com",
    ]
    with engine.begin() as conn:
        existing = (
            conn.execute(
                select(inbox_integrations_table).where(
                    inbox_integrations_table.c.user_id == user_id
                )
            )
            .mappings()
            .first()
        )
        if existing is None:
            res = conn.execute(
                inbox_integrations_table.insert().values(
                    user_id=user_id,
                    provider=provider,
                    encrypted_config=encrypted_config,
                    poll_sender_allowlist=json.dumps(allowlist),
                )
            )
            assert res.inserted_primary_key is not None
            row_id = int(str(res.inserted_primary_key[0]))
        else:
            row_id = int(existing["id"])
            conn.execute(
                inbox_integrations_table.update()
                .where(inbox_integrations_table.c.id == row_id)
                .values(
                    provider=provider,
                    encrypted_config=encrypted_config,
                    poll_sender_allowlist=json.dumps(allowlist),
                )
            )
        row = (
            conn.execute(
                select(inbox_integrations_table).where(inbox_integrations_table.c.id == row_id)
            )
            .mappings()
            .one()
        )
        return _row_to_inbox_integration(dict(row))


def get_inbox_integration(engine: Engine, user_id: int) -> InboxIntegrationRecord | None:
    with engine.connect() as conn:
        row = (
            conn.execute(
                select(inbox_integrations_table).where(
                    inbox_integrations_table.c.user_id == user_id
                )
            )
            .mappings()
            .first()
        )
        return _row_to_inbox_integration(dict(row)) if row is not None else None


def save_answer(
    engine: Engine,
    *,
    user_id: int,
    question_text: str,
    question_type: QuestionType,
    answer_value: str,
    scope: str = "global",
) -> AnswerBankEntry:
    now = _now_iso()
    with engine.begin() as conn:
        res = conn.execute(
            answer_bank_table.insert().values(
                user_id=user_id,
                question_text=question_text,
                question_type=question_type,
                answer_value=answer_value,
                scope=scope,
                times_reused=0,
                last_used_at=now,
            )
        )
        assert res.inserted_primary_key is not None
        row_id = int(str(res.inserted_primary_key[0]))
        row = (
            conn.execute(select(answer_bank_table).where(answer_bank_table.c.id == row_id))
            .mappings()
            .one()
        )
        return _row_to_answer_entry(dict(row))


def list_answers(engine: Engine, user_id: int) -> list[AnswerBankEntry]:
    with engine.connect() as conn:
        rows = (
            conn.execute(
                select(answer_bank_table)
                .where(answer_bank_table.c.user_id == user_id)
                .order_by(answer_bank_table.c.times_reused.desc(), answer_bank_table.c.id.desc())
            )
            .mappings()
            .all()
        )
        return [_row_to_answer_entry(dict(r)) for r in rows]


def increment_answer_reuse(engine: Engine, answer_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            answer_bank_table.update()
            .where(answer_bank_table.c.id == answer_id)
            .values(
                times_reused=answer_bank_table.c.times_reused + 1,
                last_used_at=_now_iso(),
            )
        )


def create_application(
    engine: Engine,
    *,
    user_id: int,
    job_snapshot: JobSnapshot,
    match_score: float = 0.0,
    tailored_resume_path: str = "",
    status: ApplicationStatus = "queued",
    current_step: str = "",
    filled_payload: dict[str, str] | None = None,
) -> ApplicationRecord:
    now = _now_iso()
    with engine.begin() as conn:
        res = conn.execute(
            applications_table.insert().values(
                user_id=user_id,
                job_id=job_snapshot["id"],
                job_snapshot_json=json.dumps(job_snapshot),
                match_score=match_score,
                tailored_resume_path=tailored_resume_path,
                status=status,
                current_step=current_step,
                filled_payload_json=json.dumps(filled_payload or {}),
                screenshot_paths_json="[]",
                error_detail="",
                created_at=now,
                submitted_at="",
            )
        )
        assert res.inserted_primary_key is not None
        app_id = int(str(res.inserted_primary_key[0]))
        row = (
            conn.execute(select(applications_table).where(applications_table.c.id == app_id))
            .mappings()
            .one()
        )
        return _row_to_application(dict(row))


def update_application(
    engine: Engine,
    app_id: int,
    *,
    status: ApplicationStatus | None = None,
    match_score: float | None = None,
    current_step: str | None = None,
    filled_payload: dict[str, str] | None = None,
    screenshot_paths: list[str] | None = None,
    error_detail: str | None = None,
    submitted_at: str | None = None,
) -> ApplicationRecord:
    values: dict[str, object] = {}
    if status is not None:
        values["status"] = status
    if match_score is not None:
        values["match_score"] = match_score
    if current_step is not None:
        values["current_step"] = current_step
    if filled_payload is not None:
        values["filled_payload_json"] = json.dumps(filled_payload)
    if screenshot_paths is not None:
        values["screenshot_paths_json"] = json.dumps(screenshot_paths)
    if error_detail is not None:
        values["error_detail"] = error_detail
    if submitted_at is not None:
        values["submitted_at"] = submitted_at

    with engine.begin() as conn:
        if values:
            conn.execute(
                applications_table.update()
                .where(applications_table.c.id == app_id)
                .values(**values)
            )
        row = (
            conn.execute(select(applications_table).where(applications_table.c.id == app_id))
            .mappings()
            .one()
        )
        return _row_to_application(dict(row))


def get_application(engine: Engine, app_id: int) -> ApplicationRecord | None:
    with engine.connect() as conn:
        row = (
            conn.execute(select(applications_table).where(applications_table.c.id == app_id))
            .mappings()
            .first()
        )
        return _row_to_application(dict(row)) if row is not None else None


def list_applications(
    engine: Engine, user_id: int, status: ApplicationStatus | None = None
) -> list[ApplicationRecord]:
    stmt = select(applications_table).where(applications_table.c.user_id == user_id)
    if status is not None:
        stmt = stmt.where(applications_table.c.status == status)
    stmt = stmt.order_by(applications_table.c.id.desc())
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
        return [_row_to_application(dict(r)) for r in rows]


def count_submitted_today(engine: Engine, user_id: int) -> int:
    today_prefix = datetime.now(UTC).date().isoformat()
    with engine.connect() as conn:
        count = conn.execute(
            select(func.count())
            .select_from(applications_table)
            .where(
                applications_table.c.user_id == user_id,
                applications_table.c.status == "submitted",
                applications_table.c.submitted_at.startswith(today_prefix),
            )
        ).scalar_one()
        return int(count)


def load_jobs_from_pool(
    jobs_db_url: str,
    *,
    limit: int = 50,
    company: str | None = None,
    search: str | None = None,
) -> list[JobSnapshot]:
    """Read-only lookup of scraped jobs from jobs.db without touching its tables."""
    from scraper.db import companies_table, jobs_table, sources_table

    pool_engine = create_engine(jobs_db_url, future=True)
    stmt = (
        select(
            jobs_table.c.id,
            companies_table.c.name.label("company"),
            jobs_table.c.title,
            jobs_table.c.url,
            sources_table.c.name.label("source"),
            jobs_table.c.description,
        )
        .select_from(
            jobs_table.join(companies_table, jobs_table.c.company_id == companies_table.c.id).join(
                sources_table, jobs_table.c.source_id == sources_table.c.id
            )
        )
        .limit(limit)
    )
    if company:
        stmt = stmt.where(companies_table.c.name.ilike(f"%{company}%"))
    if search:
        stmt = stmt.where(jobs_table.c.title.ilike(f"%{search}%"))

    with pool_engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
        return [
            {
                "id": str(r["id"]),
                "company": str(r["company"]),
                "title": str(r["title"]),
                "url": str(r["url"]),
                "source": str(r["source"]),
                "description": str(r["description"]),
            }
            for r in rows
        ]


def _row_to_user_profile(row: dict[str, object]) -> UserProfileRecord:
    raw_profile = cast(CandidateProfile, json.loads(str(row["profile_json"])))
    raw_settings = cast(ApplySettings, json.loads(str(row["settings_json"])))
    return UserProfileRecord(
        id=int(str(row["id"])),
        display_name=str(row["display_name"]),
        primary_email=str(row["primary_email"]),
        email_alias_strategy=cast(EmailAliasStrategy, str(row["email_alias_strategy"])),
        profile=raw_profile,
        master_resume_path=str(row["master_resume_path"]),
        settings=raw_settings,
        updated_at=str(row["updated_at"]),
    )


def _row_to_auth_credential(row: dict[str, object]) -> AuthCredentialRecord:
    enc_pw = row["encrypted_password"]
    enc_state = row["encrypted_storage_state"]
    return AuthCredentialRecord(
        id=int(str(row["id"])),
        user_id=int(str(row["user_id"])),
        auth_scope=cast(AuthScope, str(row["auth_scope"])),
        domain_key=str(row["domain_key"]),
        board=str(row["board"]),
        email_used=str(row["email_used"]),
        encrypted_password=str(enc_pw) if enc_pw is not None else None,
        encrypted_storage_state=str(enc_state) if enc_state is not None else None,
        provision_method=cast(ProvisionMethod, str(row["provision_method"])),
        status=cast(CredentialStatus, str(row["status"])),
        last_verified_at=str(row["last_verified_at"]),
    )


def _row_to_inbox_integration(row: dict[str, object]) -> InboxIntegrationRecord:
    enc_cfg = row["encrypted_config"]
    allowlist = cast(list[str], json.loads(str(row["poll_sender_allowlist"])))
    return InboxIntegrationRecord(
        id=int(str(row["id"])),
        user_id=int(str(row["user_id"])),
        provider=cast(VerificationProvider, str(row["provider"])),
        encrypted_config=str(enc_cfg) if enc_cfg is not None else None,
        poll_sender_allowlist=allowlist,
    )


def _row_to_answer_entry(row: dict[str, object]) -> AnswerBankEntry:
    return AnswerBankEntry(
        id=int(str(row["id"])),
        user_id=int(str(row["user_id"])),
        question_text=str(row["question_text"]),
        question_type=cast(QuestionType, str(row["question_type"])),
        answer_value=str(row["answer_value"]),
        scope=str(row["scope"]),
        times_reused=int(str(row["times_reused"])),
        last_used_at=str(row["last_used_at"]),
    )


def _row_to_application(row: dict[str, object]) -> ApplicationRecord:
    return ApplicationRecord(
        id=int(str(row["id"])),
        user_id=int(str(row["user_id"])),
        job_id=str(row["job_id"]),
        job_snapshot=cast(JobSnapshot, json.loads(str(row["job_snapshot_json"]))),
        match_score=float(str(row["match_score"])),
        tailored_resume_path=str(row["tailored_resume_path"]),
        status=cast(ApplicationStatus, str(row["status"])),
        current_step=str(row["current_step"]),
        filled_payload=cast(dict[str, str], json.loads(str(row["filled_payload_json"]))),
        screenshot_paths=cast(list[str], json.loads(str(row["screenshot_paths_json"]))),
        error_detail=str(row["error_detail"]),
        created_at=str(row["created_at"]),
        submitted_at=str(row["submitted_at"]),
    )
