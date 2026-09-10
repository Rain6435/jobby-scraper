"""IBM careers scraper (www.ibm.com/careers/search).

IBM runs its own custom job search powered by an internal Elasticsearch-backed
API ("Genesis") — not a standard ATS board. The endpoint was discovered via browser
network analysis on the careers page:

    POST https://www-api.ibm.com/search/api/v2
    Headers: Content-Type: application/json
             Referer: https://www.ibm.com/

No authentication required. The payload uses Elasticsearch query DSL with
IBM-specific field names:

    field_keyword_05  → country (e.g. "United States", "Canada", "India")
    field_keyword_08  → job category / career area (e.g. "Software Engineering")
    field_keyword_17  → work type (e.g. "Hybrid", "Remote", "On-site")
    field_keyword_18  → experience level (e.g. "Entry Level", "Internship", "Professional")
    field_keyword_19  → location string (e.g. "Toronto, CA", "Multiple Cities")
    field_keyword_20  → legal entity / subsidiary (e.g. "(0147) International Business Machines Corporation")
    field_text_01     → numeric job ID (e.g. 129622) used in careers portal URLs
    language          → posting language (e.g. "en", "fr")

For full documentation and query DSL examples, see exploration/ibm_api.md.

Results are paginated via ``from`` + ``size``. Total available jobs is returned
as ``hits.total.value``. English-language postings are filtered with
``lang: "en"``.

One config entry covers all IBM jobs (no per-employer slug needed):
    {"board": "ibm", "name": "IBM"}

The ``_id`` field is a SHA-256 hash unique per posting; ``url`` links directly
to ``careers.ibm.com/careers/JobDetail?jobId=...``.
"""

from __future__ import annotations

import logging
from typing import NotRequired, TypedDict, cast

from scraper.boards.base import BaseScraper, make_session
from scraper.models import Job

API = "https://www-api.ibm.com/search/api/v2"
PAGE_SIZE = 100
MAX_PAGES = 25  # safety cap — ~2500 jobs, well above IBM's ~2000 live postings
TIMEOUT = 30

log = logging.getLogger("scraper.ibm")


class IBMJobSource(TypedDict):
    title: NotRequired[str]
    url: NotRequired[str]
    description: NotRequired[str]
    language: NotRequired[str]
    field_text_01: NotRequired[int | str]  # numeric job ID
    field_keyword_05: NotRequired[str]  # country
    field_keyword_08: NotRequired[str]  # category
    field_keyword_17: NotRequired[str]  # work type
    field_keyword_18: NotRequired[str]  # level
    field_keyword_19: NotRequired[str]  # location
    field_keyword_20: NotRequired[str]  # legal entity


class IBMHit(TypedDict):
    _id: NotRequired[str]
    _source: NotRequired[IBMJobSource]


class IBMTotal(TypedDict):
    value: NotRequired[int]
    relation: NotRequired[str]


class IBMHitsObject(TypedDict):
    hits: NotRequired[list[IBMHit]]
    total: NotRequired[IBMTotal]


class IBMResponse(TypedDict):
    hits: NotRequired[IBMHitsObject]


class IBMScraper(BaseScraper):
    source = "ibm"

    def fetch_jobs(self) -> list[Job]:
        session = make_session()
        session.headers.update(
            {
                "Content-Type": "application/json",
                "Referer": "https://www.ibm.com/",
                "Accept": "application/json, text/plain, */*",
            }
        )

        jobs: list[Job] = []
        empty_must: list[dict[str, str]] = []
        for page in range(MAX_PAGES):
            offset = page * PAGE_SIZE
            # Payload mirrors the exact shape the IBM careers page sends
            payload = {
                "appId": "careers",
                "scopes": ["careers2"],
                "query": {"bool": {"must": empty_must}},
                "size": PAGE_SIZE,
                "from": offset,
                "sort": [{"_score": "desc"}, {"pageviews": "desc"}],
                "lang": "en",
                "sm": {"query": "", "lang": "en"},
                "_source": [
                    "_id",
                    "title",
                    "url",
                    "description",
                    "field_keyword_17",
                    "field_keyword_08",
                    "field_keyword_18",
                    "field_keyword_19",
                ],
            }

            log.debug("%s: page=%d offset=%d", self.name, page, offset)
            resp = session.post(API, json=payload, timeout=TIMEOUT)
            resp.raise_for_status()

            raw: object = resp.json()
            if not isinstance(raw, dict):
                log.warning("%s: unexpected response type %s", self.name, type(raw))
                break
            data = cast(IBMResponse, raw)

            hits_obj: IBMHitsObject = data.get("hits") or {}
            hits: list[IBMHit] = hits_obj.get("hits") or []
            total_obj: IBMTotal = hits_obj.get("total") or {}
            total: int = total_obj.get("value") or 0

            log.debug(
                "%s: page=%d returned %d hits (total=%d)",
                self.name,
                page,
                len(hits),
                total,
            )

            for hit in hits:
                jobs.append(self._to_job(hit))

            if not hits or offset + len(hits) >= total:
                break

        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    def _to_job(self, hit: IBMHit) -> Job:
        src: IBMJobSource = hit.get("_source") or {}
        job_id = hit.get("_id") or ""
        location = src.get("field_keyword_19") or ""
        return Job(
            id=f"{self.slug}:{job_id}",
            company=self.name,
            title=(src.get("title") or "").strip(),
            location=location,
            locations=[location] if location else [],
            url=src.get("url") or "",
            posted_on="",
            posted_days=None,
            source=self.source,
            description=(src.get("description") or "").strip(),
        )
