"""BambooHR careers scraper.

The /list endpoint returns every opening with its location but no posting date
or description (those live in /detail; date is still skipped — age is tracked
by Job.first_seen instead — but the description costs one extra GET per job).
Multi-location roles already arrive as separate rows.
    GET https://<company>.bamboohr.com/careers/list
    GET https://<company>.bamboohr.com/careers/<id>/detail → {"result": {"jobOpening": {"description": "<html>..."}}}
Each result has id, jobOpeningName, location{city,state}. Config:
    {"board": "bamboohr", "company": "<subdomain>"}.
"""

from __future__ import annotations

import logging
from typing import NotRequired, TypedDict, cast

import requests

from scraper.boards.base import BaseScraper, make_session
from scraper.config_types import BambooHrConfig
from scraper.models import Job
from scraper.text import html_to_text

LIST_URL = "https://{company}.bamboohr.com/careers/list"
JOB_URL = "https://{company}.bamboohr.com/careers/{id}"
DETAIL_URL = "https://{company}.bamboohr.com/careers/{id}/detail"
TIMEOUT = 30

log = logging.getLogger("scraper.bamboohr")


class BambooHrLocation(TypedDict):
    city: NotRequired[str]
    state: NotRequired[str]


class BambooHrListing(TypedDict):
    id: str
    jobOpeningName: NotRequired[str]
    location: NotRequired[BambooHrLocation]


class BambooHrListResponse(TypedDict):
    result: NotRequired[list[BambooHrListing]]


class BambooHrJobOpening(TypedDict):
    description: NotRequired[str]


class BambooHrDetailResult(TypedDict):
    jobOpening: NotRequired[BambooHrJobOpening]


class BambooHrDetailResponse(TypedDict):
    result: NotRequired[BambooHrDetailResult]


class BambooHRScraper(BaseScraper):
    source = "bamboohr"

    def fetch_jobs(self) -> list[Job]:
        company: BambooHrConfig = cast(BambooHrConfig, self.company)
        subdomain = company["company"]
        session = make_session()
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})

        log.debug("%s: fetching job list", self.name)
        resp = session.get(LIST_URL.format(company=subdomain), timeout=TIMEOUT)
        resp.raise_for_status()
        body: BambooHrListResponse = resp.json()
        results = body.get("result", [])
        log.debug("%s: %d listings returned", self.name, len(results))

        job_ids = [f"{self.slug}:{r['id']}" for r in results]
        details = self._fetch_details_concurrent(
            job_ids,
            ("description",),
            lambda job_id: (self._fetch_description(session, subdomain, job_id.split(":", 1)[1]),),
        )

        jobs: list[Job] = []
        for r in results:
            loc = r.get("location") or {}
            where = ", ".join(part for part in (loc.get("city"), loc.get("state")) if part)
            locations = [where] if where else []
            job_id = f"{self.slug}:{r['id']}"
            (description,) = cast("tuple[str]", details[job_id])
            jobs.append(
                Job(
                    id=job_id,
                    company=self.name,
                    title=(r.get("jobOpeningName") or "").strip(),
                    location=where,
                    locations=locations,
                    url=JOB_URL.format(company=subdomain, id=r["id"]),
                    posted_on="",  # date only in detail — skipped
                    posted_days=None,  # age tracked via first_seen
                    source=self.source,
                    description=description,
                )
            )
        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    @staticmethod
    def _fetch_description(session: requests.Session, subdomain: str, job_id: str) -> str:
        try:
            resp = session.get(DETAIL_URL.format(company=subdomain, id=job_id), timeout=TIMEOUT)
            resp.raise_for_status()
            detail: BambooHrDetailResponse = resp.json()
            opening = detail.get("result", {}).get("jobOpening", {})
            return html_to_text(opening.get("description", ""))
        except Exception:
            log.warning("BambooHR detail fetch failed for job %s", job_id)
            return ""
