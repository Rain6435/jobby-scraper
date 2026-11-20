"""Deterministic state machine playbook for Workday (myworkdayjobs.com)."""

from __future__ import annotations

from apply.browser.runner import detect_bot_gate
from apply.playbooks.base import AuthGateStatus, BasePlaybook

WORKDAY_STEPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("workday:my_information", ("my information", "legal name", "how did you hear")),
    ("workday:my_experience", ("my experience", "work experience", "add another")),
    ("workday:application_questions", ("application questions", "voluntary")),
    ("workday:voluntary_disclosures", ("voluntary disclosures", "gender", "veteran")),
    ("workday:self_identify", ("self identify", "disability")),
    ("workday:review", ("review", "submit application")),
)


class WorkdayPlaybook(BasePlaybook):
    board = "workday"

    def detect_auth_gate(self, url: str, html_content: str) -> AuthGateStatus:
        if detect_bot_gate(html_content):
            return "captcha"
        lower = html_content.lower()
        if "create account" in lower and (
            "email address" in lower or "verify new password" in lower
        ):
            return "signup_required"
        if "sign in" in lower and ("password" in lower or "/login" in url.lower()):
            return "login_required"
        return "authenticated"

    def detect_step(self, url: str, html_content: str) -> str:
        lower = html_content.lower()
        for step_name, markers in WORKDAY_STEPS:
            if any(m in lower for m in markers):
                return step_name
        if "apply" in url.lower():
            return "workday:apply_entry"
        return "workday:unknown"
