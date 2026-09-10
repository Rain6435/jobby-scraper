"""Oracle Cloud HCM Candidate Experience scraper.

Candidate-facing career portals expose the public recruiting CE API:
    GET https://<tenant>/hcmRestApi/resources/latest/recruitingCEJobRequisitions?finder=findReqs;siteNumber=<site>&limit=25&offset=0&onlyData=true
Config:
{"board": "oraclecloud", "tenant": "<subdomain_or_host>", "site_number": "<site_id>"}
"""

from __future__ import annotations

import logging
from typing import NotRequired, TypedDict, cast

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import posted_days_from_iso, relative_day_text
from scraper.config_types import OracleCloudConfig
from scraper.models import Job
from scraper.text import html_to_text

API_PATH = "/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
TIMEOUT = 30
PAGE_LIMIT = 25
MAX_PAGES = 100

log = logging.getLogger("scraper.oraclecloud")


class OracleJobItem(TypedDict):
    Id: NotRequired[str | int]
    Title: NotRequired[str]
    PrimaryLocation: NotRequired[str | None]
    PostedDate: NotRequired[str | None]
    ExternalDescriptionStr: NotRequired[str | None]
    ShortDescriptionStr: NotRequired[str | None]
    JobFamily: NotRequired[str | None]
    WorkLocation: NotRequired[str | None]
    requisitionList: NotRequired[list[OracleJobItem]]


class OracleResponse(TypedDict):
    items: NotRequired[list[OracleJobItem]]
    count: NotRequired[int]
    hasMore: NotRequired[bool]
    limit: NotRequired[int]
    offset: NotRequired[int]
    totalResults: NotRequired[int]


class OracleCloudScraper(BaseScraper):
    source = "oraclecloud"

    def fetch_jobs(self) -> list[Job]:
        cfg: OracleCloudConfig = cast(OracleCloudConfig, self.company)
        tenant = cfg["tenant"]
        site_number = cfg.get("site_number", "CX")

        host = tenant if "oraclecloud.com" in tenant else f"{tenant}.oraclecloud.com"
        base_url = f"https://{host}{API_PATH}"

        session = make_session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            }
        )

        jobs: list[Job] = []
        offset = 0

        for _ in range(MAX_PAGES):
            finder_param = f"findReqs;siteNumber={site_number}"
            if offset > 0:
                finder_param += f",offset={offset}"
            params = {
                "finder": finder_param,
                "limit": str(PAGE_LIMIT),
                "offset": str(offset),
                "onlyData": "true",
                "expand": "requisitionList",
            }

            log.debug("%s: fetching page offset %d", self.name, offset)
            resp = session.get(base_url, params=params, timeout=TIMEOUT)
            resp.raise_for_status()

            raw_json: object = resp.json()
            if not isinstance(raw_json, dict):
                break

            data = cast(OracleResponse, raw_json)
            items = data.get("items", [])
            if not items:
                break

            job_items: list[OracleJobItem] = []
            for item in items:
                if "requisitionList" in item and item["requisitionList"]:
                    job_items.extend(item["requisitionList"])
                elif "Title" in item or "Id" in item:
                    job_items.append(item)

            if not job_items:
                break

            for item in job_items:
                job_id = str(item.get("Id", "")).strip()
                if not job_id:
                    continue

                title = (item.get("Title") or "").strip()
                location = (item.get("PrimaryLocation") or item.get("WorkLocation") or "").strip()
                posted_iso = item.get("PostedDate") or ""
                posted_days = posted_days_from_iso(posted_iso)

                desc_html = (
                    item.get("ExternalDescriptionStr") or item.get("ShortDescriptionStr") or ""
                )
                description = html_to_text(desc_html)

                job_url = (
                    f"https://{host}/hcmUI/CandidateExperience/en/sites/{site_number}/job/{job_id}"
                )

                jobs.append(
                    Job(
                        id=f"{self.slug}:{job_id}",
                        company=self.name,
                        title=title,
                        location=location,
                        locations=[location] if location else [],
                        url=job_url,
                        posted_on=relative_day_text(posted_days),
                        posted_days=posted_days,
                        source=self.source,
                        description=description,
                    )
                )

            if any("requisitionList" in item for item in items):
                offset += len(job_items)
                if len(job_items) < PAGE_LIMIT:
                    break
            else:
                has_more = data.get("hasMore")
                count = data.get("count", len(items))
                offset += count

                if (
                    has_more is False
                    or (has_more is None and count < PAGE_LIMIT)
                    or len(items) == 0
                ):
                    break

        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs
