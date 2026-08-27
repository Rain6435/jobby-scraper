"""Recruitee (Tellent) public job board scraper.

One unauthenticated GET returns every open offer with location, posting
date, and full description — no pagination, no per-job detail calls:
    GET https://<company>.recruitee.com/api/offers/
Each offer has id, title, careers_url, published_at (format
"YYYY-MM-DD HH:MM:SS UTC", not ISO-8601), description (HTML), and a
structured locations[] array (each with city/state/country). Config:
{"board": "recruitee", "company": "<subdomain>"}.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import NotRequired, TypedDict, cast

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import relative_day_text
from scraper.config_types import RecruiteeConfig
from scraper.models import Job
from scraper.text import html_to_text

API = "https://{company}.recruitee.com/api/offers/"
TIMEOUT = 30

log = logging.getLogger("scraper.recruitee")


class RecruiteeLocation(TypedDict):
    city: NotRequired[str]
    state: NotRequired[str]
    country: NotRequired[str]


class RecruiteeOffer(TypedDict):
    id: int
    title: NotRequired[str]
    careers_url: NotRequired[str]
    published_at: NotRequired[str]
    description: NotRequired[str]
    locations: NotRequired[list[RecruiteeLocation]]
    city: NotRequired[str]
    state_name: NotRequired[str]
    country: NotRequired[str]


class RecruiteeOffersResponse(TypedDict):
    offers: NotRequired[list[RecruiteeOffer]]


def posted_days_from_recruitee_ts(ts: str) -> int | None:
    """Whole days since a Recruitee "YYYY-MM-DD HH:MM:SS UTC" timestamp. None if unparseable."""
    if not ts:
        return None
    try:
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S %Z").replace(tzinfo=UTC)
    except ValueError:
        return None
    delta = datetime.now(UTC) - dt
    return max(delta.days, 0)


class RecruiteeScraper(BaseScraper):
    source = "recruitee"

    def fetch_jobs(self) -> list[Job]:
        cfg: RecruiteeConfig = cast(RecruiteeConfig, self.company)
        company = cfg["company"]
        session = make_session()
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})

        log.debug("%s: fetching job list", self.name)
        resp = session.get(API.format(company=company), timeout=TIMEOUT)
        resp.raise_for_status()
        body: RecruiteeOffersResponse = resp.json()
        offers = body.get("offers", [])
        log.debug("%s: %d offers returned", self.name, len(offers))

        jobs: list[Job] = []
        for o in offers:
            locations = self._locations(o)
            posted_days = posted_days_from_recruitee_ts(o.get("published_at", ""))
            jobs.append(
                Job(
                    id=f"{self.slug}:{o['id']}",
                    company=self.name,
                    title=(o.get("title") or "").strip(),
                    location=locations[0] if locations else "",
                    locations=locations,
                    url=o.get("careers_url", ""),
                    posted_on=relative_day_text(posted_days),
                    posted_days=posted_days,
                    source=self.source,
                    description=html_to_text(o.get("description", "")),
                )
            )
        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    @staticmethod
    def _locations(offer: RecruiteeOffer) -> list[str]:
        """Structured locations[] ("City, State, Country"), falling back to the
        offer's flat city/country fields."""
        locs: list[str] = []
        for loc in offer.get("locations") or []:
            parts = [loc.get("city"), loc.get("state"), loc.get("country")]
            where = ", ".join(p for p in parts if p)
            if where:
                locs.append(where)
        if locs:
            return locs
        parts = [offer.get("city"), offer.get("state_name"), offer.get("country")]
        where = ", ".join(p for p in parts if p)
        return [where] if where else []
