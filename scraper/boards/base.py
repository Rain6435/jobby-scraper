"""Base class for all job board scrapers.

To add a new board:
1. Create a new module in scraper/boards/ subclassing BaseScraper.
2. Implement fetch_jobs() returning a list of normalized Job objects.
3. Register the class in SCRAPERS in scraper/boards/__init__.py.
Companies in config.json select their scraper via the "board" field.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from scraper.config_types import CompanyConfig
from scraper.models import Job

log = logging.getLogger("scraper.boards.base")

DETAIL_FETCH_WORKERS = 16


def slugify(name: str) -> str:
    """Company name → stable slug for the Job.id prefix, e.g. "TD Bank" → "td-bank"."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def make_session() -> requests.Session:
    """requests.Session with retry/backoff for transient failures.

    Career-page hosts (Workday tenants especially) intermittently 429 under
    concurrent load; retrying with backoff here means a single rate-limited
    request no longer takes down that company's whole scrape for the run.

    pool_maxsize matches DETAIL_FETCH_WORKERS: the default HTTPAdapter pool
    (10) is smaller than the thread pool that boards with a per-job detail
    call (workday, rippling, bamboohr, smartrecruiters) run their concurrent
    fetches through via _fetch_details_concurrent — undersized, a request
    beyond the pool's 10 connections gets its connection discarded instead of
    reused (confirmed via urllib3's own "Connection pool is full, discarding
    connection" warning on a 4000+-posting company), which doesn't break
    anything but defeats connection reuse for every fetch past the 10th.
    """
    retry = Retry(
        total=4,
        backoff_factor=1.5,  # 1.5s, 3s, 6s, 12s between attempts
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=DETAIL_FETCH_WORKERS)
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

    def _fetch_with_cache(
        self,
        job_id: str,
        fields: tuple[str, ...],
        fetch_fn: Callable[[], tuple[object, ...]],
    ) -> tuple[object, ...]:
        """Cached-or-fetch branch shared by every detail-fetch board: pull
        `fields` off the previous run's cached Job if job_id was already
        known, otherwise call fetch_fn() — which owns its own exception
        handling and fallback values, untouched by this helper."""
        cached = self._cached_detail(job_id)
        if cached is not None:
            return tuple(getattr(cached, f) for f in fields)
        return fetch_fn()

    def _fetch_details_concurrent(
        self,
        job_ids: list[str],
        fields: tuple[str, ...],
        fetch_fn: Callable[[str], tuple[object, ...]],
        *,
        max_workers: int = DETAIL_FETCH_WORKERS,
    ) -> dict[str, tuple[object, ...]]:
        """Cached-or-fetch, run concurrently, for boards with one detail HTTP
        call per listed job (workday, rippling, bamboohr, smartrecruiters).

        For each id in job_ids: reuse the previous run's cached `fields` (via
        _cached_detail) when known, otherwise call fetch_fn(job_id) — which
        owns its own exception handling and fallback values, untouched by
        this helper, same contract as _fetch_with_cache. Only the actual
        network calls (the cache misses) run in a thread pool; cache hits are
        resolved inline since they do no I/O. fetch_fn is called with only
        job_id — callers close over whatever else they need (session,
        subdomain, etc.) since each board's detail call takes different
        extra arguments.

        Returns a dict keyed by job_id so callers can look up results after
        the list-order loop that built job_ids — needed because
        as_completed() yields whenever a request finishes, not in submission
        order, and the caller still needs each result matched to its job.
        """
        results: dict[str, tuple[object, ...]] = {}
        to_fetch: list[str] = []
        for job_id in job_ids:
            cached = self._cached_detail(job_id)
            if cached is not None:
                results[job_id] = tuple(getattr(cached, f) for f in fields)
            else:
                to_fetch.append(job_id)

        if not to_fetch:
            return results

        log.debug(
            "%s: fetching %d/%d details concurrently (max_workers=%d)",
            self.name,
            len(to_fetch),
            len(job_ids),
            max_workers,
        )
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(fetch_fn, job_id): job_id for job_id in to_fetch}
            for future in as_completed(futures):
                job_id = futures[future]
                results[job_id] = future.result()
        return results

    @abstractmethod
    def fetch_jobs(self) -> list[Job]:
        """Fetch all current postings for this company, normalized to Job."""
        raise NotImplementedError
