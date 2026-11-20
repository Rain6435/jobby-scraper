"""Tier 1 direct schema/HTTP ATS submitters."""

from apply.submitters.ashby import AshbySubmitter
from apply.submitters.base import BaseSubmitter
from apply.submitters.greenhouse import GreenhouseSubmitter
from apply.submitters.lever import LeverSubmitter

SUBMITTERS: dict[str, type[BaseSubmitter]] = {
    "greenhouse": GreenhouseSubmitter,
    "ashby": AshbySubmitter,
    "lever": LeverSubmitter,
}

__all__ = [
    "AshbySubmitter",
    "BaseSubmitter",
    "GreenhouseSubmitter",
    "LeverSubmitter",
    "SUBMITTERS",
]
