"""Diffing helper: which jobs are new since the previous run."""

from __future__ import annotations

import logging

from scraper.models import Job

log = logging.getLogger("scraper.storage")


def diff(previous: dict[str, Job], current: list[Job]) -> list[Job]:
    """Jobs present now but absent from the previous snapshot."""
    new_jobs = [job for job in current if job.id not in previous]
    log.debug(
        "Diff: %d current, %d previous, %d new",
        len(current),
        len(previous),
        len(new_jobs),
    )
    return new_jobs
