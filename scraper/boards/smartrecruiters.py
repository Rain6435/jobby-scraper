"""SmartRecruiters public job board scraper.

The list endpoint returns every open posting with its location and release
date, but not a description or a stable posting URL — both live only in the
per-posting detail endpoint, so each listed job costs one extra GET:
    GET https://api.smartrecruiters.com/v1/companies/<company>/postings?limit=100&offset=0
        → {"totalFound": N, "content": [...]}
    GET https://api.smartrecruiters.com/v1/companies/<company>/postings/<id>
        → {"postingUrl": "...", "jobAd": {"sections": {"jobDescription": {"text": "<html>"}, ...}}}
Each list item has id, name, releasedDate (ISO+tz), location.fullLocation.
Config: {"board": "smartrecruiters", "company": "<identifier>"}.
"""

from __future__ import annotations

import logging
from typing import NotRequired, TypedDict, cast

import requests

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import posted_days_from_iso, relative_day_text
from scraper.config_types import SmartRecruitersConfig
from scraper.models import Job
from scraper.text import html_to_text

API = "https://api.smartrecruiters.com/v1/companies/{company}/postings"
DETAIL_URL = "https://api.smartrecruiters.com/v1/companies/{company}/postings/{posting_id}"
PAGE_LIMIT = 100
MAX_PAGES = 50  # safety cap
TIMEOUT = 30

log = logging.getLogger("scraper.smartrecruiters")


class SmartRecruitersLocation(TypedDict):
    fullLocation: NotRequired[str]


class SmartRecruitersPosting(TypedDict):
    id: str
    name: NotRequired[str]
    releasedDate: NotRequired[str]
    location: NotRequired[SmartRecruitersLocation]


class SmartRecruitersListResponse(TypedDict):
    totalFound: NotRequired[int]
    content: NotRequired[list[SmartRecruitersPosting]]


class SmartRecruitersJobDescriptionSection(TypedDict):
    text: NotRequired[str]


class SmartRecruitersJobAdSections(TypedDict):
    jobDescription: NotRequired[SmartRecruitersJobDescriptionSection]


class SmartRecruitersJobAd(TypedDict):
    sections: NotRequired[SmartRecruitersJobAdSections]


class SmartRecruitersDetailResponse(TypedDict):
    postingUrl: NotRequired[str]
    jobAd: NotRequired[SmartRecruitersJobAd]


class SmartRecruitersScraper(BaseScraper):
    source = "smartrecruiters"

    def fetch_jobs(self) -> list[Job]:
        cfg: SmartRecruitersConfig = cast(SmartRecruitersConfig, self.company)
        company = cfg["company"]
        url = API.format(company=company)
        session = make_session()
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})

        jobs: list[Job] = []
        offset = 0
        for _page in range(MAX_PAGES):
            log.debug("%s: fetching offset=%d", self.name, offset)
            resp = session.get(url, params={"limit": PAGE_LIMIT, "offset": offset}, timeout=TIMEOUT)
            resp.raise_for_status()
            data: SmartRecruitersListResponse = resp.json()
            postings = data.get("content", [])
            total_found = data.get("totalFound", len(postings))
            log.debug(
                "%s: %d postings on this page (totalFound=%d)",
                self.name,
                len(postings),
                total_found,
            )

            for p in postings:
                loc = p.get("location") or {}
                where = loc.get("fullLocation") or ""
                locations = [where] if where else []
                posted_days = posted_days_from_iso(p.get("releasedDate", ""))
                job_id = f"{self.slug}:{p['id']}"
                description, posting_url = cast(
                    "tuple[str, str]",
                    self._fetch_with_cache(
                        job_id,
                        ("description", "url"),
                        lambda: self._fetch_detail(session, company, p["id"]),
                    ),
                )
                jobs.append(
                    Job(
                        id=job_id,
                        company=self.name,
                        title=(p.get("name") or "").strip(),
                        location=where,
                        locations=locations,
                        url=posting_url,
                        posted_on=relative_day_text(posted_days),
                        posted_days=posted_days,
                        source=self.source,
                        description=description,
                    )
                )

            offset += len(postings)
            if not postings or offset >= total_found:
                log.debug("%s: reached last page, stopping", self.name)
                break
        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    @staticmethod
    def _fetch_detail(session: requests.Session, company: str, posting_id: str) -> tuple[str, str]:
        try:
            resp = session.get(
                DETAIL_URL.format(company=company, posting_id=posting_id),
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            detail: SmartRecruitersDetailResponse = resp.json()
            sections = (detail.get("jobAd") or {}).get("sections") or {}
            html = (sections.get("jobDescription") or {}).get("text", "")
            return html_to_text(html), detail.get("postingUrl", "")
        except Exception:
            log.warning("SmartRecruiters detail fetch failed for job %s", posting_id)
            return "", ""
