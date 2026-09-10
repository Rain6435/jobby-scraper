"""Microsoft careers scraper (careers.microsoft.com).

Microsoft runs a custom career portal (PCSX) with dedicated JSON search and
details endpoints:

    Search:  GET https://apply.careers.microsoft.com/api/pcsx/search?domain=microsoft.com
    Details: GET https://apply.careers.microsoft.com/api/pcsx/position_details?domain=microsoft.com&position_id={id}

No authentication required. The search response returns:
    count      → total matched live postings
    positions  → list of job objects with ID, title, standardized locations,
                 and epoch timestamps

Job descriptions are fetched on demand via position_details and cached across
runs using BaseScraper._fetch_details_concurrent.

Config entry:
    {"board": "microsoft", "name": "Microsoft"}
    {"board": "microsoft", "name": "Microsoft", "location": "Remote"}
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

SEARCH_URL = "https://apply.careers.microsoft.com/api/pcsx/search"
DETAIL_URL = "https://apply.careers.microsoft.com/api/pcsx/position_details"
PAGE_SIZE = 10
DEFAULT_MAX_PAGES = 30  # ~300 jobs by default (sorted by newest timestamp)
MAX_PAGES_CAP = 300  # safety cap — up to ~3000 jobs
TIMEOUT = 30

log = logging.getLogger("scraper.microsoft")


class MicrosoftPosition(TypedDict):
    id: NotRequired[int]
    atsJobId: NotRequired[str]
    displayJobId: NotRequired[str]
    name: NotRequired[str]
    locations: NotRequired[list[str]]
    standardizedLocations: NotRequired[list[str]]
    postedTs: NotRequired[int]
    workLocationOption: NotRequired[str]
    department: NotRequired[str]
    positionUrl: NotRequired[str]


class MicrosoftSearchData(TypedDict):
    count: NotRequired[int]
    positions: NotRequired[list[MicrosoftPosition]]


class MicrosoftSearchResponse(TypedDict):
    status: NotRequired[int]
    data: NotRequired[MicrosoftSearchData]


class MicrosoftDetailData(TypedDict):
    jobDescription: NotRequired[str]


class MicrosoftDetailResponse(TypedDict):
    status: NotRequired[int]
    data: NotRequired[MicrosoftDetailData]


def posted_days_from_epoch(ts: int | float | None) -> int | None:
    """Convert Unix epoch timestamp (seconds or ms) to days elapsed since posting."""
    if not ts:
        return None
    if ts > 1e11:
        ts = ts / 1000
    try:
        dt = datetime.fromtimestamp(ts, UTC)
        delta = datetime.now(UTC) - dt
        return max(delta.days, 0)
    except (ValueError, OverflowError, OSError):
        return None


class MicrosoftScraper(BaseScraper):
    source = "microsoft"

    def fetch_jobs(self) -> list[Job]:
        session = make_session()
        session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            }
        )

        base_params: dict[str, str | int] = {
            "domain": "microsoft.com",
            "sort_by": "timestamp",
        }
        if loc := self.company.get("location"):
            base_params["location"] = str(loc)
        if q := self.company.get("query"):
            base_params["query"] = str(q)

        configured_pages = self.company.get("max_pages")
        max_pages = (
            min(int(configured_pages), MAX_PAGES_CAP) if configured_pages else DEFAULT_MAX_PAGES
        )

        positions_by_id: dict[str, MicrosoftPosition] = {}
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

            data = cast(MicrosoftSearchResponse, raw).get("data") or {}
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

    def _to_job(self, pos: MicrosoftPosition, description: str = "") -> Job:
        job_id = str(pos.get("id") or "").strip()
        title = (pos.get("name") or "").strip()

        locs = pos.get("standardizedLocations") or pos.get("locations") or []
        primary_loc = locs[0] if locs else ""

        rel_url = (pos.get("positionUrl") or f"/careers/job/{job_id}").strip()
        url = (
            f"https://apply.careers.microsoft.com{rel_url}" if rel_url.startswith("/") else rel_url
        )

        posted_days = posted_days_from_epoch(pos.get("postedTs"))
        posted_on = relative_day_text(posted_days)

        return Job(
            id=f"{self.slug}:{job_id}",
            company=self.name,
            title=title,
            location=primary_loc,
            locations=locs,
            url=url,
            posted_on=posted_on,
            posted_days=posted_days,
            source=self.source,
            description=description,
        )

    @staticmethod
    def _fetch_detail(session: requests.Session, position_id: str) -> tuple[str]:
        try:
            params = {
                "domain": "microsoft.com",
                "position_id": position_id,
                "hl": "en",
            }
            resp = session.get(DETAIL_URL, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            data: MicrosoftDetailResponse = resp.json()
            raw_html = (data.get("data") or {}).get("jobDescription") or ""
            return (html_to_text(raw_html),)
        except Exception:
            log.warning("Microsoft detail fetch failed for position %s", position_id)
            return ("",)
