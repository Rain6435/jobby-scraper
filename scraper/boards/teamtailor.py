"""Teamtailor public job board scraper.

One unauthenticated GET returns every published job as a JSON Feed — no
pagination, no per-job detail calls:
    GET https://<slug>.teamtailor.com/jobs.json
Response is {"version", "title", "items": [...]}. Each item has id (uuid),
title, url, date_published (ISO 8601 with offset), content_html, and a nested
schema.org _jobposting.jobLocation[] with address.addressLocality/Region/Country.
Config: {"board": "teamtailor", "company": "<slug>"}.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import cast, NotRequired, TypedDict

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import relative_day_text
from scraper.config_types import TeamtailorConfig
from scraper.models import Job
from scraper.text import html_to_text

API = "https://{slug}.teamtailor.com/jobs.json"
TIMEOUT = 30

log = logging.getLogger("scraper.teamtailor")


class TeamtailorAddress(TypedDict):
    addressLocality: NotRequired[str]
    addressRegion: NotRequired[str]
    addressCountry: NotRequired[str]


class TeamtailorJobLocationEntry(TypedDict):
    address: NotRequired[TeamtailorAddress]


class TeamtailorJobPosting(TypedDict):
    jobLocation: NotRequired[list[TeamtailorJobLocationEntry]]


class TeamtailorItem(TypedDict):
    id: str
    title: NotRequired[str]
    url: NotRequired[str]
    date_published: NotRequired[str]
    content_html: NotRequired[str]
    _jobposting: NotRequired[TeamtailorJobPosting]


class TeamtailorJobsResponse(TypedDict):
    items: NotRequired[list[TeamtailorItem]]


def posted_days_from_iso(iso: str | None) -> int | None:
    """Whole days between an ISO-8601 timestamp and now (UTC). None if unparseable."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    return max(delta.days, 0)


class TeamtailorScraper(BaseScraper):
    source = "teamtailor"

    def fetch_jobs(self) -> list[Job]:
        company: TeamtailorConfig = cast(TeamtailorConfig, self.company)
        slug = company["company"]
        session = make_session()
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})

        log.debug("%s: fetching job list", self.name)
        resp = session.get(API.format(slug=slug), timeout=TIMEOUT)
        resp.raise_for_status()
        body: TeamtailorJobsResponse = resp.json()
        postings = body.get("items", [])
        log.debug("%s: %d postings returned", self.name, len(postings))

        jobs: list[Job] = []
        for p in postings:
            locations = self._locations(p)
            posted_days = posted_days_from_iso(p.get("date_published"))
            jobs.append(
                Job(
                    id=f"{self.slug}:{p['id']}",
                    company=self.name,
                    title=(p.get("title") or "").strip(),
                    location=locations[0] if locations else "",
                    locations=locations,
                    url=p.get("url", ""),
                    posted_on=relative_day_text(posted_days),
                    posted_days=posted_days,
                    source=self.source,
                    description=html_to_text(p.get("content_html", "")),
                )
            )
        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    @staticmethod
    def _locations(posting: TeamtailorItem) -> list[str]:
        """schema.org _jobposting.jobLocation[].address, best-effort — absent
        or malformed on some postings, so any missing piece just yields []."""
        jobposting = posting.get("_jobposting") or {}
        entries = jobposting.get("jobLocation") or []
        locs: list[str] = []
        for entry in entries:
            address = (entry or {}).get("address") or {}
            parts = [
                address.get("addressLocality"),
                address.get("addressRegion"),
                address.get("addressCountry"),
            ]
            joined = ", ".join(p for p in parts if p)
            if joined:
                locs.append(joined)
        return locs
