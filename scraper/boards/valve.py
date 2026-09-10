"""Valve Software careers scraper (www.valvesoftware.com/en/jobs).

Valve runs its own flat careers site with no external ATS vendor. All open
positions are listed on a single page:

    List:   GET https://www.valvesoftware.com/en/jobs
    Detail: GET https://www.valvesoftware.com/en/jobs?job_id={job_id}

Positions are extracted via link regexes. Full role descriptions are fetched
concurrently from each job page and cached across runs via
BaseScraper._fetch_details_concurrent.

All Valve jobs are on-site at Valve HQ in Bellevue, WA.

Config entry:
    {"board": "valve", "name": "Valve"}
"""

from __future__ import annotations

import logging
import re
from typing import cast

import requests

from scraper.boards.base import BaseScraper, make_session
from scraper.models import Job
from scraper.text import html_to_text

LIST_URL = "https://www.valvesoftware.com/en/jobs"
DETAIL_URL = "https://www.valvesoftware.com/en/jobs?job_id={job_id}"
LOCATION = "Bellevue, WA"
TIMEOUT = 30

ITEM_RE = re.compile(
    r"<a[^>]+href=[\"\']https://www\.valvesoftware\.com/en/jobs\?job_id=(\d+)[\"\'][^>]*>(.*?)</a>",
    re.DOTALL,
)
DESC_RE = re.compile(
    r"<div class=[\"\']job_description_intro[\"\']>(.*?)</div>",
    re.DOTALL,
)

log = logging.getLogger("scraper.valve")


class ValveScraper(BaseScraper):
    source = "valve"

    def fetch_jobs(self) -> list[Job]:
        session = make_session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            }
        )

        log.debug("%s: fetching jobs list from %s", self.name, LIST_URL)
        resp = session.get(LIST_URL, timeout=TIMEOUT)
        resp.raise_for_status()

        matches = ITEM_RE.findall(resp.text)
        openings: dict[str, str] = {}  # job_id -> title
        for job_id, inner in matches:
            clean_title = re.sub(r"<[^>]+>", " ", inner)
            clean_title = re.sub(r"\s+", " ", clean_title).strip()
            if job_id and clean_title:
                openings[job_id] = clean_title

        log.debug("%s: found %d listings", self.name, len(openings))

        should_fetch_details = self.company.get("fetch_details", True)
        job_ids = [f"{self.slug}:{jid}" for jid in openings]
        details: dict[str, tuple[object, ...]] = {}

        if should_fetch_details and job_ids:
            details = self._fetch_details_concurrent(
                job_ids,
                ("description",),
                lambda job_id: self._fetch_detail(session, job_id.split(":", 1)[1]),
            )

        jobs: list[Job] = []
        for jid, title in openings.items():
            full_id = f"{self.slug}:{jid}"
            desc = ""
            if full_id in details:
                desc = cast(str, details[full_id][0])

            jobs.append(
                Job(
                    id=full_id,
                    company=self.name,
                    title=title,
                    location=LOCATION,
                    locations=[LOCATION],
                    url=f"https://www.valvesoftware.com/en/jobs?job_id={jid}",
                    posted_on="",
                    posted_days=None,
                    source=self.source,
                    description=desc,
                )
            )

        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    @staticmethod
    def _fetch_detail(session: requests.Session, job_id: str) -> tuple[str]:
        try:
            url = DETAIL_URL.format(job_id=job_id)
            resp = session.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            match = DESC_RE.search(resp.text)
            if match:
                return (html_to_text(match.group(1)),)
            return ("",)
        except Exception:
            log.warning("Valve detail fetch failed for job %s", job_id)
            return ("",)
