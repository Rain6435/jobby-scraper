"""Atlassian careers scraper (atlassian.com/company/careers).

Atlassian serves all open job postings in a single unauthenticated JSON payload:

    Endpoint: GET https://www.atlassian.com/endpoint/careers/listings

Each posting record in the response array includes the full job description
(overview, responsibilities, qualifications, compensation), structured location
strings, category taxonomy, employment type, and portal update timestamps.

Config entry:
    {"board": "atlassian", "name": "Atlassian"}
    {"board": "atlassian", "name": "Atlassian", "category": "Engineering"}
    {"board": "atlassian", "name": "Atlassian", "location": "Remote"}
    {"board": "atlassian", "name": "Atlassian", "keyword": "Python"}
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import NotRequired, TypedDict, cast

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import relative_day_text
from scraper.models import Job
from scraper.text import html_to_text

LISTINGS_URL = "https://www.atlassian.com/endpoint/careers/listings"
TIMEOUT = 20

log = logging.getLogger("scraper.atlassian")


class AtlassianPortalPost(TypedDict):
    id: NotRequired[int]
    portalId: NotRequired[int]
    portalUrl: NotRequired[str]
    updatedDate: NotRequired[str]


class AtlassianJobPost(TypedDict):
    id: NotRequired[int | str]
    portalId: NotRequired[int]
    portalJobPost: NotRequired[AtlassianPortalPost]
    title: NotRequired[str]
    category: NotRequired[str]
    type: NotRequired[str]
    locations: NotRequired[list[str]]
    overview: NotRequired[str]
    responsibilities: NotRequired[str]
    qualifications: NotRequired[str]
    compensation: NotRequired[str]
    payRanges: NotRequired[str]
    applyUrl: NotRequired[str]


def clean_atlassian_location(raw: str) -> str:
    """Clean Atlassian's verbose location string into a concise, standard format.

    Examples:
        'Austin - United States -   Austin, Texas 78702 United States' -> 'Austin, United States'
        'Remote - Americas - Remote' -> 'Remote, Americas'
        'Remote - Remote' -> 'Remote'
        'Mountain View - United States or Remote - ...' -> 'Mountain View, United States or Remote'
    """
    parts = [re.sub(r"\s+", " ", p).strip() for p in raw.split(" - ") if p.strip()]
    if not parts:
        return "Remote"
    if len(parts) == 1:
        return parts[0]
    if parts[0].lower() == "remote":
        if len(parts) > 1 and parts[1].lower() != "remote":
            return f"Remote, {parts[1]}"
        return "Remote"

    city = parts[0]
    country = parts[1] if len(parts) > 1 else ""
    if country and country.lower() != city.lower():
        return f"{city}, {country}"
    return city


def parse_atlassian_date(date_str: str | None) -> datetime | None:
    """Parse Atlassian updatedDate string, e.g. '2026-09-08 01:00 AM'."""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str.strip(), "%Y-%m-%d %I:%M %p")
        return dt.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


class AtlassianScraper(BaseScraper):
    source = "atlassian"

    def fetch_jobs(self) -> list[Job]:
        session = make_session()
        session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            }
        )

        category_filter = cast(str, self.company.get("category") or "").strip().lower()
        location_filter = cast(str, self.company.get("location") or "").strip().lower()
        keyword_filter = cast(str, self.company.get("keyword") or "").strip().lower()

        log.debug("%s: fetching listings from %s", self.name, LISTINGS_URL)
        resp = session.get(LISTINGS_URL, timeout=TIMEOUT)
        resp.raise_for_status()

        raw: object = resp.json()
        if not isinstance(raw, list):
            log.warning("%s: unexpected response type %s", self.name, type(raw))
            return []

        postings = cast(list[AtlassianJobPost], raw)
        log.debug("%s: received %d postings from API", self.name, len(postings))

        jobs: list[Job] = []
        now = datetime.now(UTC)

        for post in postings:
            title = (post.get("title") or "").strip()
            if not title:
                continue

            raw_id = post.get("id")
            if raw_id is None:
                continue
            external_id = str(raw_id).strip()

            category = (post.get("category") or "").strip()
            if category_filter and category_filter not in category.lower():
                continue

            raw_locs = post.get("locations") or []
            if location_filter:
                loc_match = any(location_filter in loc.lower() for loc in raw_locs)
                if not loc_match:
                    continue

            if keyword_filter and keyword_filter not in title.lower():
                continue

            # Clean locations
            cleaned_locs = [
                clean_atlassian_location(loc) for loc in raw_locs if loc and loc.strip()
            ]
            primary_loc = cleaned_locs[0] if cleaned_locs else "Remote"

            # URL: prefer portalUrl (canonical view), fallback to applyUrl
            portal_post = post.get("portalJobPost") or {}
            portal_url = portal_post.get("portalUrl") or post.get("applyUrl") or ""

            # Posting date
            updated_raw = portal_post.get("updatedDate")
            dt = parse_atlassian_date(updated_raw)
            posted_days: int | None = None
            posted_date: str | None = None
            posted_on: str = ""
            if dt:
                posted_date = dt.strftime("%Y-%m-%d")
                delta = (now - dt).days
                posted_days = max(0, delta)
                posted_on = relative_day_text(posted_days)

            # Assemble rich description
            desc_parts: list[str] = []
            for val in (
                post.get("overview"),
                post.get("responsibilities"),
                post.get("qualifications"),
                post.get("payRanges"),
                post.get("compensation"),
            ):
                if val and val.strip():
                    desc_parts.append(val.strip())

            raw_html_desc = "\n\n".join(desc_parts)
            plain_desc = html_to_text(raw_html_desc) if raw_html_desc else ""

            job_id = f"{self.slug}:{external_id}"
            jobs.append(
                Job(
                    id=job_id,
                    company=self.name,
                    title=title,
                    location=primary_loc,
                    locations=cleaned_locs,
                    url=portal_url,
                    posted_on=posted_on,
                    posted_days=posted_days,
                    posted_date=posted_date,
                    source=self.source,
                    description=plain_desc,
                )
            )

        log.debug("%s: successfully parsed %d jobs", self.name, len(jobs))
        return jobs
