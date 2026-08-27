"""Snapshot storage and diffing against docs/jobs.json."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import NotRequired, TypedDict

from scraper.models import Job, JobDict

log = logging.getLogger("scraper.storage")


class SnapshotJobDict(JobDict):
    is_new: bool


class SnapshotFile(TypedDict):
    updated_at: NotRequired[str]
    jobs: NotRequired[list[JobDict]]


def load_snapshot(path: Path) -> dict[str, Job]:
    """Load the previous snapshot as {job_id: Job}.

    Missing, empty, or corrupt file = first run (notifications suppressed)
    rather than crashing the pipeline. utf-8-sig tolerates a BOM from
    Windows editors.
    """
    if not path.exists():
        log.info("No snapshot at %s — treating as first run", path)
        return {}
    try:
        data: SnapshotFile = json.loads(path.read_text(encoding="utf-8-sig"))
        jobs = {j["id"]: Job.from_dict(j) for j in data.get("jobs", [])}
        log.debug("Loaded snapshot %s: %d jobs, updated_at=%s", path, len(jobs), data.get("updated_at"))
        return jobs
    except (json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError):
        log.warning("Snapshot %s is corrupt — treating as first run", path)
        return {}


def diff(previous: dict[str, Job], current: list[Job]) -> list[Job]:
    """Jobs present now but absent from the previous snapshot."""
    new_jobs = [job for job in current if job.id not in previous]
    log.debug("Diff: %d current, %d previous, %d new", len(current), len(previous), len(new_jobs))
    return new_jobs


def save_snapshot(path: Path, jobs: list[Job], new_ids: set[str]) -> None:
    """Write docs/jobs.json: full current listing with is_new flags.

    Preserves first_seen from prior runs (caller sets it on Job); new jobs are
    stamped with the current time.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    serialized: list[SnapshotJobDict] = []
    for job in jobs:
        if not job.first_seen:
            job.first_seen = now
        entry: SnapshotJobDict = {**job.to_dict(), "is_new": job.id in new_ids}
        serialized.append(entry)

    payload = {"updated_at": now, "jobs": serialized}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.debug("Wrote %s: %d jobs (%d flagged is_new)", path, len(serialized), len(new_ids))
