"""ReliefWeb (UN & Global Humanitarian NGOs) job board scraper.

Unlike per-employer boards, ReliefWeb is a global humanitarian aggregator
covering UN agencies, the Red Cross/Red Crescent, and international NGOs.
Job.company is set per-result from the API's own source organization:
    GET https://api.reliefweb.int/v2/jobs
Config:
{"board": "reliefweb", "name": "ReliefWeb"}.
"""

from __future__ import annotations

import logging
from typing import NotRequired, TypedDict

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import posted_days_from_iso, relative_day_text
from scraper.models import Job
from scraper.text import html_to_text

API = "https://api.reliefweb.int/v2/jobs"
RESULTS_PER_PAGE = 100
MAX_PAGES = 10  # safety cap against runaway pagination (~1000 jobs)
TIMEOUT = 30

log = logging.getLogger("scraper.reliefweb")


class ReliefwebNamedItem(TypedDict):
    name: NotRequired[str]
    shortname: NotRequired[str]


class ReliefwebDate(TypedDict):
    created: NotRequired[str]
    closing: NotRequired[str]


class ReliefwebFields(TypedDict):
    title: NotRequired[str]
    url: NotRequired[str]
    body: NotRequired[str]
    body_html: NotRequired[str]
    date: NotRequired[ReliefwebDate]
    source: NotRequired[list[ReliefwebNamedItem]]
    country: NotRequired[list[ReliefwebNamedItem]]
    city: NotRequired[list[ReliefwebNamedItem]]


class ReliefwebDataItem(TypedDict):
    id: str | int
    fields: NotRequired[ReliefwebFields]


class ReliefwebResponse(TypedDict):
    totalCount: NotRequired[int]
    count: NotRequired[int]
    data: NotRequired[list[ReliefwebDataItem]]


class ReliefwebScraper(BaseScraper):
    source = "reliefweb"

    def fetch_jobs(self) -> list[Job]:
        import os

        appname = os.environ.get("RELIEFWEB_APPNAME") or "jobby-scraper"
        session = make_session()
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})

        jobs: list[Job] = []
        for page in range(MAX_PAGES):
            offset = page * RESULTS_PER_PAGE
            log.debug("%s: fetching page=%d (offset=%d)", self.name, page + 1, offset)
            try:
                resp = session.get(
                    API,
                    params={
                        "appname": appname,
                        "profile": "list",
                        "limit": RESULTS_PER_PAGE,
                        "offset": offset,
                    },
                    timeout=TIMEOUT,
                )
                if resp.status_code == 403:
                    log.warning(
                        "%s: ReliefWeb API requires an approved appname (RELIEFWEB_APPNAME env var) — skipping",
                        self.name,
                    )
                    return []
                resp.raise_for_status()
            except Exception as e:
                log.warning("%s: error fetching ReliefWeb page=%d: %s", self.name, page + 1, e)
                break

            body: ReliefwebResponse = resp.json()
            data_items = body.get("data", [])
            log.debug("%s: page=%d returned %d items", self.name, page + 1, len(data_items))

            for item in data_items:
                job = self._to_job(item)
                if job:
                    jobs.append(job)

            if len(data_items) < RESULTS_PER_PAGE:
                break

        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    def _to_job(self, item: ReliefwebDataItem) -> Job | None:
        job_id = str(item.get("id", ""))
        if not job_id:
            return None

        fields = item.get("fields", {})
        title = (fields.get("title") or "").strip()
        url = fields.get("url", "")

        sources = fields.get("source") or []
        company = sources[0].get("name") if sources else self.name
        if not company:
            company = self.name

        locations = self._locations(fields)
        created_at = (fields.get("date") or {}).get("created", "")
        posted_days = posted_days_from_iso(created_at)

        desc_raw = fields.get("body") or fields.get("body_html") or ""
        description = html_to_text(desc_raw)

        return Job(
            id=f"{self.slug}:{job_id}",
            company=company,
            title=title,
            location=locations[0] if locations else "",
            locations=locations,
            url=url,
            posted_on=relative_day_text(posted_days),
            posted_days=posted_days,
            source=self.source,
            description=description,
        )

    @staticmethod
    def _locations(fields: ReliefwebFields) -> list[str]:
        cities = [c.get("name") for c in fields.get("city") or [] if c.get("name")]
        countries = [c.get("name") for c in fields.get("country") or [] if c.get("name")]

        if cities and countries:
            return [f"{cities[0]}, {countries[0]}"]
        if countries:
            return [c for c in countries if c]
        if cities:
            return [c for c in cities if c]
        return []
