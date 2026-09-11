"""Jibe enterprise career portal scraper (e.g. GitHub, PepsiCo, Costco, FedEx).

Jibe (by iCIMS) powers candidate search portals for enterprise employers:
    Search endpoint: GET {base_url}/api/jobs?page={page}&limit={limit}

Authentication: None. Returns JSON with `totalCount` and `jobs`.
Each job item contains full HTML description, locations, requisition ID,
canonical URL, and creation timestamp.

Config options:
    {"board": "jibe", "name": "GitHub", "tenant": "githubinc"}
    {"board": "jibe", "name": "GitHub", "url": "https://www.github.careers"}
    {"board": "jibe", "name": "PepsiCo", "tenant": "pepsico"}
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import NotRequired, TypedDict, cast

from requests.exceptions import RequestException

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import relative_day_text
from scraper.config_types import JibeConfig
from scraper.models import Job
from scraper.text import html_to_text

TIMEOUT = 25
DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 50

log = logging.getLogger("scraper.jibe")


class JibeAdditionalLocation(TypedDict):
    location_name: NotRequired[str | None]
    city: NotRequired[str | None]
    state: NotRequired[str | None]
    country: NotRequired[str | None]
    country_code: NotRequired[str | None]


class JibeMetaData(TypedDict):
    canonical_url: NotRequired[str | None]


class JibeJobData(TypedDict):
    slug: NotRequired[str | int | None]
    req_id: NotRequired[str | int | None]
    title: NotRequired[str | None]
    description: NotRequired[str | None]
    create_date: NotRequired[str | None]
    posted_date: NotRequired[str | None]
    location_name: NotRequired[str | None]
    full_location: NotRequired[str | None]
    city: NotRequired[str | None]
    state: NotRequired[str | None]
    country: NotRequired[str | None]
    country_code: NotRequired[str | None]
    multipleLocations: NotRequired[bool | None]
    additional_locations: NotRequired[list[JibeAdditionalLocation] | None]
    canonical_url: NotRequired[str | None]
    apply_url: NotRequired[str | None]
    meta_data: NotRequired[JibeMetaData | None]


class JibeJobItem(TypedDict):
    data: NotRequired[JibeJobData | None]


class JibeApiResponse(TypedDict):
    totalCount: NotRequired[int | None]
    jobs: NotRequired[list[JibeJobItem] | None]


def posted_days_from_jibe_date(date_str: str | None) -> int | None:
    """Calculate days ago from Jibe ISO-8601 date string, or None if unparseable."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    return max(0, (now - dt).days)


class JibeScraper(BaseScraper):
    source = "jibe"

    def __init__(
        self,
        company: JibeConfig,
        settings: dict[str, object] | None = None,
        previous: dict[str, Job] | None = None,
    ) -> None:
        super().__init__(company, settings, previous)
        self.jibe_config: JibeConfig = company

    def _resolve_base_url(self) -> str:
        if url := self.jibe_config.get("url"):
            return url.rstrip("/")
        if tenant := self.jibe_config.get("tenant"):
            return f"https://{tenant}.jibeapply.com"
        msg = f"{self.name}: neither 'tenant' nor 'url' specified in jibe configuration"
        raise ValueError(msg)

    def fetch_jobs(self) -> list[Job]:
        base_url = self._resolve_base_url()
        api_url = f"{base_url}/api/jobs"
        session = make_session()
        session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            }
        )

        max_pages = self.jibe_config.get("max_pages") or DEFAULT_MAX_PAGES
        jobs: list[Job] = []
        seen_req_ids: set[str] = set()
        last_page = 0

        for page in range(1, max_pages + 1):
            last_page = page
            params: dict[str, str | int] = {
                "page": page,
                "limit": DEFAULT_PAGE_SIZE,
            }
            log.debug("%s: fetching Jibe page %d (%s)", self.name, page, api_url)
            try:
                resp = session.get(api_url, params=params, timeout=TIMEOUT)
                resp.raise_for_status()
                payload = cast(JibeApiResponse, resp.json())
            except RequestException as exc:
                log.warning("%s: network error fetching Jibe page %d: %s", self.name, page, exc)
                break
            except ValueError as exc:
                log.warning("%s: failed parsing JSON from Jibe page %d: %s", self.name, page, exc)
                break

            raw_jobs = payload.get("jobs") or []
            if not raw_jobs:
                break

            for item in raw_jobs:
                data = item.get("data")
                if not data:
                    continue

                raw_req_id = data.get("req_id") or data.get("slug")
                if raw_req_id is None:
                    continue
                req_id = str(raw_req_id).strip()
                if not req_id or req_id in seen_req_ids:
                    continue
                seen_req_ids.add(req_id)

                title = data.get("title") or "Untitled"
                desc_html = data.get("description") or ""
                description = html_to_text(desc_html)

                primary_loc = data.get("location_name") or data.get("full_location")
                if not primary_loc:
                    loc_parts = [
                        p
                        for p in (data.get("city"), data.get("state"), data.get("country"))
                        if p and str(p).strip()
                    ]
                    primary_loc = ", ".join(loc_parts) if loc_parts else "Unknown"

                locations: list[str] = [primary_loc]
                if data.get("multipleLocations") and (add_locs := data.get("additional_locations")):
                    for add in add_locs:
                        name = add.get("location_name") or add.get("country")
                        if name and name not in locations:
                            locations.append(name)

                canonical_url = data.get("canonical_url")
                if not canonical_url:
                    meta = data.get("meta_data")
                    if meta:
                        canonical_url = meta.get("canonical_url")
                if not canonical_url:
                    canonical_url = data.get("apply_url")
                if not canonical_url:
                    canonical_url = f"{base_url}/jobs/{req_id}"

                date_str = data.get("create_date") or data.get("posted_date")
                posted_days = posted_days_from_jibe_date(date_str)
                posted_on = relative_day_text(posted_days) if posted_days is not None else ""

                job = Job(
                    id=f"{self.slug}:{req_id}",
                    company=self.name,
                    title=title,
                    location=primary_loc,
                    locations=locations,
                    url=canonical_url,
                    posted_on=posted_on,
                    posted_days=posted_days,
                    source=self.source,
                    description=description,
                )
                jobs.append(job)

            total_count = payload.get("totalCount")
            if total_count is not None and len(seen_req_ids) >= total_count:
                break

        log.info("%s: fetched %d jobs across %d pages", self.name, len(jobs), last_page)
        return jobs
