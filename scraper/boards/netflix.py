"""Netflix careers scraper (jobs.netflix.com / explore.jobs.netflix.net).

Netflix runs its career portal on Eightfold.ai at explore.jobs.netflix.net:

    Search:  GET https://explore.jobs.netflix.net/api/apply/v2/jobs?domain=netflix.com
    Details: GET https://explore.jobs.netflix.net/api/apply/v2/jobs/{id}?domain=netflix.com

No authentication required. The search response returns:
    count      → total matched live postings
    positions  → list of job objects with ID, title, locations, department,
                 and creation timestamp (epoch seconds)

Job descriptions are fetched on demand via the detail endpoint and cached
across runs using BaseScraper._fetch_details_concurrent.

Config entry:
    {"board": "netflix", "name": "Netflix"}
    {"board": "netflix", "name": "Netflix", "query": "engineer"}
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import NotRequired, TypedDict, cast

import requests

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import relative_day_text
from scraper.models import Job
from scraper.text import html_to_text

SEARCH_URL = "https://explore.jobs.netflix.net/api/apply/v2/jobs"
DETAIL_URL = "https://explore.jobs.netflix.net/api/apply/v2/jobs/{id}"
PAGE_SIZE = 10
DEFAULT_MAX_PAGES = 50  # ~500 jobs by default (Netflix has ~495 live postings)
MAX_PAGES_CAP = 150  # safety cap
TIMEOUT = 30

log = logging.getLogger("scraper.netflix")


class NetflixPosition(TypedDict):
    id: NotRequired[int | str]
    name: NotRequired[str]
    posting_name: NotRequired[str]
    location: NotRequired[str]
    locations: NotRequired[list[str]]
    department: NotRequired[str]
    business_unit: NotRequired[str]
    t_create: NotRequired[int]
    t_update: NotRequired[int]
    canonicalPositionUrl: NotRequired[str]
    ats_job_id: NotRequired[str]


class NetflixSearchResponse(TypedDict):
    count: NotRequired[int]
    positions: NotRequired[list[NetflixPosition]]


class NetflixScraper(BaseScraper):
    source = "netflix"

    def fetch_jobs(self) -> list[Job]:
        session = make_session()
        session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            }
        )

        base_params: list[tuple[str, str | int]] = [
            ("domain", "netflix.com"),
            ("num", PAGE_SIZE),
        ]
        if query := self.company.get("query"):
            base_params.append(("query", query))
        if location := self.company.get("location"):
            base_params.append(("location", location))

        cfg_max = self.company.get("max_pages")
        if isinstance(cfg_max, int) and cfg_max > 0:
            max_pages = min(cfg_max, MAX_PAGES_CAP)
        else:
            max_pages = DEFAULT_MAX_PAGES

        positions_by_id: dict[str, NetflixPosition] = {}
        for page in range(max_pages):
            start = page * PAGE_SIZE
            params = dict(base_params)
            params["start"] = start

            log.debug("%s: page=%d start=%d", self.name, page, start)
            resp = session.get(SEARCH_URL, params=params, timeout=TIMEOUT)
            resp.raise_for_status()

            raw: object = resp.json()
            if not isinstance(raw, dict):
                log.warning("%s: unexpected response type %s", self.name, type(raw))
                break

            data = cast(NetflixSearchResponse, raw)
            total_count = data.get("count") or 0
            positions = data.get("positions") or []

            log.debug(
                "%s: page=%d returned %d positions (total=%d)",
                self.name,
                page,
                len(positions),
                total_count,
            )

            for pos in positions:
                pid = str(pos.get("id") or "")
                if pid:
                    positions_by_id[pid] = pos

            if not positions or start + len(positions) >= total_count:
                break

        # Fetch descriptions concurrently if enabled (default True)
        should_fetch_details = self.company.get("fetch_details", True)
        job_ids = [f"{self.slug}:{pid}" for pid in positions_by_id]
        details: dict[str, tuple[object, ...]] = {}

        if should_fetch_details and job_ids:
            details = self._fetch_details_concurrent(
                job_ids,
                ("description",),
                lambda job_id: self._fetch_detail(session, job_id.split(":", 1)[1]),
                max_workers=4,
            )

        jobs: list[Job] = []
        for pid, p in positions_by_id.items():
            full_job_id = f"{self.slug}:{pid}"
            desc = ""
            if full_job_id in details:
                desc = cast(str, details[full_job_id][0])

            jobs.append(self._to_job(p, desc))

        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    def _fetch_detail(self, session: requests.Session, position_id: str) -> tuple[str]:
        """Fetch position details including full description."""
        url = DETAIL_URL.format(id=position_id)
        params = {"domain": "netflix.com"}
        try:
            resp = session.get(url, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            data: dict[str, object] = resp.json()
            raw_html = str(data.get("job_description") or "")
            return (html_to_text(raw_html),)
        except Exception as e:
            log.warning("%s: failed to fetch details for %s: %s", self.name, position_id, e)
            return ("",)

    def _to_job(self, raw: NetflixPosition, description: str) -> Job:
        raw_id = raw.get("id") or ""
        post_id = str(raw_id).strip()
        title = (raw.get("name") or raw.get("posting_name") or "").strip()

        locations = raw.get("locations") or []
        primary_loc = raw.get("location") or (locations[0] if locations else "")

        posted_days: int | None = None
        posted_date: str | None = None
        posted_on: str = ""
        if t_create := raw.get("t_create"):
            dt = datetime.fromtimestamp(t_create, tz=UTC)
            posted_date = dt.strftime("%Y-%m-%d")
            delta = (datetime.now(tz=UTC) - dt).days
            posted_days = max(0, delta)
            posted_on = relative_day_text(posted_days)

        url = (
            raw.get("canonicalPositionUrl")
            or f"https://explore.jobs.netflix.net/careers/job/{post_id}"
        )

        return Job(
            id=f"{self.slug}:{post_id}",
            company=self.name,
            title=title,
            location=primary_loc,
            locations=locations if locations else ([primary_loc] if primary_loc else []),
            url=url,
            posted_on=posted_on,
            source=self.source,
            posted_days=posted_days,
            posted_date=posted_date,
            description=description,
            company_blurb=self.company.get("blurb", ""),
        )
