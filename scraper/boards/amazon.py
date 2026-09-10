"""Amazon careers scraper (www.amazon.jobs).

Amazon runs a custom job search portal powered by an internal Elasticsearch-backed
JSON API:

    GET https://www.amazon.jobs/en/search.json
    Parameters:
      offset, result_limit (max 100), sort=recent
      category[], country[], business_category[]

No authentication or session handshake required. The response returns:
    hits  → total matched live postings
    jobs  → list of job objects with full description, qualifications,
            posting dates, and normalized multi-location data

One config entry covers all Amazon corporate & subsidiary jobs (e.g. AWS, Kuiper,
Twitch, Zoox), or can optionally pin to a specific category/country:
    {"board": "amazon", "name": "Amazon"}
    {"board": "amazon", "name": "AWS", "business_category": "amazon-web-services"}
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import NotRequired, TypedDict, cast

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import relative_day_text
from scraper.models import Job
from scraper.text import html_to_text

API = "https://www.amazon.jobs/en/search.json"
PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 50  # ~5000 jobs (Amazon orders by recent)
MAX_PAGES_CAP = 100  # safety cap — up to 10,000 jobs (Elasticsearch max_result_window)
TIMEOUT = 30

log = logging.getLogger("scraper.amazon")


class RawAmazonJob(TypedDict):
    id_icims: NotRequired[str | int]
    id: NotRequired[str | int]
    title: NotRequired[str]
    company_name: NotRequired[str]
    job_path: NotRequired[str]
    location: NotRequired[str]
    normalized_location: NotRequired[str]
    locations: NotRequired[list[str]]
    posted_date: NotRequired[str]
    description: NotRequired[str]
    basic_qualifications: NotRequired[str]
    preferred_qualifications: NotRequired[str]
    business_category: NotRequired[str]
    job_category: NotRequired[str]


class AmazonResponse(TypedDict):
    hits: NotRequired[int]
    jobs: NotRequired[list[RawAmazonJob]]
    error: NotRequired[str | None]


def parse_amazon_date(raw_date: str) -> int | None:
    """Parse Amazon's 'Month Day, Year' (e.g. 'September  9, 2026') into days ago."""
    if not raw_date:
        return None
    cleaned = re.sub(r"\s+", " ", raw_date.strip())
    try:
        dt = datetime.strptime(cleaned, "%B %d, %Y").replace(tzinfo=UTC)
        delta = datetime.now(UTC) - dt
        return max(delta.days, 0)
    except ValueError:
        return None


class AmazonScraper(BaseScraper):
    source = "amazon"

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

        # Optional filters from company config
        base_params: list[tuple[str, str | int]] = [
            ("result_limit", PAGE_SIZE),
            ("sort", "recent"),
        ]
        if category := self.company.get("category"):
            base_params.append(("category[]", category))
        if country := self.company.get("country"):
            base_params.append(("country[]", country))
        if business := self.company.get("business_category"):
            base_params.append(("business_category[]", business))

        configured_pages = self.company.get("max_pages")
        max_pages = (
            min(int(configured_pages), MAX_PAGES_CAP) if configured_pages else DEFAULT_MAX_PAGES
        )

        jobs: list[Job] = []
        for page in range(max_pages):
            offset = page * PAGE_SIZE
            if offset >= 10000:
                # Amazon API enforces max_result_window = 10,000
                break

            params = [("offset", offset)] + base_params
            log.debug("%s: page=%d offset=%d", self.name, page, offset)

            resp = session.get(API, params=params, timeout=TIMEOUT)
            resp.raise_for_status()

            raw: object = resp.json()
            if not isinstance(raw, dict):
                log.warning("%s: unexpected response type %s", self.name, type(raw))
                break

            data = cast(AmazonResponse, raw)
            if err := data.get("error"):
                log.warning("%s: API returned error: %s", self.name, err)
                break

            hits = data.get("hits") or 0
            raw_jobs = data.get("jobs") or []
            log.debug(
                "%s: page=%d returned %d jobs (total hits=%d)",
                self.name,
                page,
                len(raw_jobs),
                hits,
            )

            for j in raw_jobs:
                jobs.append(self._to_job(j))

            if (
                not raw_jobs
                or (hits and offset + len(raw_jobs) >= hits)
                or (not hits and len(raw_jobs) < PAGE_SIZE)
            ):
                break

        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    def _to_job(self, raw: RawAmazonJob) -> Job:
        raw_id = raw.get("id_icims") or raw.get("id") or ""
        job_id = str(raw_id).strip()

        title = (raw.get("title") or "").strip()
        primary_loc = (raw.get("normalized_location") or raw.get("location") or "").strip()

        # Parse all locations from raw JSON list if present
        locations: list[str] = []
        for l_raw in raw.get("locations") or []:
            try:
                l_obj = json.loads(l_raw)
                nl = (l_obj.get("normalizedLocation") or l_obj.get("location") or "").strip()
                if nl and nl not in locations:
                    locations.append(nl)
            except (json.JSONDecodeError, TypeError):
                cleaned = l_raw.strip()
                if cleaned and cleaned not in locations:
                    locations.append(cleaned)

        if primary_loc and primary_loc not in locations:
            locations.insert(0, primary_loc)
        elif not primary_loc and locations:
            primary_loc = locations[0]

        # Build full URL
        job_path = (raw.get("job_path") or "").strip()
        if job_path.startswith("/"):
            url = f"https://www.amazon.jobs{job_path}"
        elif job_path:
            url = job_path
        else:
            url = f"https://www.amazon.jobs/en/jobs/{job_id}"

        # Combine description and qualifications
        desc_parts: list[str] = []
        if desc := (raw.get("description") or "").strip():
            desc_parts.append(desc)
        if basic := (raw.get("basic_qualifications") or "").strip():
            desc_parts.append(f"Basic Qualifications:\n{basic}")
        if pref := (raw.get("preferred_qualifications") or "").strip():
            desc_parts.append(f"Preferred Qualifications:\n{pref}")
        full_description = html_to_text("\n\n".join(desc_parts))

        posted_days = parse_amazon_date(raw.get("posted_date") or "")
        posted_on = relative_day_text(posted_days)

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
            description=full_description,
        )
