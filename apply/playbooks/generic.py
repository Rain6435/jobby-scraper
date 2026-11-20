"""Generic single-page / semi-structured ATS playbook for auth-free boards."""

from __future__ import annotations

from apply.browser.runner import detect_bot_gate
from apply.playbooks.base import AuthGateStatus, BasePlaybook


class GenericSinglePagePlaybook(BasePlaybook):
    board = "generic"

    def detect_auth_gate(self, url: str, html_content: str) -> AuthGateStatus:
        if detect_bot_gate(html_content):
            return "captcha"
        lower = html_content.lower()
        if "sign in to apply" in lower and "password" in lower:
            return "login_required"
        return "authenticated"

    def detect_step(self, url: str, html_content: str) -> str:
        lower = html_content.lower()
        if "thank you" in lower or "application received" in lower:
            return "generic:submitted"
        return "generic:single_page"
