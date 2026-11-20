"""Strict typed models for the automated job application engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, NotRequired, TypedDict

ExecutionMode = Literal["copilot", "autopilot"]
EmailAliasStrategy = Literal["direct", "plus_address"]
AuthScope = Literal["tenant", "global"]
ProvisionMethod = Literal["user_interactive", "auto_created"]
CredentialStatus = Literal["active", "expired", "needs_verification", "locked"]
VerificationProvider = Literal["imap", "gmail_oauth", "manual_prompt"]
QuestionType = Literal["boolean", "select", "number", "short_text", "long_text"]
ApplicationStatus = Literal[
    "queued",
    "matching",
    "filling",
    "awaiting_auth",
    "awaiting_email_otp",
    "awaiting_user_qa",
    "awaiting_captcha",
    "ready_for_review",
    "submitted",
    "failed",
    "skipped",
]
ElementRole = Literal[
    "textbox",
    "textarea",
    "select",
    "typeahead_select",
    "radio_group",
    "checkbox",
    "file_input",
    "button",
]
ActionType = Literal[
    "fill_text",
    "select_option",
    "select_typeahead",
    "select_radio",
    "toggle_checkbox",
    "upload_file",
    "click",
]


class WorkExperience(TypedDict):
    company: str
    title: str
    start_date: str
    end_date: NotRequired[str]
    location: NotRequired[str]
    highlights: NotRequired[list[str]]


class EducationEntry(TypedDict):
    institution: str
    degree: str
    field_of_study: NotRequired[str]
    graduation_year: NotRequired[str]


class CandidateProfile(TypedDict):
    full_name: str
    first_name: str
    last_name: str
    email: str
    phone: NotRequired[str]
    location: NotRequired[str]
    linkedin_url: NotRequired[str]
    github_url: NotRequired[str]
    portfolio_url: NotRequired[str]
    summary: NotRequired[str]
    skills: NotRequired[list[str]]
    languages: NotRequired[list[str]]
    work_experience: NotRequired[list[WorkExperience]]
    education: NotRequired[list[EducationEntry]]
    work_authorization: NotRequired[dict[str, str]]
    requires_sponsorship: NotRequired[bool]
    salary_expectation: NotRequired[str]
    notice_period: NotRequired[str]
    eeo_defaults: NotRequired[dict[str, str]]


class ApplySettings(TypedDict):
    execution_mode: ExecutionMode
    daily_limit: int
    min_match_score: float
    auto_create_accounts: bool
    blocked_companies: list[str]
    email_alias_strategy: EmailAliasStrategy


class JobSnapshot(TypedDict):
    id: str
    company: str
    title: str
    url: str
    source: str
    location: NotRequired[str]
    description: NotRequired[str]


class MatchResult(TypedDict):
    score: float
    rationale: str
    matched_skills: list[str]
    missing_skills: list[str]
    recommended: bool


class DistilledElement(TypedDict):
    uid: str
    role: ElementRole
    label: str
    required: bool
    current_value: str | bool | None
    widget_hint: NotRequired[str]
    options: NotRequired[list[str]]
    accept: NotRequired[str]


class DistilledPage(TypedDict):
    page_url: str
    detected_step: str
    elements: list[DistilledElement]


class FieldAction(TypedDict):
    uid: str
    action: ActionType
    value: str | bool
    confidence: float
    source: NotRequired[str]


class MissingInfoQuestion(TypedDict):
    uid: str
    question_text: str
    question_type: QuestionType
    options: NotRequired[list[str]]


class NextAction(TypedDict):
    uid: str
    action: ActionType
    is_final_submit: bool


class FieldActionPlan(TypedDict):
    field_actions: list[FieldAction]
    missing_info_questions: list[MissingInfoQuestion]
    next_action: NextAction | None


class SubmitResult(TypedDict):
    ok: bool
    status: ApplicationStatus
    confirmation_id: NotRequired[str]
    message: str
    filled_payload: NotRequired[dict[str, str]]


@dataclass(slots=True)
class UserProfileRecord:
    id: int
    display_name: str
    primary_email: str
    email_alias_strategy: EmailAliasStrategy
    profile: CandidateProfile
    master_resume_path: str
    settings: ApplySettings
    updated_at: str


@dataclass(slots=True)
class AuthCredentialRecord:
    id: int
    user_id: int
    auth_scope: AuthScope
    domain_key: str
    board: str
    email_used: str
    encrypted_password: str | None
    encrypted_storage_state: str | None
    provision_method: ProvisionMethod
    status: CredentialStatus
    last_verified_at: str


@dataclass(slots=True)
class InboxIntegrationRecord:
    id: int
    user_id: int
    provider: VerificationProvider
    encrypted_config: str | None
    poll_sender_allowlist: list[str] = field(default_factory=lambda: [])


@dataclass(slots=True)
class AnswerBankEntry:
    id: int
    user_id: int
    question_text: str
    question_type: QuestionType
    answer_value: str
    scope: str = "global"
    times_reused: int = 0
    last_used_at: str = ""


@dataclass(slots=True)
class ApplicationRecord:
    id: int
    user_id: int
    job_id: str
    job_snapshot: JobSnapshot
    match_score: float
    tailored_resume_path: str
    status: ApplicationStatus
    current_step: str
    filled_payload: dict[str, str]
    screenshot_paths: list[str]
    error_detail: str
    created_at: str
    submitted_at: str
