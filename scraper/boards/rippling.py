"""Rippling ATS public job board scraper.

The list endpoint already carries structured locations (the posting date lives
only in detail — we still skip it; age is tracked by Job.first_seen instead).
The description is detail-only, so it costs one extra GET per listed job:
    GET https://ats.rippling.com/api/v2/board/<board_id>/jobs?page=&pageSize=50
    GET https://ats.rippling.com/api/v2/board/<board_id>/jobs/<job_id>
        → {"description": {"role": "<html>...", "company": "<html>..."}}
      (some boards may return "description" as a plain string instead of this
      object shape — handled defensively).
Each list item has id (uuid), name, url, locations[].name. Config:
    {"board": "rippling", "board_id": "<slug>"}.
"""

from __future__ import annotations

import logging
from typing import NotRequired, TypedDict, cast

import requests

from scraper.boards.base import BaseScraper, make_session
from scraper.config_types import RipplingConfig
from scraper.models import Job
from scraper.text import html_to_text

API = "https://ats.rippling.com/api/v2/board/{board_id}/jobs"
DETAIL_URL = "https://ats.rippling.com/api/v2/board/{board_id}/jobs/{job_id}"
PAGE_SIZE = 50
MAX_PAGES = 50  # safety cap
TIMEOUT = 30

log = logging.getLogger("scraper.rippling")


class RipplingLocation(TypedDict):
    name: NotRequired[str]
    city: NotRequired[str]
    state: NotRequired[str]
    country: NotRequired[str]


class RipplingItem(TypedDict):
    id: str
    name: NotRequired[str]
    url: NotRequired[str]
    locations: NotRequired[list[RipplingLocation]]


class RipplingJobsResponse(TypedDict):
    items: NotRequired[list[RipplingItem]]
    totalPages: NotRequired[int]


class RipplingDescription(TypedDict):
    role: NotRequired[str]
    company: NotRequired[str]


class RipplingJobDetailResponse(TypedDict):
    description: NotRequired[str | RipplingDescription]


class RipplingScraper(BaseScraper):
    source = "rippling"

    def fetch_jobs(self) -> list[Job]:
        company: RipplingConfig = cast(RipplingConfig, self.company)
        board_id = company["board_id"]
        url = API.format(board_id=board_id)
        session = make_session()
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})

        jobs: list[Job] = []
        page = 0
        while page < MAX_PAGES:
            log.debug("%s: fetching page=%d", self.name, page)
            resp = session.get(url, params={"page": page, "pageSize": PAGE_SIZE}, timeout=TIMEOUT)
            resp.raise_for_status()
            data: RipplingJobsResponse = resp.json()
            log.debug("%s: totalPages=%d reported", self.name, data.get("totalPages", 1))
            for item in data.get("items", []):
                locations: list[str] = []
                for loc in item.get("locations", []):
                    where = self._location_str(loc)
                    if where:
                        locations.append(where)
                job_id = f"{self.slug}:{item['id']}"
                (description,) = cast(
                    "tuple[str]",
                    self._fetch_with_cache(
                        job_id,
                        ("description",),
                        lambda: (self._fetch_description(session, board_id, item["id"]),),
                    ),
                )
                jobs.append(
                    Job(
                        id=job_id,
                        company=self.name,
                        title=(item.get("name") or "").strip(),
                        location=locations[0] if locations else "",
                        locations=locations,
                        url=item.get("url", ""),
                        posted_on="",  # date only in detail — skipped
                        posted_days=None,  # age tracked via first_seen
                        source=self.source,
                        description=description,
                    )
                )
            if page >= data.get("totalPages", 1) - 1:
                log.debug("%s: reached last page at page=%d, stopping", self.name, page)
                break
            page += 1
        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    @staticmethod
    def _fetch_description(session: requests.Session, board_id: str, job_id: str) -> str:
        try:
            resp = session.get(DETAIL_URL.format(board_id=board_id, job_id=job_id), timeout=TIMEOUT)
            resp.raise_for_status()
            detail: RipplingJobDetailResponse = resp.json()
            description = detail.get("description", "")
            # Usually {"role": "<html>", "company": "<html>"} — "role" is the
            # actual posting text. Some boards may return a plain string instead.
            html = description.get("role", "") if isinstance(description, dict) else description
            return html_to_text(html)
        except Exception:
            log.warning("Rippling detail fetch failed for job %s", job_id)
            return ""

    @staticmethod
    def _location_str(loc: RipplingLocation) -> str:
        """Build "City, State, Country" from the structured fields.

        Avoids Rippling's raw name like "Hybrid (Montreal, QC, CA)" — its "CA"
        country code for Canada collides with California in the location
        classifier. Spelling out the country ("Canada") keeps Montreal jobs
        classified correctly. Falls back to the raw name if fields are absent.
        """
        raw_parts = [loc.get("city"), loc.get("state"), loc.get("country")]
        parts = [p for p in raw_parts if p]
        return ", ".join(parts) if parts else (loc.get("name") or "")
