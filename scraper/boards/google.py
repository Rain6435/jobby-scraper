"""Google careers scraper (careers.google.com / google.com/about/careers).

Google runs an internal BoQ application (boq_corp-hiring-boq-cportal-frontend)
that embeds live search results and full job descriptions into the HTML payload
via server-side rendered JavaScript callbacks:

    Endpoint: GET https://www.google.com/about/careers/applications/jobs/results
    Data block: AF_initDataCallback({key: 'ds:1', ... data: [...]})

Each posting record includes the numeric job ID, title, structured multi-location
entries, company/division name (Google, DeepMind, YouTube), epoch creation
timestamps, and complete role descriptions, responsibilities, and qualifications
without requiring separate detail HTTP calls.

Config entry:
    {"board": "google", "name": "Google"}
    {"board": "google", "name": "Google DeepMind", "company_name": "DeepMind"}
    {"board": "google", "name": "Google", "location": "Seattle", "query": "software"}
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import cast

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import relative_day_text
from scraper.models import Job
from scraper.text import html_to_text

BASE_URL = "https://www.google.com/about/careers/applications/jobs/results"
PAGE_SIZE = 20
DEFAULT_MAX_PAGES = 50  # ~1,000 jobs by default (Google has ~3,400 active roles)
MAX_PAGES_CAP = 200  # safety cap — up to 4,000 jobs
TIMEOUT = 30

log = logging.getLogger("scraper.google")


class GoogleScraper(BaseScraper):
    source = "google"

    def fetch_jobs(self) -> list[Job]:
        session = make_session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

        base_params: list[tuple[str, str | int]] = []
        if q := self.company.get("query"):
            base_params.append(("q", q))
        if loc := self.company.get("location"):
            base_params.append(("location", loc))
        if comp := self.company.get("company_name"):
            base_params.append(("company", comp))

        cfg_max = self.company.get("max_pages")
        if isinstance(cfg_max, int) and cfg_max > 0:
            max_pages = min(cfg_max, MAX_PAGES_CAP)
        else:
            max_pages = DEFAULT_MAX_PAGES

        jobs: list[Job] = []

        for page in range(1, max_pages + 1):
            params = [("page", page)] + base_params
            log.debug("%s: page=%d params=%s", self.name, page, params)

            resp = session.get(BASE_URL, params=params, timeout=TIMEOUT)
            resp.raise_for_status()

            raw_jobs, total_count = self._parse_page(resp.text)
            log.debug(
                "%s: page=%d returned %d postings (total=%d)",
                self.name,
                page,
                len(raw_jobs),
                total_count,
            )

            if not raw_jobs:
                break

            for raw in raw_jobs:
                job = self._to_job(raw)
                if job:
                    jobs.append(job)

            if len(raw_jobs) < PAGE_SIZE or (total_count and len(jobs) >= total_count):
                break

        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    def _parse_page(self, html_content: str) -> tuple[list[list[object]], int]:
        """Extract the ds:1 data array and total count from AF_initDataCallback."""
        matches = re.findall(
            r"AF_initDataCallback\s*\(\s*\{.*?key:\s*[\'\"](ds:1)[\'\"].*?data:\s*(\[.*?\])\s*,\s*sideChannel:",
            html_content,
            re.DOTALL,
        )
        if not matches:
            log.warning("%s: could not find AF_initDataCallback for ds:1", self.name)
            return [], 0

        try:
            data_raw: object = json.loads(matches[0][1])
            if not isinstance(data_raw, list):
                return [], 0
            data = cast(list[object], data_raw)
            if not data:
                return [], 0

            raw_jobs: list[list[object]] = []
            if data and isinstance(data[0], list):
                raw_jobs = [
                    cast(list[object], item)
                    for item in cast(list[object], data[0])
                    if isinstance(item, list)
                ]
            total_count = data[2] if len(data) > 2 and isinstance(data[2], int) else 0
            return raw_jobs, total_count
        except Exception as e:
            log.warning("%s: failed to parse ds:1 JSON: %s", self.name, e)
            return [], 0

    def _to_job(self, raw: list[object]) -> Job | None:
        if not raw:
            return None

        job_id = str(raw[0]).strip() if len(raw) > 0 and raw[0] is not None else ""
        if not job_id:
            return None

        title = str(raw[1]).strip() if len(raw) > 1 and raw[1] else ""

        # Parse locations list from raw[9]
        locations: list[str] = []
        if len(raw) > 9 and isinstance(raw[9], list):
            for item in cast(list[object], raw[9]):
                if isinstance(item, list):
                    item_list = cast(list[object], item)
                    if (
                        len(item_list) > 0
                        and isinstance(item_list[0], str)
                        and item_list[0].strip()
                    ):
                        locations.append(item_list[0].strip())

        primary_loc = locations[0] if locations else "Remote"

        # Creation timestamp from raw[12][0] (epoch seconds)
        posted_days: int | None = None
        posted_date: str | None = None
        posted_on: str = ""
        if len(raw) > 12 and isinstance(raw[12], list):
            sub_12 = cast(list[object], raw[12])
            if len(sub_12) > 0 and isinstance(sub_12[0], (int, float)):
                dt = datetime.fromtimestamp(int(sub_12[0]), tz=UTC)
                posted_date = dt.strftime("%Y-%m-%d")
                delta = (datetime.now(tz=UTC) - dt).days
                posted_days = max(0, delta)
                posted_on = relative_day_text(posted_days)

        # Concatenate About the Job, Responsibilities, and Qualifications
        def _extract_text_slot(slot: object) -> str:
            if isinstance(slot, list):
                s_list = cast(list[object], slot)
                if len(s_list) > 1 and s_list[1] is not None:
                    return str(s_list[1]).strip()
            return ""

        desc_parts: list[str] = []
        if len(raw) > 10 and (txt := _extract_text_slot(raw[10])):
            desc_parts.append(txt)
        if len(raw) > 3 and (txt := _extract_text_slot(raw[3])):
            desc_parts.append(txt)
        if len(raw) > 4 and (txt := _extract_text_slot(raw[4])):
            desc_parts.append(txt)

        full_desc = "\n\n".join(p for p in desc_parts if p)
        description = html_to_text(full_desc)

        url = f"https://www.google.com/about/careers/applications/jobs/results/{job_id}"

        return Job(
            id=f"{self.slug}:{job_id}",
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
