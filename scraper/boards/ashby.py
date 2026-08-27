"""Ashby public job board scraper.

One unauthenticated GET returns every open job with location, posting date, and
full description — no pagination, no per-job detail calls:
    GET https://api.ashbyhq.com/posting-api/job-board/<slug>?includeCompensation=true
Each job has id, title, location, secondaryLocations[].location, publishedAt
(ISO+tz), jobUrl, descriptionPlain, descriptionHtml. Config:
{"board": "ashby", "slug": "<slug>"}.
"""

from __future__ import annotations

import logging
from typing import NotRequired, TypedDict, cast

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import posted_days_from_iso, relative_day_text
from scraper.config_types import AshbyConfig
from scraper.models import Job
from scraper.text import html_to_text

API = "https://api.ashbyhq.com/posting-api/job-board/{slug}"
TIMEOUT = 30

log = logging.getLogger("scraper.ashby")


class AshbySecondaryLocation(TypedDict):
    location: NotRequired[str]


class AshbyPosting(TypedDict):
    id: str
    title: NotRequired[str]
    location: NotRequired[str]
    secondaryLocations: NotRequired[list[AshbySecondaryLocation]]
    publishedAt: NotRequired[str]
    jobUrl: NotRequired[str]
    descriptionPlain: NotRequired[str]
    descriptionHtml: NotRequired[str]


class AshbyJobBoardResponse(TypedDict):
    jobs: NotRequired[list[AshbyPosting]]


class AshbyScraper(BaseScraper):
    source = "ashby"

    def fetch_jobs(self) -> list[Job]:
        company: AshbyConfig = cast(AshbyConfig, self.company)
        slug = company["slug"]
        session = make_session()
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})

        log.debug("%s: fetching job list", self.name)
        resp = session.get(
            API.format(slug=slug),
            params={"includeCompensation": "true"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        body: AshbyJobBoardResponse = resp.json()
        postings = body.get("jobs", [])
        log.debug("%s: %d postings returned", self.name, len(postings))

        jobs: list[Job] = []
        for p in postings:
            locations = self._locations(p)
            posted_days = posted_days_from_iso(p.get("publishedAt", ""))
            jobs.append(
                Job(
                    id=f"{self.slug}:{p['id']}",
                    company=self.name,
                    title=(p.get("title") or "").strip(),
                    location=locations[0] if locations else "",
                    locations=locations,
                    url=p.get("jobUrl", ""),
                    posted_on=relative_day_text(posted_days),
                    posted_days=posted_days,
                    source=self.source,
                    description=self._description(p),
                )
            )
        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    @staticmethod
    def _description(posting: AshbyPosting) -> str:
        """Prefer descriptionPlain (already plain text, no strip needed) over
        stripping descriptionHtml."""
        plain = (posting.get("descriptionPlain") or "").strip()
        if plain:
            return plain
        return html_to_text(posting.get("descriptionHtml", ""))

    @staticmethod
    def _locations(posting: AshbyPosting) -> list[str]:
        """Primary location plus any secondaryLocations, flattened to strings."""
        locs = [posting.get("location")]
        locs += [loc.get("location") for loc in posting.get("secondaryLocations") or []]
        return [loc for loc in locs if loc]
