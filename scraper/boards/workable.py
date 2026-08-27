"""Workable public job board scraper.

One unauthenticated GET returns every open job with full description and
structured location fields — no pagination, no per-job detail calls:
    GET https://apply.workable.com/api/v1/widget/accounts/<slug>?details=true
The `details=true` param is required — without it, each job's `description`
field is present but always null. Response is {"name", "description",
"jobs": [...]}. Each job has shortcode (stable id), title, url,
published_on ("YYYY-MM-DD"), description (HTML), locations[] (each with
city/region/country), plus top-level city/state/country as a fallback when
locations[] is empty. Config: {"board": "workable", "company": "<slug>"}.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import NotRequired, TypedDict, cast

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import relative_day_text
from scraper.config_types import WorkableConfig
from scraper.models import Job
from scraper.text import html_to_text

API = "https://apply.workable.com/api/v1/widget/accounts/{slug}"
TIMEOUT = 30

log = logging.getLogger("scraper.workable")


class WorkableLocation(TypedDict):
    city: NotRequired[str]
    region: NotRequired[str]
    country: NotRequired[str]


class WorkablePosting(TypedDict):
    shortcode: str
    title: NotRequired[str]
    url: NotRequired[str]
    published_on: NotRequired[str]
    description: NotRequired[str]
    locations: NotRequired[list[WorkableLocation]]
    city: NotRequired[str]
    state: NotRequired[str]
    country: NotRequired[str]


class WorkableAccountResponse(TypedDict):
    jobs: NotRequired[list[WorkablePosting]]


def posted_days_from_date_str(date_str: str | None) -> int | None:
    """Whole days between a "YYYY-MM-DD" date string and now (UTC). None if unparseable."""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None
    delta = datetime.now(UTC) - dt
    return max(delta.days, 0)


class WorkableScraper(BaseScraper):
    source = "workable"

    def fetch_jobs(self) -> list[Job]:
        company: WorkableConfig = cast(WorkableConfig, self.company)
        slug = company["company"]
        session = make_session()
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})

        log.debug("%s: fetching job list", self.name)
        resp = session.get(API.format(slug=slug), params={"details": "true"}, timeout=TIMEOUT)
        resp.raise_for_status()
        body: WorkableAccountResponse = resp.json()
        postings = body.get("jobs", [])
        log.debug("%s: %d postings returned", self.name, len(postings))

        jobs: list[Job] = []
        for p in postings:
            locations = self._locations(p)
            posted_days = posted_days_from_date_str(p.get("published_on"))
            jobs.append(
                Job(
                    id=f"{self.slug}:{p['shortcode']}",
                    company=self.name,
                    title=(p.get("title") or "").strip(),
                    location=locations[0] if locations else "",
                    locations=locations,
                    url=p.get("url", ""),
                    posted_on=relative_day_text(posted_days),
                    posted_days=posted_days,
                    source=self.source,
                    description=html_to_text(p.get("description", "")),
                )
            )
        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    @staticmethod
    def _locations(posting: WorkablePosting) -> list[str]:
        """locations[] (each city/region/country), falling back to the
        top-level city/state/country fields when locations[] is empty."""
        entries = posting.get("locations") or []
        locs = [WorkableScraper._join_location(loc) for loc in entries]
        locs = [loc for loc in locs if loc]
        if locs:
            return locs
        fallback_loc: WorkableLocation = {
            "city": posting.get("city", ""),
            "region": posting.get("state", ""),
            "country": posting.get("country", ""),
        }
        fallback = WorkableScraper._join_location(fallback_loc)
        return [fallback] if fallback else []

    @staticmethod
    def _join_location(loc: WorkableLocation) -> str:
        parts = [loc.get("city"), loc.get("region"), loc.get("country")]
        return ", ".join(p for p in parts if p)
