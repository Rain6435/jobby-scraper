"""Electronic Arts (EA) careers scraper (jobs.ea.com).

Electronic Arts runs a custom branded career portal across jobs.ea.com:

    Search:  GET https://jobs.ea.com/en_US/careers/SearchJobs
    Details: GET https://jobs.ea.com/en_US/careers/JobDetail/{title-slug}/{job_id}

No authentication required. The search page renders server-side articles with
title, numeric role ID, standardized location, worker type, and department.

Job descriptions are fetched on demand via JobDetail and cached across runs
using BaseScraper._fetch_details_concurrent.

Config entry:
    {"board": "ea", "name": "Electronic Arts"}
    {"board": "ea", "name": "Electronic Arts", "search": "engineer"}
"""

from __future__ import annotations

import logging
import re
from typing import TypedDict, cast

import requests

from scraper.boards.base import BaseScraper, make_session
from scraper.models import Job
from scraper.text import html_to_text

SEARCH_URL = "https://jobs.ea.com/en_US/careers/SearchJobs"
PAGE_SIZE = 20
DEFAULT_MAX_PAGES = 30  # ~600 jobs (EA has ~326 live roles globally)
MAX_PAGES_CAP = 100  # safety cap
TIMEOUT = 30

log = logging.getLogger("scraper.ea")


class RawEaJob(TypedDict):
    id: str
    title: str
    location: str
    url: str
    department: str
    worker_type: str


class EaScraper(BaseScraper):
    source = "ea"

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

        base_params: list[tuple[str, str | int]] = [("jobRecordsPerPage", PAGE_SIZE)]
        if search := self.company.get("search"):
            base_params.append(("search", search))

        cfg_max = self.company.get("max_pages")
        if isinstance(cfg_max, int) and cfg_max > 0:
            max_pages = min(cfg_max, MAX_PAGES_CAP)
        else:
            max_pages = DEFAULT_MAX_PAGES

        jobs_by_id: dict[str, RawEaJob] = {}
        for page in range(max_pages):
            offset = page * PAGE_SIZE
            params = [("jobOffset", offset)] + base_params

            log.debug("%s: page=%d offset=%d", self.name, page, offset)
            resp = session.get(SEARCH_URL, params=params, timeout=TIMEOUT)
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

            for job in raw_jobs:
                jid = job["id"]
                if jid:
                    jobs_by_id[jid] = job

            if len(raw_jobs) < PAGE_SIZE or (total_count and offset + len(raw_jobs) >= total_count):
                break

        should_fetch_details = self.company.get("fetch_details", False)
        job_ids = [f"{self.slug}:{jid}" for jid in jobs_by_id]
        details: dict[str, tuple[object, ...]] = {}

        if should_fetch_details and job_ids:
            details = self._fetch_details_concurrent(
                job_ids,
                ("description",),
                lambda full_id: self._fetch_detail(
                    session, jobs_by_id[full_id.split(":", 1)[1]]["url"]
                ),
                max_workers=8,
            )

        jobs: list[Job] = []
        for jid, raw in jobs_by_id.items():
            full_id = f"{self.slug}:{jid}"
            desc = ""
            if full_id in details:
                desc = cast(str, details[full_id][0])

            jobs.append(self._to_job(raw, desc))

        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    def _parse_page(self, html_content: str) -> tuple[list[RawEaJob], int]:
        """Extract job listings and total count from SearchJobs HTML."""
        total_count = 0
        m_total = re.search(r"aria-label=[\'\"]([0-9,]+)\s+results[\'\"]", html_content)
        if not m_total:
            m_total = re.search(r"of\s+([0-9,]+)\s*<", html_content)
        if m_total:
            total_count = int(m_total.group(1).replace(",", ""))

        articles = re.findall(
            r"<article class=\"article article--result[^\"]*\"[^>]*>(.*?)</article>",
            html_content,
            re.DOTALL,
        )

        jobs: list[RawEaJob] = []
        for art in articles:
            m_url = re.search(
                r"href=\"(https://jobs\.ea\.com/en_US/careers/JobDetail/[^\"]+/(\d+))\"", art
            )
            m_title = re.search(r"<a class=\"link link_result\"[^>]*>\s*([^<]+)\s*</a>", art)
            m_loc = re.search(r"<span class=\"list-item-location\">([^<]+)</span>", art)
            m_type = re.search(r"<span class=\"list-item-workerType\">([^<]+)</span>", art)
            m_dept = re.search(r"<span class=\"list-item-department\">([^<]+)</span>", art)

            if not m_url:
                continue

            url = m_url.group(1)
            jid = m_url.group(2)
            title = m_title.group(1).strip() if m_title else ""
            loc = m_loc.group(1).strip() if m_loc else "Remote"
            wtype = m_type.group(1).strip() if m_type else ""
            dept = m_dept.group(1).strip() if m_dept else ""

            jobs.append(
                RawEaJob(
                    id=jid,
                    title=title,
                    location=loc,
                    url=url,
                    department=dept,
                    worker_type=wtype,
                )
            )

        return jobs, total_count

    def _fetch_detail(self, session: requests.Session, job_url: str) -> tuple[str]:
        """Fetch job description from JobDetail page."""
        try:
            resp = session.get(job_url, timeout=TIMEOUT)
            resp.raise_for_status()
            fields = re.findall(
                r"<div class=\"article__content__view__field__value\">(.*?)</div>",
                resp.text,
                re.DOTALL,
            )
            clean_fields = [html_to_text(f) for f in fields]
            longest = max(clean_fields, key=len) if clean_fields else ""
            return (longest,)
        except Exception as e:
            log.warning("%s: failed to fetch details from %s: %s", self.name, job_url, e)
            return ("",)

    def _to_job(self, raw: RawEaJob, description: str) -> Job:
        loc = raw["location"]
        return Job(
            id=f"{self.slug}:{raw['id']}",
            company=self.name,
            title=raw["title"],
            location=loc,
            locations=[loc] if loc else [],
            url=raw["url"],
            posted_on="",
            source=self.source,
            description=description,
            company_blurb=self.company.get("blurb", ""),
        )
