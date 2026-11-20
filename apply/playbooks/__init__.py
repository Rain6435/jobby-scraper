"""Deterministic ATS playbooks for Tier 2 multi-step portals."""

from apply.playbooks.base import AuthGateStatus, BasePlaybook
from apply.playbooks.generic import GenericSinglePagePlaybook
from apply.playbooks.successfactors import SuccessFactorsPlaybook
from apply.playbooks.workday import WorkdayPlaybook

PLAYBOOKS: dict[str, type[BasePlaybook]] = {
    "workday": WorkdayPlaybook,
    "successfactors": SuccessFactorsPlaybook,
    "bamboohr": GenericSinglePagePlaybook,
    "rippling": GenericSinglePagePlaybook,
    "workable": GenericSinglePagePlaybook,
    "breezy": GenericSinglePagePlaybook,
    "recruitee": GenericSinglePagePlaybook,
    "pinpoint": GenericSinglePagePlaybook,
    "teamtailor": GenericSinglePagePlaybook,
    "smartrecruiters": GenericSinglePagePlaybook,
    "jazzhr": GenericSinglePagePlaybook,
    "personio": GenericSinglePagePlaybook,
}

__all__ = [
    "AuthGateStatus",
    "BasePlaybook",
    "GenericSinglePagePlaybook",
    "PLAYBOOKS",
    "SuccessFactorsPlaybook",
    "WorkdayPlaybook",
]
