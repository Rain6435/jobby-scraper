"""Lever public job board scraper.

One unauthenticated GET returns every open job with location, posting date,
and full description — no pagination, no per-job detail calls:
    GET https://api.lever.co/v0/postings/<company>?mode=json
Response is a bare JSON array (no envelope key). Each posting has id, text
(title), hostedUrl, createdAt (epoch milliseconds, not ISO), categories.location
(primary), categories.allLocations (array), descriptionPlain. Config:
{"board": "lever", "company": "<slug>"}.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import relative_day_text
from scraper.models import Job
from scraper.text import html_to_text

API = "https://api.lever.co/v0/postings/{company}"
TIMEOUT = 30

log = logging.getLogger("scraper.lever")


def posted_days_from_epoch_ms(ms: int | None) -> int | None:
    """Whole days between an epoch-millisecond timestamp and now (UTC). None if missing."""
    if not ms:
        return None
    try:
        dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
    delta = datetime.now(timezone.utc) - dt
    return max(delta.days, 0)


class LeverScraper(BaseScraper):
    source = "lever"

    def fetch_jobs(self) -> list[Job]:
        company = self.company["company"]
        session = make_session()
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})

        log.debug("%s: fetching job list", self.name)
        resp = session.get(
            API.format(company=company), params={"mode": "json"}, timeout=TIMEOUT
        )
        resp.raise_for_status()
        postings = resp.json()
        log.debug("%s: %d postings returned", self.name, len(postings))

        jobs: list[Job] = []
        for p in postings:
            locations = self._locations(p)
            posted_days = posted_days_from_epoch_ms(p.get("createdAt"))
            jobs.append(
                Job(
                    id=f"{self.slug}:{p['id']}",
                    company=self.name,
                    title=(p.get("text") or "").strip(),
                    location=locations[0] if locations else "",
                    locations=locations,
                    url=p.get("hostedUrl", ""),
                    posted_on=relative_day_text(posted_days),
                    posted_days=posted_days,
                    source=self.source,
                    description=self._description(p),
                )
            )
        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    @staticmethod
    def _description(posting: dict) -> str:
        """Prefer descriptionPlain (already plain text, no strip needed) over
        stripping the HTML description."""
        plain = (posting.get("descriptionPlain") or "").strip()
        if plain:
            return plain
        return html_to_text(posting.get("description", ""))

    @staticmethod
    def _locations(posting: dict) -> list[str]:
        """categories.allLocations, falling back to the single categories.location."""
        categories = posting.get("categories") or {}
        locs = categories.get("allLocations") or []
        if locs:
            return [loc for loc in locs if loc]
        primary = categories.get("location")
        return [primary] if primary else []
