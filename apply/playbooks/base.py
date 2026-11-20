"""Base interface for Tier 2 deterministic ATS playbooks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal
from urllib.parse import urlparse

AuthGateStatus = Literal["authenticated", "login_required", "signup_required", "captcha"]


class BasePlaybook(ABC):
    board: str = "base"

    @staticmethod
    def domain_key(job_url: str) -> str:
        """Extract the tenant/domain key used in auth_credentials."""
        return urlparse(job_url).netloc.lower()

    @abstractmethod
    def detect_auth_gate(self, url: str, html_content: str) -> AuthGateStatus:
        """Determine whether the current page requires login, signup, or CAPTCHA."""
        raise NotImplementedError

    @abstractmethod
    def detect_step(self, url: str, html_content: str) -> str:
        """Identify the current wizard step for deterministic state tracking."""
        raise NotImplementedError
