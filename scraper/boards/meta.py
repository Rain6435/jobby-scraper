"""Meta careers scraper (metacareers.com).

Meta (Facebook, Instagram, WhatsApp, Reality Labs, Meta AI) operates its own
in-house career portal powered by a GraphQL backend at metacareers.com.

Search: POST https://www.metacareers.com/graphql
Payload includes doc_id="27129360303422352" (CareersJobSearchResultsV2DataQuery)
and LSD token.

Each posting has:
    - id (e.g. "1456837426495499")
    - title (e.g. "Infrastructure Accounting Manager...")
    - locations (list of office/remote locations)
    - teams (list of primary divisions/teams)
    - sub_teams (list of specific sub-teams)

Direct job URLs follow:
    https://www.metacareers.com/jobs/{id}/

Config entry:
    {"board": "meta", "name": "Meta"}
"""

from __future__ import annotations

import json
import logging
from typing import NotRequired, TypedDict, cast

import requests

from scraper.boards.base import BaseScraper, make_session
from scraper.config_types import MetaConfig
from scraper.models import Job

GRAPHQL_URL = "https://www.metacareers.com/graphql"
DOC_ID = "27129360303422352"
LSD_TOKEN = "AdRzjWA2SQrP3uT6KgvnpnR7hgo"
TIMEOUT = 30

log = logging.getLogger("scraper.meta")


class MetaRawJob(TypedDict):
    id: NotRequired[str | int]
    title: NotRequired[str]
    locations: NotRequired[list[str]]
    teams: NotRequired[list[str]]
    sub_teams: NotRequired[list[str]]


class MetaSearchResults(TypedDict):
    all_jobs: NotRequired[list[MetaRawJob]]


class MetaData(TypedDict):
    job_search_with_featured_jobs_v2: NotRequired[MetaSearchResults]


class MetaResponse(TypedDict):
    data: NotRequired[MetaData]


class MetaScraper(BaseScraper):
    source = "meta"

    def __init__(self, company: MetaConfig) -> None:
        super().__init__(company)
        self._meta_config: MetaConfig = company

    def fetch_jobs(self) -> list[Job]:
        session = make_session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://www.metacareers.com/jobs/",
                "Origin": "https://www.metacareers.com",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Dest": "empty",
                "x-fb-friendly-name": "CareersJobSearchResultsV2DataQuery",
                "x-asbd-id": "359341",
                "x-fb-lsd": LSD_TOKEN,
            }
        )

        query = self._meta_config.get("query")
        payload = {
            "av": "0",
            "__user": "0",
            "__a": "1",
            "__req": "3",
            "lsd": LSD_TOKEN,
            "fb_api_caller_class": "RelayModern",
            "fb_api_req_friendly_name": "CareersJobSearchResultsV2DataQuery",
            "variables": json.dumps(
                {
                    "search_input": {
                        "q": query if query else None,
                        "divisions": [],
                        "offices": [],
                        "roles": [],
                        "leadership_levels": [],
                        "saved_jobs": [],
                        "saved_searches": [],
                        "sub_teams": [],
                        "teams": [],
                        "is_leadership": False,
                        "is_remote_only": False,
                        "sort_by_new": False,
                        "results_per_page": None,
                    },
                    "viewasUserID": None,
                    "isLoggedIn": False,
                }
            ),
            "doc_id": DOC_ID,
        }

        try:
            resp = session.post(GRAPHQL_URL, data=payload, timeout=TIMEOUT)
            resp.raise_for_status()
            data = cast(MetaResponse, resp.json())
        except requests.RequestException as e:
            log.warning("Failed to fetch Meta jobs: %s", e)
            return []

        search_data = data.get("data", {}).get("job_search_with_featured_jobs_v2", {})
        raw_jobs = search_data.get("all_jobs", [])

        jobs: list[Job] = []
        for raw in raw_jobs:
            job_id = str(raw.get("id") or "").strip()
            title = str(raw.get("title") or "").strip()
            if not job_id or not title:
                continue

            locations = [str(loc).strip() for loc in raw.get("locations") or [] if str(loc).strip()]
            location = locations[0] if locations else ""

            teams = [str(t).strip() for t in raw.get("teams") or [] if str(t).strip()]
            sub_teams = [str(st).strip() for st in raw.get("sub_teams") or [] if str(st).strip()]

            desc_parts: list[str] = []
            if teams:
                desc_parts.append(f"Teams: {', '.join(teams)}")
            if sub_teams:
                desc_parts.append(f"Sub-teams: {', '.join(sub_teams)}")
            description = " | ".join(desc_parts)

            jobs.append(
                Job(
                    id=f"{self.slug}:{job_id}",
                    company=self.name,
                    title=title,
                    location=location,
                    locations=locations,
                    url=f"https://www.metacareers.com/jobs/{job_id}/",
                    posted_on="",
                    source=self.source,
                    description=description,
                )
            )

        log.info("Scraped %d jobs for %s", len(jobs), self.name)
        return jobs
