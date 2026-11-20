"""Base class for Tier 1 direct schema/HTTP application submitters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from apply.models import DistilledPage, FieldActionPlan, SubmitResult


class BaseSubmitter(ABC):
    source: str = "base"

    @abstractmethod
    def fetch_form_schema(self, job_url: str) -> DistilledPage:
        """Fetch and normalize the ATS application form into a DistilledPage."""
        raise NotImplementedError

    @abstractmethod
    def submit(
        self,
        job_url: str,
        distilled: DistilledPage,
        plan: FieldActionPlan,
        *,
        resume_path: Path | None = None,
        dry_run: bool = True,
    ) -> SubmitResult:
        """Execute (or dry-run) the form submission using the planned field actions."""
        raise NotImplementedError


def plan_to_dict(distilled: DistilledPage, plan: FieldActionPlan) -> dict[str, str]:
    """Convert a FieldActionPlan into a human-readable {label: value} dictionary."""
    by_uid = {el["uid"]: el["label"] for el in distilled["elements"]}
    out: dict[str, str] = {}
    for action in plan["field_actions"]:
        label = by_uid.get(action["uid"], action["uid"])
        out[label] = str(action["value"])
    return out
