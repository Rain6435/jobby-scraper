"""Base class for all job board scrapers.

To add a new board:
1. Create a new module in scraper/boards/ subclassing BaseScraper.
2. Implement fetch_jobs() returning a list of normalized Job objects.
3. Register the class in SCRAPERS in scraper/boards/__init__.py.
Companies in config.json select their scraper via the "board" field.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from scraper.config_types import CompanyConfig
from scraper.models import Job


def slugify(name: str) -> str:
    """Company name → stable slug for the Job.id prefix, e.g. "TD Bank" → "td-bank"."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def make_session() -> requests.Session:
    """requests.Session with retry/backoff for transient failures.

    Career-page hosts (Workday tenants especially) intermittently 429 under
    concurrent load; retrying with backoff here means a single rate-limited
    request no longer takes down that company's whole scrape for the run.
    """
    retry = Retry(
        total=4,
        backoff_factor=1.5,  # 1.5s, 3s, 6s, 12s between attempts
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class BaseScraper(ABC):
    source: str = "base"

    def __init__(
        self,
        company: CompanyConfig,
        settings: dict[str, object] | None = None,
        previous: dict[str, Job] | None = None,
    ):
        """company: one entry from config.json's "companies" list.

        settings: board-agnostic options from config.json. Currently unused —
            reserved for future options shared across all boards.

        previous: the prior run's full snapshot, keyed by Job.id (main.py
            already loads this before scraping starts). Boards that make a
            per-job detail HTTP call (workday, rippling, bamboohr,
            smartrecruiters) use this via _cached_detail() to skip that call
            for postings already known from last time, reusing the cached
            detail-only fields (description, etc.) instead — the list call
            and new/removed-job detection both still run every time
            regardless. Defaults to {} so a caller that doesn't pass this
            (e.g. existing tests) gets today's always-fetch behavior.
        """
        self.company = company
        self.name = company["name"]
        self.slug = slugify(self.name)
        self.settings = settings or {}
        self.previous = previous or {}

    def _cached_detail(self, job_id: str) -> Job | None:
        """The previous run's Job for this id, if any — lets a board reuse
        detail-only fields (description, etc.) instead of re-fetching them."""
        return self.previous.get(job_id)

    @abstractmethod
    def fetch_jobs(self) -> list[Job]:
        """Fetch all current postings for this company, normalized to Job."""
        raise NotImplementedError
