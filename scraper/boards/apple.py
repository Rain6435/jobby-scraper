"""Apple careers scraper (jobs.apple.com).

Apple's career portal uses a React/Remix architecture that embeds full search
state inside a global hydration variable on each search page:

    GET https://jobs.apple.com/en-us/search?page={page}
    window.__staticRouterHydrationData = JSON.parse("...");

No authentication or session handshake required. The hydration state provides:
    totalRecords  → total active postings
    searchResults → list of job objects with ID, title, structured locations,
                    plain-text jobSummary, and ISO GMT timestamps

Config entry:
    {"board": "apple", "name": "Apple"}
    {"board": "apple", "name": "Apple", "location": "united-states-USA"}
"""

from __future__ import annotations

import json
import logging
import re
from typing import NotRequired, TypedDict, cast

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import posted_days_from_iso, relative_day_text
from scraper.models import Job

SEARCH_URL = "https://jobs.apple.com/en-us/search"
PAGE_SIZE = 20
DEFAULT_MAX_PAGES = 50  # ~1000 jobs by default
MAX_PAGES_CAP = 350  # safety cap — up to ~7000 jobs
TIMEOUT = 30

log = logging.getLogger("scraper.apple")


class AppleLocation(TypedDict):
    name: NotRequired[str]
    city: NotRequired[str]
    stateProvince: NotRequired[str]
    countryName: NotRequired[str]


class RawAppleJob(TypedDict):
    positionId: NotRequired[str | int]
    id: NotRequired[str | int]
    postingTitle: NotRequired[str]
    transformedPostingTitle: NotRequired[str]
    jobSummary: NotRequired[str]
    postingDate: NotRequired[str]
    postDateInGMT: NotRequired[str]
    locations: NotRequired[list[AppleLocation]]


class AppleSearchData(TypedDict):
    totalRecords: NotRequired[int]
    searchResults: NotRequired[list[RawAppleJob]]


class AppleLoaderData(TypedDict):
    search: NotRequired[AppleSearchData]


class AppleHydrationData(TypedDict):
    loaderData: NotRequired[AppleLoaderData]


class AppleScraper(BaseScraper):
    source = "apple"

    def fetch_jobs(self) -> list[Job]:
        session = make_session()
        session.headers.update(
            {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            }
        )

        base_params: dict[str, str | int] = {}
        if search := self.company.get("search"):
            base_params["search"] = str(search)
        if location := self.company.get("location"):
            base_params["location"] = str(location)
        if team := self.company.get("team"):
            base_params["team"] = str(team)

        configured_pages = self.company.get("max_pages")
        max_pages = (
            min(int(configured_pages), MAX_PAGES_CAP) if configured_pages else DEFAULT_MAX_PAGES
        )

        jobs: list[Job] = []
        for page in range(1, max_pages + 1):
            params = dict(base_params)
            params["page"] = page

            log.debug("%s: page=%d", self.name, page)
            resp = session.get(SEARCH_URL, params=params, timeout=TIMEOUT)
            resp.raise_for_status()

            total, page_jobs = self._extract_jobs_from_html(resp.text)
            log.debug(
                "%s: page=%d returned %d jobs (total=%d)",
                self.name,
                page,
                len(page_jobs),
                total,
            )

            for raw in page_jobs:
                jobs.append(self._to_job(raw))

            if not page_jobs or len(jobs) >= total:
                break

        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    @staticmethod
    def _extract_jobs_from_html(html: str) -> tuple[int, list[RawAppleJob]]:
        match = re.search(
            r"window\.__staticRouterHydrationData\s*=\s*JSON\.parse\(([\"\x27].*?[\"\x27])\);",
            html,
        )
        if not match:
            return 0, []

        try:
            raw_str = json.loads(match.group(1))
            data = json.loads(raw_str) if isinstance(raw_str, str) else raw_str
            search_data = cast(AppleHydrationData, data).get("loaderData", {}).get("search", {})
            total = search_data.get("totalRecords", 0)
            results = search_data.get("searchResults", [])
            return total, results
        except Exception as e:
            log.warning("Failed to parse Apple hydration JSON: %s", e)
            return 0, []

    def _to_job(self, raw: RawAppleJob) -> Job:
        raw_id = raw.get("positionId") or raw.get("id") or ""
        job_id = str(raw_id).strip()

        title = (raw.get("postingTitle") or "").strip()
        slug_title = (raw.get("transformedPostingTitle") or "").strip()

        # Build clean locations
        locations: list[str] = []
        for loc in raw.get("locations") or []:
            name = (loc.get("name") or "").strip()
            if not name:
                parts = [
                    loc.get("city"),
                    loc.get("stateProvince"),
                    loc.get("countryName"),
                ]
                name = ", ".join(filter(None, [p.strip() for p in parts if p]))
            if name and name not in locations:
                locations.append(name)

        primary_loc = locations[0] if locations else ""

        url = (
            f"https://jobs.apple.com/en-us/details/{job_id}/{slug_title}"
            if slug_title
            else f"https://jobs.apple.com/en-us/details/{job_id}"
        )

        posted_days = posted_days_from_iso(raw.get("postDateInGMT") or "")
        posted_on = relative_day_text(posted_days)
        description = (raw.get("jobSummary") or "").strip()

        return Job(
            id=f"{self.slug}:{job_id}",
            company=self.name,
            title=title,
            location=primary_loc,
            locations=locations,
            url=url,
            posted_on=posted_on,
            posted_days=posted_days,
            source=self.source,
            description=description,
        )
