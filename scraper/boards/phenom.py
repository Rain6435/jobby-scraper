"""Phenom People career portal scraper.

Phenom People powers talent portals for major global and Canadian enterprises
(e.g., OpenText, Bell Canada, Air Canada, Cisco). Data is rendered server-side
into a JavaScript object `phApp.ddo`:

    Search endpoint: GET https://{domain}/{locale}/search-results?from={offset}&s=1
    Detail endpoint: GET https://{domain}/{locale}/job/{job_id}

Config entry:
    {"board": "phenom", "name": "OpenText", "url": "https://careers.opentext.com/us/en"}
    {"board": "phenom", "name": "Bell Canada", "url": "https://jobs.bell.ca/ca/en"}
    {"board": "phenom", "name": "Air Canada", "url": "https://careers.aircanada.com/ca/en"}
    {"board": "phenom", "name": "Cisco", "url": "https://careers.cisco.com/global/en", "location": "Canada"}
"""

from __future__ import annotations

import json
import logging
import math
import re
from concurrent.futures import ThreadPoolExecutor
from typing import NotRequired, TypedDict, cast

from requests.exceptions import RequestException

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import posted_days_from_iso, relative_day_text
from scraper.config_types import PhenomConfig
from scraper.models import Job
from scraper.text import html_to_text

TIMEOUT = 15
PAGE_SIZE = 10
DEFAULT_MAX_PAGES = 50
PAGE_WORKERS = 8
DETAIL_WORKERS = 8

log = logging.getLogger("scraper.phenom")

DDO_PATTERN = re.compile(
    r"phApp\.ddo\s*=\s*(\{.*?\});\s*(?:phApp|window|<\/script>)",
    re.DOTALL,
)


class PhenomRawJob(TypedDict):
    jobId: NotRequired[str | int]
    reqId: NotRequired[str | int]
    jobSeqNo: NotRequired[str]
    title: NotRequired[str]
    location: NotRequired[str]
    multi_location: NotRequired[list[str]]
    city: NotRequired[str]
    state: NotRequired[str]
    country: NotRequired[str]
    category: NotRequired[str]
    multi_category: NotRequired[list[str]]
    postedDate: NotRequired[str]
    dateCreated: NotRequired[str]
    descriptionTeaser: NotRequired[str]


class PhenomJobDetail(TypedDict):
    description: NotRequired[str]


class PhenomJobDetailData(TypedDict):
    job: NotRequired[PhenomJobDetail]


class PhenomJobDetailWrapper(TypedDict):
    data: NotRequired[PhenomJobDetailData]


class PhenomRefineData(TypedDict):
    jobs: NotRequired[list[PhenomRawJob]]


class PhenomRefineSearch(TypedDict):
    totalHits: NotRequired[int | str]
    data: NotRequired[PhenomRefineData]


class PhenomDDO(TypedDict):
    eagerLoadRefineSearch: NotRequired[PhenomRefineSearch]
    jobDetail: NotRequired[PhenomJobDetailWrapper]


def extract_ddo(html: str) -> PhenomDDO | None:
    """Extract and parse the phApp.ddo JSON payload embedded in Phenom HTML."""
    match = DDO_PATTERN.search(html)
    if not match:
        return None
    try:
        raw: object = json.loads(match.group(1))
        if isinstance(raw, dict):
            return cast(PhenomDDO, raw)
        return None
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("Failed to decode phApp.ddo JSON: %s", exc)
        return None


def normalize_urls(configured_url: str) -> tuple[str, str]:
    """Return (portal_url, search_url) from a configured Phenom URL."""
    base = configured_url.strip().rstrip("/")
    if base.endswith("/search-results"):
        portal_url = base[: -len("/search-results")]
        search_url = base
    else:
        portal_url = base
        search_url = f"{base}/search-results"
    return portal_url, search_url


class PhenomScraper(BaseScraper):
    source = "phenom"

    def __init__(self, company: PhenomConfig) -> None:
        super().__init__(company)
        self.session = make_session()

    def _fetch_page(self, search_url: str, offset: int) -> tuple[int, list[PhenomRawJob]]:
        """Fetch a single page of results and return (totalHits, raw_jobs)."""
        url = f"{search_url}?from={offset}&s=1"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        try:
            resp = self.session.get(url, headers=headers, timeout=TIMEOUT)
            resp.raise_for_status()
            ddo = extract_ddo(resp.text)
            if not ddo:
                log.warning("%s: no phApp.ddo found at offset=%d", self.name, offset)
                return 0, []
            refine = ddo.get("eagerLoadRefineSearch") or {}
            total_hits = int(refine.get("totalHits") or 0)
            raw_jobs = (refine.get("data") or {}).get("jobs") or []
            return total_hits, raw_jobs
        except RequestException as exc:
            log.warning("%s: error fetching page offset=%d: %s", self.name, offset, exc)
            return 0, []

    def _fetch_detail_description(self, portal_url: str, job_id: str, fallback: str) -> str:
        """Fetch the full job description from the individual job detail page."""
        url = f"{portal_url}/job/{job_id}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        try:
            resp = self.session.get(url, headers=headers, timeout=TIMEOUT)
            resp.raise_for_status()
            ddo = extract_ddo(resp.text)
            if not ddo:
                return fallback
            job_detail = ddo.get("jobDetail") or {}
            job_data = job_detail.get("data") or {}
            job_obj = job_data.get("job") or {}
            desc_html = job_obj.get("description") or ""
            if desc_html:
                return html_to_text(desc_html)
            return fallback
        except RequestException as exc:
            log.debug("%s: error fetching detail for %s: %s", self.name, job_id, exc)
            return fallback

    def fetch_jobs(self) -> list[Job]:
        company: PhenomConfig = cast(PhenomConfig, self.company)
        raw_url = company.get("url", "")
        if not raw_url:
            log.warning("%s: missing 'url' in configuration", self.name)
            return []

        portal_url, search_url = normalize_urls(raw_url)
        max_pages = company.get("max_pages", DEFAULT_MAX_PAGES)
        fetch_details = company.get("fetch_details", False)

        loc_filter = company.get("location", "").strip().lower()
        kw_filter = company.get("keyword", "").strip().lower()
        cat_filter = company.get("category", "").strip().lower()

        self.session = make_session()

        # 1. Fetch initial page to discover totalHits and first 10 jobs
        total_hits, first_jobs = self._fetch_page(search_url, 0)
        raw_postings: list[PhenomRawJob] = list(first_jobs)

        # 2. Concurrently fetch remaining pages if totalHits > PAGE_SIZE
        if total_hits > PAGE_SIZE and max_pages > 1:
            total_pages = min(math.ceil(total_hits / PAGE_SIZE), max_pages)
            offsets = [p * PAGE_SIZE for p in range(1, total_pages)]
            log.debug(
                "%s: fetching %d pages for %d total hits", self.name, len(offsets), total_hits
            )

            with ThreadPoolExecutor(max_workers=PAGE_WORKERS) as pool:
                futures = [pool.submit(self._fetch_page, search_url, off) for off in offsets]
                for f in futures:
                    _, page_jobs = f.result()
                    raw_postings.extend(page_jobs)

        # 3. Filter and normalize postings
        jobs: list[Job] = []
        slug = self.slug

        for item in raw_postings:
            title = str(item.get("title") or "").strip()
            if not title:
                continue

            # Identify unique ID
            raw_id = item.get("jobId") or item.get("reqId") or item.get("jobSeqNo")
            if not raw_id:
                continue
            stable_id = str(raw_id).strip()

            # Location handling
            primary_loc = str(item.get("location") or "").strip()
            multi_loc = item.get("multi_location") or []
            locations = [str(loc).strip() for loc in multi_loc if str(loc).strip()]
            if not locations and primary_loc:
                locations = [primary_loc]
            elif not primary_loc and locations:
                primary_loc = locations[0]

            country = str(item.get("country") or "").strip()
            city = str(item.get("city") or "").strip()
            state = str(item.get("state") or "").strip()

            # Filtering
            if loc_filter:
                combined_loc = " ".join([primary_loc, country, city, state] + locations).lower()
                if loc_filter not in combined_loc:
                    continue

            teaser = str(item.get("descriptionTeaser") or "").strip()
            if kw_filter:
                combined_kw = f"{title} {teaser}".lower()
                if kw_filter not in combined_kw:
                    continue

            category = str(item.get("category") or "").strip()
            multi_cat = item.get("multi_category") or []
            if cat_filter:
                combined_cat = " ".join([category] + [str(c) for c in multi_cat]).lower()
                if cat_filter not in combined_cat:
                    continue

            # Posting dates
            posted_date_str = str(item.get("postedDate") or item.get("dateCreated") or "").strip()
            posted_days = posted_days_from_iso(posted_date_str) if posted_date_str else None
            posted_on = relative_day_text(posted_days) if posted_days is not None else ""
            posted_date = posted_date_str[:10] if len(posted_date_str) >= 10 else None

            job_url = f"{portal_url}/job/{stable_id}"
            job_unique_id = f"{slug}:{stable_id}"

            jobs.append(
                Job(
                    id=job_unique_id,
                    company=self.name,
                    title=title,
                    location=primary_loc,
                    locations=locations,
                    url=job_url,
                    posted_on=posted_on,
                    posted_days=posted_days,
                    posted_date=posted_date,
                    source=self.source,
                    description=teaser,
                )
            )

        # 4. Optional detail fetch if configured
        if fetch_details and jobs:
            log.debug("%s: fetching full details for %d jobs", self.name, len(jobs))
            job_ids = [j.id for j in jobs]
            job_map = {j.id: j for j in jobs}

            detail_results = self._fetch_details_concurrent(
                job_ids,
                ("description",),
                lambda jid: (
                    self._fetch_detail_description(
                        portal_url,
                        jid.split(":", 1)[1],
                        fallback=job_map[jid].description,
                    ),
                ),
                max_workers=DETAIL_WORKERS,
            )

            for j in jobs:
                if j.id in detail_results:
                    (full_desc,) = detail_results[j.id]
                    if full_desc:
                        j.description = str(full_desc)

        log.info("%s: scraped %d jobs (total reported: %d)", self.name, len(jobs), total_hits)
        return jobs
