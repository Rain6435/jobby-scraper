"""iCIMS candidate portal scraper.

Parses public iCIMS candidate search portals:
    GET https://<tenant>.icims.com/jobs/search?pr=<page>&in_iframe=1
Config:
{"board": "icims", "tenant": "<subdomain_or_host>", "domain": "<custom_domain>"}
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import cast
from urllib.parse import urljoin

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import posted_days_from_iso, relative_day_text
from scraper.config_types import IcimsConfig
from scraper.models import Job

TIMEOUT = 30
MAX_PAGES = 50

log = logging.getLogger("scraper.icims")


def parse_icims_date(date_str: str) -> int | None:
    """Parse iCIMS date format (e.g. '3/1/2026', '2026-03-01', '3 days ago')."""
    if not date_str:
        return None
    date_str = date_str.strip()

    # Try ISO
    days = posted_days_from_iso(date_str)
    if days is not None:
        return days

    # Try M/D/YYYY
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(date_str, fmt).replace(tzinfo=UTC)
            now = datetime.now(UTC)
            return max(0, (now - dt).days)
        except ValueError:
            pass

    # Try relative "N days ago" / "N hours ago"
    m = re.search(r"(\d+)\s+day", date_str, re.IGNORECASE)
    if m:
        return int(m.group(1))
    if re.search(r"\bhour|today|just posted\b", date_str, re.IGNORECASE):
        return 0

    return None


class _ParsedIcimsJob:
    def __init__(self) -> None:
        self.job_id: str = ""
        self.title: str = ""
        self.url: str = ""
        self.location: str = ""
        self.posted_date: str = ""


class _IcimsHTMLParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.jobs: list[_ParsedIcimsJob] = []
        self.current_job: _ParsedIcimsJob | None = None
        self.in_anchor = False
        self.current_tag_header = ""
        self.in_header_tag = False
        self.in_header_subtag = False
        self.buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = {k: v or "" for k, v in attrs}
        classes = attr_dict.get("class", "")
        href = attr_dict.get("href", "")

        if "iCIMS_Anchor" in classes or ("/jobs/" in href and "/job" in href):
            # Only treat as job link if it's not a login / general link
            m = re.search(r"/jobs/(\d+)/", href)
            if m:
                self.current_job = _ParsedIcimsJob()
                full_url = urljoin(self.base_url, href)
                self.current_job.url = full_url
                self.current_job.job_id = m.group(1)
                self.in_anchor = True
                self.buffer = []

        elif self.in_anchor and tag in ("h1", "h2", "h3", "h4", "span", "div"):
            self.buffer = []

        elif "iCIMS_JobHeaderTag" in classes:
            self.in_header_tag = True
            self.buffer = []

        elif "iCIMS_JobHeaderSubTag" in classes:
            self.in_header_subtag = True
            self.buffer = []

    def handle_endtag(self, tag: str) -> None:
        text = " ".join(self.buffer).strip()
        if self.in_anchor and self.current_job:
            if tag in ("h1", "h2", "h3", "h4", "span", "a"):
                if text and text.lower() != "title":
                    self.current_job.title = text
            if tag == "a":
                self.in_anchor = False
                if self.current_job.job_id and self.current_job.title:
                    self.jobs.append(self.current_job)

        elif self.in_header_tag:
            self.current_tag_header = text.lower()
            self.in_header_tag = False

        elif self.in_header_subtag:
            if self.jobs:
                target_job = self.jobs[-1]
                if "location" in self.current_tag_header and not target_job.location:
                    target_job.location = text
                elif "date" in self.current_tag_header and not target_job.posted_date:
                    target_job.posted_date = text
            self.in_header_subtag = False

    def handle_data(self, data: str) -> None:
        cleaned = data.strip()
        if cleaned:
            self.buffer.append(cleaned)


class IcimsScraper(BaseScraper):
    source = "icims"

    def fetch_jobs(self) -> list[Job]:
        cfg: IcimsConfig = cast(IcimsConfig, self.company)
        tenant = cfg["tenant"]
        custom_domain = cfg.get("domain")

        if custom_domain:
            domain = custom_domain
        elif "." in tenant:
            domain = tenant
        else:
            domain = f"{tenant}.icims.com"

        session = make_session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

        jobs: list[Job] = []
        seen_job_ids: set[str] = set()
        base_url = f"https://{domain}/jobs/search"

        for page in range(MAX_PAGES):
            params = {
                "pr": str(page),
                "in_iframe": "1",
            }

            log.debug("%s: fetching page %d from %s", self.name, page, base_url)
            resp = session.get(base_url, params=params, timeout=TIMEOUT)
            resp.raise_for_status()

            parser = _IcimsHTMLParser(base_url)
            parser.feed(resp.text)

            new_jobs_on_page = 0
            for pj in parser.jobs:
                job_id = pj.job_id or pj.url.split("/")[-1]
                if not job_id or job_id in seen_job_ids:
                    continue

                seen_job_ids.add(job_id)
                new_jobs_on_page += 1

                title = pj.title or "Job Opening"
                location = pj.location
                posted_days = parse_icims_date(pj.posted_date)

                jobs.append(
                    Job(
                        id=f"{self.slug}:{job_id}",
                        company=self.name,
                        title=title,
                        location=location,
                        locations=[location] if location else [],
                        url=pj.url,
                        posted_on=relative_day_text(posted_days),
                        posted_days=posted_days,
                        source=self.source,
                        description="",
                    )
                )

            if new_jobs_on_page == 0:
                break

        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs
