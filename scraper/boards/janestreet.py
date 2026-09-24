"""Jane Street careers scraper (janestreet.com/jobs/main.json).

Jane Street operates its own custom career portal listing all global roles
at janestreet.com. The complete open positions catalog is available via an
unauthenticated JSON endpoint at https://www.janestreet.com/jobs/main.json.

Each posting has:
    - id (e.g. 8631912002)
    - position (title, e.g. "Software Engineer")
    - category (department, e.g. "Technology")
    - availability (e.g. "Full-Time: Experienced", "Internship")
    - city (city code, e.g. "NYC", "LDN", "SGP", "HKG")
    - overview (HTML job description with full role requirements)
    - team (team name)
    - min_salary, max_salary (salary range)

Direct job URLs follow:
    https://www.janestreet.com/join-jane-street/position/{id}/

Config entry:
    {"board": "janestreet", "name": "Jane Street"}
"""

from __future__ import annotations

import logging
from typing import NotRequired, TypedDict, cast

import requests

from scraper.boards.base import BaseScraper, make_session
from scraper.config_types import JaneStreetConfig
from scraper.models import Job
from scraper.text import html_to_text

JOBS_URL = "https://www.janestreet.com/jobs/main.json"
TIMEOUT = 30

CITY_NAME_MAP: dict[str, str] = {
    "NYC": "New York, NY",
    "LDN": "London, UK",
    "HKG": "Hong Kong",
    "AMS": "Amsterdam, Netherlands",
    "CHI": "Chicago, IL",
    "SGP": "Singapore",
    "MUM": "Mumbai, India",
    "SHA": "Shanghai, China",
    "PHL": "Philadelphia, PA",
    "SF": "San Francisco, CA",
    "ATX": "Austin, TX",
    "NYC/HKG": "New York, NY / Hong Kong",
}

log = logging.getLogger("scraper.janestreet")


class JaneStreetRawJob(TypedDict):
    id: NotRequired[int | str]
    position: NotRequired[str]
    category: NotRequired[str]
    availability: NotRequired[str]
    city: NotRequired[str]
    overview: NotRequired[str]
    team: NotRequired[str]
    duration: NotRequired[str]
    min_salary: NotRequired[str]
    max_salary: NotRequired[str]


class JaneStreetScraper(BaseScraper):
    source = "janestreet"

    def __init__(
        self,
        company: JaneStreetConfig,
        settings: dict[str, object] | None = None,
        previous: dict[str, Job] | None = None,
    ) -> None:
        super().__init__(company, settings, previous)
        self._jane_config: JaneStreetConfig = company

    def fetch_jobs(self) -> list[Job]:
        session = make_session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
            }
        )

        try:
            resp = session.get(JOBS_URL, timeout=TIMEOUT)
            resp.raise_for_status()
            raw_jobs = cast(list[JaneStreetRawJob], resp.json())
        except requests.RequestException as e:
            log.warning("Failed to fetch Jane Street jobs: %s", e)
            return []

        location_filter = self._jane_config.get("location")
        jobs: list[Job] = []

        for raw in raw_jobs:
            raw_id = raw.get("id")
            title = (raw.get("position") or "").strip()
            if not raw_id or not title:
                continue

            city_code = (raw.get("city") or "").strip()
            location = CITY_NAME_MAP.get(city_code, city_code)
            locations = [location] if location else []

            if (
                location_filter
                and location_filter.lower() not in location.lower()
                and location_filter.lower() not in city_code.lower()
            ):
                continue

            overview_html = raw.get("overview") or ""
            desc_text = html_to_text(overview_html)

            min_sal = raw.get("min_salary")
            max_sal = raw.get("max_salary")
            if min_sal and max_sal:
                salary_header = f"Salary: ${min_sal} - ${max_sal}"
                desc_text = f"{salary_header}\n\n{desc_text}" if desc_text else salary_header

            category = raw.get("category")
            team = raw.get("team")
            availability = raw.get("availability")
            meta_parts: list[str] = []
            if category:
                meta_parts.append(f"Department: {category}")
            if team:
                meta_parts.append(f"Team: {team}")
            if availability:
                meta_parts.append(f"Type: {availability}")
            if meta_parts:
                meta_header = " | ".join(meta_parts)
                desc_text = f"{meta_header}\n\n{desc_text}" if desc_text else meta_header

            jobs.append(
                Job(
                    id=f"{self.slug}:{raw_id}",
                    company=self.name,
                    title=title,
                    location=location,
                    locations=locations,
                    url=f"https://www.janestreet.com/join-jane-street/position/{raw_id}/",
                    posted_on="",
                    source=self.source,
                    description=desc_text,
                )
            )

        log.info("Scraped %d jobs for %s", len(jobs), self.name)
        return jobs
