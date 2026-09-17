"""Bloomberg / Avature careers scraper (bloomberg.avature.net).

Bloomberg operates its global careers portal on the Avature candidate platform
at bloomberg.avature.net. Other quantitative and technology firms (such as Two Sigma)
also leverage Avature with custom search endpoints.

Each listing in the HTML results has:
    - id (numeric ID at the end of the JobDetail URL, e.g. "22127")
    - title (e.g. "Senior Software Engineer - BQL Reliability Engineering")
    - location (e.g. "London, United Kingdom" or "New York, New York, United States of America")
    - url (direct link to the JobDetail page)

Config options:
    {"board": "bloomberg", "name": "Bloomberg"}
    {"board": "bloomberg", "name": "Two Sigma", "url": "https://careers.twosigma.com/careers/OpenRoles"}
"""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests

from scraper.boards.base import BaseScraper, make_session
from scraper.config_types import BloombergConfig
from scraper.models import Job

TIMEOUT = 30
DEFAULT_URL = "https://bloomberg.avature.net/careers/SearchJobs"
DEFAULT_MAX_PAGES = 35

log = logging.getLogger("scraper.bloomberg")


class _ParsedAvatureJob:
    def __init__(self) -> None:
        self.job_id: str = ""
        self.title: str = ""
        self.url: str = ""
        self.location: str = ""


class _AvatureHTMLParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url: str = base_url
        self.jobs: list[_ParsedAvatureJob] = []
        self.current_job: _ParsedAvatureJob | None = None
        self.in_article: bool = False
        self.in_title: bool = False
        self.in_location: bool = False
        self.text_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = {k: v or "" for k, v in attrs}
        classes = attr_dict.get("class", "").split()
        if tag == "article" and "article--result" in classes:
            self.in_article = True
            self.current_job = _ParsedAvatureJob()
        elif self.in_article:
            if tag == "a" and "link" in classes:
                href = attr_dict.get("href", "")
                m = re.search(r"/(\d+)(?:[/?#]|$)", href)
                if m and self.current_job:
                    self.current_job.url = urljoin(self.base_url, href)
                    self.current_job.job_id = m.group(1)
                    self.in_title = True
                    self.text_buf = []
            elif "list-item-location" in classes or (
                "paragraph_inner-span" in classes
                and self.current_job
                and not self.current_job.location
            ):
                self.in_location = True
                self.text_buf = []

    def handle_data(self, data: str) -> None:
        if self.in_title or self.in_location:
            self.text_buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        text = " ".join("".join(self.text_buf).split())
        if tag == "a" and self.in_title:
            if self.current_job:
                self.current_job.title = text
            self.in_title = False
            self.text_buf = []
        elif self.in_location and (tag == "span" or tag == "div"):
            if self.current_job and not self.current_job.location and text:
                self.current_job.location = text
            self.in_location = False
            self.text_buf = []
        elif tag == "article" and self.in_article:
            if self.current_job and self.current_job.job_id and self.current_job.title:
                self.jobs.append(self.current_job)
            self.in_article = False
            self.current_job = None


class BloombergScraper(BaseScraper):
    source = "bloomberg"

    def __init__(
        self,
        company: BloombergConfig,
        settings: dict[str, object] | None = None,
        previous: dict[str, Job] | None = None,
    ) -> None:
        super().__init__(company, settings, previous)
        self._bloomberg_config: BloombergConfig = company

    def fetch_jobs(self) -> list[Job]:
        base_search_url = self._bloomberg_config.get("url") or DEFAULT_URL
        max_pages = self._bloomberg_config.get("max_pages") or DEFAULT_MAX_PAGES
        query = self._bloomberg_config.get("query")
        location_filter = self._bloomberg_config.get("location")

        parsed = urlparse(base_search_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

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

        jobs: list[Job] = []
        seen_ids: set[str] = set()
        offset = 0

        for _ in range(max_pages):
            params: dict[str, str | int] = {"jobOffset": offset}
            if query and "?" not in base_search_url:
                req_url = f"{base_search_url.rstrip('/')}/{query}"
            else:
                req_url = base_search_url

            try:
                resp = session.get(req_url, params=params, timeout=TIMEOUT)
                resp.raise_for_status()
            except requests.RequestException as e:
                log.warning("Failed to fetch jobs from %s at offset %d: %s", req_url, offset, e)
                break

            parser = _AvatureHTMLParser(base_url)
            parser.feed(resp.text)

            if not parser.jobs:
                break

            page_new_jobs = 0
            for parsed_job in parser.jobs:
                if parsed_job.job_id in seen_ids:
                    continue
                seen_ids.add(parsed_job.job_id)
                page_new_jobs += 1

                loc = parsed_job.location
                if location_filter and location_filter.lower() not in loc.lower():
                    continue

                locations = [loc] if loc else []
                jobs.append(
                    Job(
                        id=f"{self.slug}:{parsed_job.job_id}",
                        company=self.name,
                        title=parsed_job.title,
                        location=loc,
                        locations=locations,
                        url=parsed_job.url,
                        posted_on="",
                        source=self.source,
                        description="",
                    )
                )

            if page_new_jobs == 0:
                break

            offset += len(parser.jobs)

        log.info("Scraped %d jobs for %s", len(jobs), self.name)
        return jobs
