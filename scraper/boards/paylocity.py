"""Paylocity Recruiting job board scraper.

Queries the public Paylocity Job Feed V2:
    GET https://recruiting.paylocity.com/recruiting/v2/api/feed/jobs/<guid>
Config:
{"board": "paylocity", "guid": "<integration_guid>"}
"""

from __future__ import annotations

import logging
from typing import NotRequired, TypedDict, cast

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import posted_days_from_iso, relative_day_text
from scraper.config_types import PaylocityConfig
from scraper.models import Job
from scraper.text import html_to_text

FEED_URL = "https://recruiting.paylocity.com/recruiting/v2/api/feed/jobs/{guid}"
TIMEOUT = 30

log = logging.getLogger("scraper.paylocity")


class PaylocityLocation(TypedDict):
    city: NotRequired[str | None]
    state: NotRequired[str | None]
    zip: NotRequired[str | None]
    country: NotRequired[str | None]


class PaylocityJobItem(TypedDict):
    jobId: NotRequired[int | str]
    publicJobId: NotRequired[int | str | None]
    jobTitle: NotRequired[str]
    jobDescription: NotRequired[str | None]
    applyUrl: NotRequired[str | None]
    jobLocation: NotRequired[PaylocityLocation | None]
    postedDate: NotRequired[str | None]
    department: NotRequired[str | None]


class PaylocityResponse(TypedDict):
    displayName: NotRequired[str]
    jobs: NotRequired[list[PaylocityJobItem]]


class PaylocityScraper(BaseScraper):
    source = "paylocity"

    def fetch_jobs(self) -> list[Job]:
        cfg: PaylocityConfig = cast(PaylocityConfig, self.company)
        guid = cfg["guid"]

        session = make_session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            }
        )

        url = FEED_URL.format(guid=guid)
        log.debug("%s: fetching Paylocity feed for guid=%s", self.name, guid)
        resp = session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()

        raw_json: object = resp.json()
        if not isinstance(raw_json, dict):
            return []

        data = cast(PaylocityResponse, raw_json)
        job_items = data.get("jobs", [])
        log.debug("%s: %d jobs returned", self.name, len(job_items))

        jobs: list[Job] = []
        for item in job_items:
            raw_id = item.get("publicJobId") or item.get("jobId") or ""
            job_id = str(raw_id).strip()
            if not job_id:
                continue

            title = (item.get("jobTitle") or "").strip()
            loc_str = self._format_location(item.get("jobLocation"))
            posted_iso = item.get("postedDate") or ""
            posted_days = posted_days_from_iso(posted_iso)

            desc_html = item.get("jobDescription") or ""
            description = html_to_text(desc_html)

            apply_url = (
                item.get("applyUrl")
                or f"https://recruiting.paylocity.com/recruiting/jobs/Details/{job_id}"
            )

            jobs.append(
                Job(
                    id=f"{self.slug}:{job_id}",
                    company=self.name,
                    title=title,
                    location=loc_str,
                    locations=[loc_str] if loc_str else [],
                    url=apply_url,
                    posted_on=relative_day_text(posted_days),
                    posted_days=posted_days,
                    source=self.source,
                    description=description,
                )
            )

        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    @staticmethod
    def _format_location(loc: PaylocityLocation | None) -> str:
        if not loc:
            return ""
        city = (loc.get("city") or "").strip()
        state = (loc.get("state") or "").strip()
        country = (loc.get("country") or "").strip()
        parts = [p for p in (city, state, country) if p]
        return ", ".join(parts)
