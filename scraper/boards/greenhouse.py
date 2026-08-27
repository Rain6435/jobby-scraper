"""Greenhouse public job board scraper.

One unauthenticated GET returns every job with its location, posting date, and
(with content=true) full description HTML — no pagination, no per-job detail
calls:
    GET https://boards-api.greenhouse.io/v1/boards/<token>/jobs?content=true
Each job has id, title, location.name, offices[].location, absolute_url,
first_published (ISO+tz), content (HTML, only with content=true). Config:
{"board": "greenhouse", "token": "<token>"}.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import NotRequired, TypedDict, cast

from scraper.boards.base import BaseScraper, make_session
from scraper.config_types import GreenhouseConfig
from scraper.models import Job
from scraper.text import html_to_text

API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
TIMEOUT = 30

log = logging.getLogger("scraper.greenhouse")


class GreenhouseLocationName(TypedDict):
    name: NotRequired[str]


class GreenhouseOffice(TypedDict):
    name: NotRequired[str]
    location: NotRequired[str]


class GreenhousePosting(TypedDict):
    id: int
    title: NotRequired[str]
    location: NotRequired[GreenhouseLocationName]
    offices: NotRequired[list[GreenhouseOffice]]
    absolute_url: NotRequired[str]
    first_published: NotRequired[str]
    content: NotRequired[str]


class GreenhouseJobsResponse(TypedDict):
    jobs: NotRequired[list[GreenhousePosting]]


def posted_days_from_iso(iso: str) -> int | None:
    """Whole days between an ISO-8601 timestamp and now (UTC). None if unparseable."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - dt
    return max(delta.days, 0)


def relative_day_text(days: int | None) -> str:
    if days is None:
        return ""
    if days == 0:
        return "Today"
    if days == 1:
        return "Yesterday"
    return f"{days} days ago"


class GreenhouseScraper(BaseScraper):
    source = "greenhouse"

    def fetch_jobs(self) -> list[Job]:
        company: GreenhouseConfig = cast(GreenhouseConfig, self.company)
        token = company["token"]
        session = make_session()
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})

        log.debug("%s: fetching job list", self.name)
        resp = session.get(API.format(token=token), params={"content": "true"}, timeout=TIMEOUT)
        resp.raise_for_status()
        body: GreenhouseJobsResponse = resp.json()
        postings = body.get("jobs", [])
        log.debug("%s: %d postings returned", self.name, len(postings))

        jobs: list[Job] = []
        for p in postings:
            locations = self._locations(p)
            posted_days = posted_days_from_iso(p.get("first_published", ""))
            jobs.append(
                Job(
                    id=f"{self.slug}:{p['id']}",
                    company=self.name,
                    title=(p.get("title") or "").strip(),
                    location=locations[0] if locations else "",
                    locations=locations,
                    url=p.get("absolute_url", ""),
                    posted_on=relative_day_text(posted_days),
                    posted_days=posted_days,
                    source=self.source,
                    description=html_to_text(p.get("content", "")),
                )
            )
        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    @staticmethod
    def _locations(posting: GreenhousePosting) -> list[str]:
        """Prefer offices[].location ("City, Country") for better classification,
        falling back to the free-form location.name."""
        offices = posting.get("offices") or []
        locs = [o.get("location") or o.get("name") for o in offices]
        locs = [loc for loc in locs if loc]
        if locs:
            return locs
        name = (posting.get("location") or {}).get("name")
        return [name] if name else []
