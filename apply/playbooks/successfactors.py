"""Deterministic state machine playbook for SAP SuccessFactors."""

from __future__ import annotations

from apply.browser.runner import detect_bot_gate
from apply.playbooks.base import AuthGateStatus, BasePlaybook


class SuccessFactorsPlaybook(BasePlaybook):
    board = "successfactors"

    def detect_auth_gate(self, url: str, html_content: str) -> AuthGateStatus:
        if detect_bot_gate(html_content):
            return "captcha"
        lower = html_content.lower()
        if "create an account" in lower or "register" in lower and "password" in lower:
            return "signup_required"
        if ("sign in" in lower or "log in" in lower) and "password" in lower:
            return "login_required"
        return "authenticated"

    def detect_step(self, url: str, html_content: str) -> str:
        lower = html_content.lower()
        if "profile" in lower or "resume" in lower:
            return "successfactors:profile_and_resume"
        if "questionnaire" in lower or "prescreening" in lower:
            return "successfactors:questions"
        if "review" in lower and "submit" in lower:
            return "successfactors:review"
        return "successfactors:apply_entry"
