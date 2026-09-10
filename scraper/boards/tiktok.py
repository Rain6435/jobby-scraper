"""TikTok / ByteDance careers scraper (lifeattiktok.com / careers.tiktok.com).

TikTok operates an in-house candidate portal and ATS backed by ByteDance's
internal Stargate microservice gateway:

    Endpoint: POST https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts

Requires gateway header:
    website-path: tiktok

Each posting record in the search results includes the full job description,
minimum and preferred requirements, structured hierarchical locations
(city, state, country), and category metadata in a single response payload.

Config entry:
    {"board": "tiktok", "name": "TikTok"}
    {"board": "tiktok", "name": "TikTok", "keyword": "software"}
"""

from __future__ import annotations

import logging
from typing import NotRequired, TypedDict, cast

from scraper.boards.base import BaseScraper, make_session
from scraper.models import Job
from scraper.text import html_to_text

SEARCH_URL = "https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts"
PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 50  # ~5,000 jobs by default (TikTok has ~4,200 active roles)
MAX_PAGES_CAP = 100  # safety cap
TIMEOUT = 30

log = logging.getLogger("scraper.tiktok")


class TikTokCityInfo(TypedDict):
    code: NotRequired[str]
    en_name: NotRequired[str]
    i18n_name: NotRequired[str]
    name: NotRequired[str]
    parent: NotRequired[TikTokCityInfo | None]


class TikTokNamedEntity(TypedDict):
    id: NotRequired[str | int]
    en_name: NotRequired[str]
    i18n_name: NotRequired[str]
    name: NotRequired[str]


class TikTokJobPost(TypedDict):
    id: NotRequired[str]
    code: NotRequired[str]
    title: NotRequired[str]
    description: NotRequired[str]
    requirement: NotRequired[str]
    city_info: NotRequired[TikTokCityInfo | None]
    job_category: NotRequired[TikTokNamedEntity | None]
    recruit_type: NotRequired[TikTokNamedEntity | None]


class TikTokData(TypedDict):
    count: NotRequired[int]
    job_post_list: NotRequired[list[TikTokJobPost]]


class TikTokResponse(TypedDict):
    code: NotRequired[int]
    message: NotRequired[str]
    data: NotRequired[TikTokData]


def _format_location(city_info: TikTokCityInfo | None) -> str:
    """Extract hierarchically ordered location: City, State, Country."""
    if not city_info:
        return "Remote"
    parts: list[str] = []
    curr: TikTokCityInfo | None = city_info
    while curr:
        name = curr.get("en_name") or curr.get("i18n_name") or curr.get("name")
        if name:
            parts.append(str(name).strip())
        curr = curr.get("parent")
    return ", ".join(parts) if parts else "Remote"


class TikTokScraper(BaseScraper):
    source = "tiktok"

    def fetch_jobs(self) -> list[Job]:
        session = make_session()
        session.headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "website-path": "tiktok",
                "Referer": "https://lifeattiktok.com/search",
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            }
        )

        keyword = cast(str, self.company.get("keyword") or "")

        cfg_max = self.company.get("max_pages")
        if isinstance(cfg_max, int) and cfg_max > 0:
            max_pages = min(cfg_max, MAX_PAGES_CAP)
        else:
            max_pages = DEFAULT_MAX_PAGES

        jobs: list[Job] = []

        for page in range(max_pages):
            offset = page * PAGE_SIZE
            payload = {
                "keyword": keyword,
                "limit": PAGE_SIZE,
                "offset": offset,
            }

            log.debug("%s: page=%d offset=%d", self.name, page, offset)
            resp = session.post(SEARCH_URL, json=payload, timeout=TIMEOUT)
            resp.raise_for_status()

            raw: object = resp.json()
            if not isinstance(raw, dict):
                log.warning("%s: unexpected response type %s", self.name, type(raw))
                break

            data = cast(TikTokResponse, raw)
            code = data.get("code")
            if code != 0:
                log.warning(
                    "%s: API returned non-zero code %s: %s", self.name, code, data.get("message")
                )
                break

            data_obj: TikTokData = data.get("data") or {}
            total_count: int = data_obj.get("count") or 0
            job_posts: list[TikTokJobPost] = data_obj.get("job_post_list") or []

            log.debug(
                "%s: page=%d returned %d postings (total=%d)",
                self.name,
                page,
                len(job_posts),
                total_count,
            )

            for post in job_posts:
                job = self._to_job(post)
                if job:
                    jobs.append(job)

            if not job_posts or (total_count and offset + len(job_posts) >= total_count):
                break

        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    def _to_job(self, raw: TikTokJobPost) -> Job | None:
        raw_id = raw.get("id") or ""
        post_id = str(raw_id).strip()
        if not post_id:
            return None

        title = (raw.get("title") or "").strip()
        location = _format_location(raw.get("city_info"))

        # Combine description and requirement sections
        desc_parts = [
            (raw.get("description") or "").strip(),
            (raw.get("requirement") or "").strip(),
        ]
        full_text = "\n\n".join(p for p in desc_parts if p)
        description = html_to_text(full_text)

        url = f"https://lifeattiktok.com/position/{post_id}"

        return Job(
            id=f"{self.slug}:{post_id}",
            company=self.name,
            title=title,
            location=location,
            locations=[location] if location else [],
            url=url,
            posted_on="",
            source=self.source,
            description=description,
            company_blurb=self.company.get("blurb", ""),
        )
