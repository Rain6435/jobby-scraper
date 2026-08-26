"""USAJobs (US federal government) job board scraper.

Unlike every other board, this is not a per-employer integration — one
config entry covers the whole nationwide search API, and Job.company is set
per-result from the API's own OrganizationName rather than from config:
    GET https://data.usajobs.gov/api/search
Requires two credentials with no functional equivalent elsewhere in this
project (every other board is keyless): USAJOBS_API_KEY and
USAJOBS_USER_AGENT (the email registered at developer.usajobs.gov, free and
instant, sent as the User-Agent header — the API rejects requests without
both). Missing either is treated as a board-scrape failure, not a hard
error: fetch_jobs() logs a warning and returns [], matching every other
board's best-effort philosophy elsewhere in this pipeline. Config:
{"board": "usajobs", "name": "..."}.

Response: {"SearchResult": {"SearchResultItems": [...]}}, each item has
MatchedObjectId and a MatchedObjectDescriptor with PositionTitle,
OrganizationName, PositionLocation[], PositionURI, PublicationStartDate
("2026-06-01T00:00:00.0000" — ISO-8601 with fractional seconds, no
timezone offset, parseable by the same posted_days_from_iso other boards
reuse), and description text under UserArea.Details.JobSummary or
QualificationSummary.
"""

from __future__ import annotations

import logging
import os

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import posted_days_from_iso, relative_day_text
from scraper.models import Job
from scraper.text import html_to_text

API = "https://data.usajobs.gov/api/search"
RESULTS_PER_PAGE = 500
MAX_PAGES = 10  # safety cap against runaway pagination, ~5000 jobs
TIMEOUT = 30

log = logging.getLogger("scraper.usajobs")


class UsajobsScraper(BaseScraper):
    source = "usajobs"

    def fetch_jobs(self) -> list[Job]:
        api_key = os.environ.get("USAJOBS_API_KEY")
        user_agent = os.environ.get("USAJOBS_USER_AGENT")
        if not api_key or not user_agent:
            log.warning(
                "%s: USAJOBS_API_KEY/USAJOBS_USER_AGENT not set — skipping", self.name
            )
            return []

        session = make_session()
        session.headers.update({
            "Host": "data.usajobs.gov",
            "User-Agent": user_agent,
            "Authorization-Key": api_key,
            "Accept": "application/json",
        })

        jobs: list[Job] = []
        for page in range(1, MAX_PAGES + 1):
            log.debug("%s: fetching page=%d", self.name, page)
            resp = session.get(
                API,
                params={"ResultsPerPage": RESULTS_PER_PAGE, "Page": page},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            items = resp.json().get("SearchResult", {}).get("SearchResultItems", [])
            log.debug("%s: page=%d returned %d items", self.name, page, len(items))
            for item in items:
                jobs.append(self._to_job(item))
            if len(items) < RESULTS_PER_PAGE:
                break

        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    def _to_job(self, item: dict) -> Job:
        descriptor = item.get("MatchedObjectDescriptor", {})
        locations = self._locations(descriptor)
        posted_days = posted_days_from_iso(descriptor.get("PublicationStartDate", ""))
        company = descriptor.get("OrganizationName") or descriptor.get("DepartmentName") or self.name
        return Job(
            id=f"{self.slug}:{item.get('MatchedObjectId', '')}",
            company=company,
            title=(descriptor.get("PositionTitle") or "").strip(),
            location=locations[0] if locations else "",
            locations=locations,
            url=descriptor.get("PositionURI", ""),
            posted_on=relative_day_text(posted_days),
            posted_days=posted_days,
            source=self.source,
            description=self._description(descriptor),
        )

    @staticmethod
    def _locations(descriptor: dict) -> list[str]:
        locs = [loc.get("LocationName") for loc in descriptor.get("PositionLocation") or []]
        locs = [loc for loc in locs if loc]
        if locs:
            return locs
        display = descriptor.get("PositionLocationDisplay")
        return [display] if display else []

    @staticmethod
    def _description(descriptor: dict) -> str:
        summary = descriptor.get("UserArea", {}).get("Details", {}).get("JobSummary", "")
        text = summary or descriptor.get("QualificationSummary", "")
        return html_to_text(text)
