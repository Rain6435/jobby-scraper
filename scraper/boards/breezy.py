"""Breezy HR public job board scraper.

One unauthenticated GET returns every open job with structured location and a
real posting date — no pagination, no per-job detail calls:
    GET https://<company>.breezy.hr/json
Each job has id, name, url, published_date (ISO+tz), location.name (primary),
locations[].name (all, for multi-location postings). Config:
    {"board": "breezy", "company": "<subdomain>"}.
"""

from __future__ import annotations

import logging

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import posted_days_from_iso, relative_day_text
from scraper.models import Job

LIST_URL = "https://{company}.breezy.hr/json"
TIMEOUT = 30

log = logging.getLogger("scraper.breezy")


class BreezyScraper(BaseScraper):
    source = "breezy"

    def fetch_jobs(self) -> list[Job]:
        subdomain = self.company["company"]
        session = make_session()
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})

        log.debug("%s: fetching job list", self.name)
        resp = session.get(LIST_URL.format(company=subdomain), timeout=TIMEOUT)
        resp.raise_for_status()
        postings = resp.json()
        log.debug("%s: %d postings returned", self.name, len(postings))

        jobs: list[Job] = []
        for p in postings:
            locations = self._locations(p)
            posted_days = posted_days_from_iso(p.get("published_date", ""))
            jobs.append(
                Job(
                    id=f"{self.slug}:{p['id']}",
                    company=self.name,
                    title=(p.get("name") or "").strip(),
                    location=locations[0] if locations else "",
                    locations=locations,
                    url=p.get("url", ""),
                    posted_on=relative_day_text(posted_days),
                    posted_days=posted_days,
                    source=self.source,
                )
            )
        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    @staticmethod
    def _locations(posting: dict) -> list[str]:
        """Prefer the locations[] list (multi-location postings), falling back
        to the single top-level location."""
        locs = [loc.get("name") for loc in posting.get("locations") or []]
        locs = [loc for loc in locs if loc]
        if locs:
            return locs
        name = (posting.get("location") or {}).get("name")
        return [name] if name else []
