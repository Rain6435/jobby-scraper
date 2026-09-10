"""Pinpoint public job board scraper.

One unauthenticated GET returns every job with its locations, posting date,
and full HTML description — no pagination, no per-job detail calls:
    GET https://<company>.pinpointhq.com/postings.json
Config:
{"board": "pinpoint", "company": "<subdomain>"}.
"""

from __future__ import annotations

import logging
from typing import NotRequired, TypedDict, cast

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import posted_days_from_iso, relative_day_text
from scraper.config_types import PinpointConfig
from scraper.models import Job
from scraper.text import html_to_text

API = "https://{company}.pinpointhq.com/postings.json"
TIMEOUT = 30

log = logging.getLogger("scraper.pinpoint")


class PinpointLocation(TypedDict):
    name: NotRequired[str]
    city: NotRequired[str]
    country: NotRequired[str]


class PinpointPosting(TypedDict):
    id: int | str
    title: NotRequired[str]
    url: NotRequired[str]
    description: NotRequired[str]
    location: NotRequired[PinpointLocation | str]
    locations: NotRequired[list[PinpointLocation | str]]
    created_at: NotRequired[str]
    updated_at: NotRequired[str]


class PinpointResponse(TypedDict):
    data: NotRequired[list[PinpointPosting]]


class PinpointScraper(BaseScraper):
    source = "pinpoint"

    def fetch_jobs(self) -> list[Job]:
        cfg: PinpointConfig = cast(PinpointConfig, self.company)
        company = cfg["company"]
        session = make_session()
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})

        log.debug("%s: fetching job list", self.name)
        resp = session.get(API.format(company=company), timeout=TIMEOUT)
        resp.raise_for_status()

        raw_json: object = resp.json()
        postings: list[PinpointPosting] = []
        if isinstance(raw_json, list):
            postings = cast(list[PinpointPosting], raw_json)
        elif isinstance(raw_json, dict):
            resp_dict = cast(PinpointResponse, raw_json)
            postings = resp_dict.get("data", [])

        log.debug("%s: %d postings returned", self.name, len(postings))

        jobs: list[Job] = []
        for p in postings:
            job_id = str(p.get("id", ""))
            if not job_id:
                continue
            locations = self._locations(p)
            posted_days = posted_days_from_iso(p.get("created_at") or p.get("updated_at") or "")
            jobs.append(
                Job(
                    id=f"{self.slug}:{job_id}",
                    company=self.name,
                    title=(p.get("title") or "").strip(),
                    location=locations[0] if locations else "",
                    locations=locations,
                    url=p.get("url", ""),
                    posted_on=relative_day_text(posted_days),
                    posted_days=posted_days,
                    source=self.source,
                    description=html_to_text(p.get("description", "")),
                )
            )

        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    @staticmethod
    def _extract_location_str(loc: PinpointLocation | str) -> str:
        if isinstance(loc, str):
            return loc.strip()
        name = loc.get("name", "")
        city = loc.get("city", "")
        country = loc.get("country", "")
        if city and country:
            return f"{city}, {country}".strip(", ")
        if name:
            return name.strip()
        if city:
            return city.strip()
        return country.strip()

    @classmethod
    def _locations(cls, posting: PinpointPosting) -> list[str]:
        loc_items: list[PinpointLocation | str] = []
        multi = posting.get("locations")
        if multi:
            loc_items.extend(multi)
        single = posting.get("location")
        if single and not multi:
            loc_items.append(single)

        loc_strings: list[str] = []
        for item in loc_items:
            s = cls._extract_location_str(item)
            if s and s not in loc_strings:
                loc_strings.append(s)
        return loc_strings
