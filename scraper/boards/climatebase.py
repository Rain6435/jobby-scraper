"""Climatebase job board scraper (climatebase.org).

Not a per-employer integration, like usajobs — one config entry covers the
whole board's search index. Backed by a public, unauthenticated Algolia
search-only key (confirmed live via the site's own frontend network calls —
search-only keys are Algolia's intended public/embedded mechanism, distinct
from admin keys, so calling it directly is not a ToS-adjacent workaround):

    POST https://8psnffqtxq-dsn.algolia.net/1/indexes/Job_production/query
    Headers: x-algolia-application-id: 8PSNFFQTXQ
             x-algolia-api-key: d2ebe27d3cc3d35fea04da7b1b0718a8

One query per keyword in `keywords` (config), each filtered to
`active:true` + `countries:Canada`, paginated at 100/page, deduped by id
across keywords afterward (the same job can match more than one keyword).
Config: {"board": "climatebase", "name": "...", "keywords": ["...", ...]}.
No credentials needed — this is this project's first keyless-but-3rd-party
board scraper backed by a vendor (Algolia) rather than the job board's own
first-party API; if Algolia ever rotates this key, requests will 403 and
fetch_jobs() degrades the same as any other board-scrape failure (logs and
returns []).

Each hit has id, title, locations[] ("City, Region, CC"), countries[]
("Canada"), how_to_apply (the real posting URL — not a "url"/"link" field,
confirmed by requesting attributesToRetrieve=["*"] against the live index),
name_of_employer, description (HTML, base64-embedded images and all —
html_to_text's tag-stripping handles this fine, no special-casing needed),
activation_date (ISO-8601 with trailing "Z", same shape posted_days_from_iso
already parses for other boards).
"""

from __future__ import annotations

import json
import logging
from typing import NotRequired, TypedDict, cast

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import posted_days_from_iso, relative_day_text
from scraper.config_types import ClimatebaseConfig
from scraper.models import Job
from scraper.text import html_to_text

APP_ID = "8PSNFFQTXQ"
API_KEY = "d2ebe27d3cc3d35fea04da7b1b0718a8"
API = f"https://{APP_ID.lower()}-dsn.algolia.net/1/indexes/Job_production/query"
HITS_PER_PAGE = 100
MAX_PAGES = 5  # safety cap per keyword, ~500 jobs
TIMEOUT = 30

ATTRIBUTES = [
    "id",
    "title",
    "locations",
    "countries",
    "how_to_apply",
    "name_of_employer",
    "description",
    "activation_date",
    "sectors",
]

log = logging.getLogger("scraper.climatebase")


class ClimatebaseHit(TypedDict):
    id: NotRequired[str]
    title: NotRequired[str]
    locations: NotRequired[list[str]]
    countries: NotRequired[list[str]]
    how_to_apply: NotRequired[str]
    name_of_employer: NotRequired[str]
    description: NotRequired[str]
    activation_date: NotRequired[str]


class ClimatebaseSearchResponse(TypedDict):
    hits: NotRequired[list[ClimatebaseHit]]
    nbPages: NotRequired[int]


class ClimatebaseScraper(BaseScraper):
    source = "climatebase"

    def fetch_jobs(self) -> list[Job]:
        cfg: ClimatebaseConfig = cast(ClimatebaseConfig, self.company)
        keywords: list[str] = cfg.get("keywords") or [""]
        session = make_session()
        session.headers.update(
            {
                "x-algolia-application-id": APP_ID,
                "x-algolia-api-key": API_KEY,
                "content-type": "application/x-www-form-urlencoded",
            }
        )

        by_id: dict[str, Job] = {}
        for keyword in keywords:
            for page in range(MAX_PAGES):
                log.debug("%s: keyword=%r page=%d", self.name, keyword, page)
                body = json.dumps(
                    {
                        "query": keyword,
                        "page": page,
                        "hitsPerPage": HITS_PER_PAGE,
                        "facetFilters": ["active:true", "countries:Canada"],
                        "attributesToRetrieve": ATTRIBUTES,
                    }
                )
                resp = session.post(API, data=body, timeout=TIMEOUT)
                resp.raise_for_status()
                data: ClimatebaseSearchResponse = resp.json()
                hits = data.get("hits", [])
                log.debug(
                    "%s: keyword=%r page=%d returned %d hits",
                    self.name,
                    keyword,
                    page,
                    len(hits),
                )
                for hit in hits:
                    job = self._to_job(hit)
                    by_id[job.id] = job
                if page + 1 >= data.get("nbPages", 0) or not hits:
                    break

        jobs = list(by_id.values())
        log.debug(
            "%s: fetched %d unique jobs across %d keyword(s)",
            self.name,
            len(jobs),
            len(keywords),
        )
        return jobs

    def _to_job(self, hit: ClimatebaseHit) -> Job:
        locations = [loc for loc in (hit.get("locations") or []) if loc]
        posted_days = posted_days_from_iso(hit.get("activation_date") or "")
        return Job(
            id=f"{self.slug}:{hit.get('id', '')}",
            company=hit.get("name_of_employer") or self.name,
            title=(hit.get("title") or "").strip(),
            location=locations[0] if locations else "",
            locations=locations,
            url=hit.get("how_to_apply") or "",
            posted_on=relative_day_text(posted_days),
            posted_days=posted_days,
            source=self.source,
            description=html_to_text(hit.get("description") or ""),
        )
