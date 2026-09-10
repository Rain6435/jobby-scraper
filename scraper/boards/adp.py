"""ADP Workforce Now Recruitment scraper.

Queries the public career center static requisition feed:
    GET https://workforcenow.adp.com/mascsr/default/careercenter/public/static/v1/reqs?cid=<cid>&ccId=<cc_id>&lang=en_US
Config:
{"board": "adp", "cid": "<client_id>", "cc_id": "<career_center_id>"}
"""

from __future__ import annotations

import logging
from typing import NotRequired, TypedDict, cast

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import posted_days_from_iso, relative_day_text
from scraper.config_types import AdpConfig
from scraper.models import Job
from scraper.text import html_to_text

API_URL = "https://workforcenow.adp.com/mascsr/default/careercenter/public/static/v1/reqs"
CAREER_URL = "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html"
TIMEOUT = 30
DEFAULT_CC_ID = "19000101_000001"

log = logging.getLogger("scraper.adp")


class AdpNameCode(TypedDict):
    shortName: NotRequired[str | None]


class AdpSubdivision(TypedDict):
    codeValue: NotRequired[str | None]


class AdpAddress(TypedDict):
    cityName: NotRequired[str | None]
    countrySubdivisionLevel1: NotRequired[AdpSubdivision | None]
    countryCode: NotRequired[str | None]


class AdpLocation(TypedDict):
    nameCode: NotRequired[AdpNameCode | None]
    address: NotRequired[AdpAddress | None]


class AdpRequisition(TypedDict):
    itemID: NotRequired[str | int]
    requisitionTitle: NotRequired[str]
    postDate: NotRequired[str | None]
    requisitionDescription: NotRequired[str | None]
    requisitionLocations: NotRequired[list[AdpLocation] | None]
    workLevelCode: NotRequired[AdpNameCode | None]


class AdpMeta(TypedDict):
    totalNumber: NotRequired[int]


class AdpResponse(TypedDict):
    jobRequisitions: NotRequired[list[AdpRequisition]]
    meta: NotRequired[AdpMeta]


class AdpScraper(BaseScraper):
    source = "adp"

    def fetch_jobs(self) -> list[Job]:
        cfg: AdpConfig = cast(AdpConfig, self.company)
        cid = cfg["cid"]
        cc_id = cfg.get("cc_id") or DEFAULT_CC_ID

        session = make_session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/plain, */*",
            }
        )

        params = {
            "cid": cid,
            "ccId": cc_id,
            "lang": "en_US",
        }

        log.debug("%s: fetching reqs for cid=%s, ccId=%s", self.name, cid, cc_id)
        resp = session.get(API_URL, params=params, timeout=TIMEOUT)
        resp.raise_for_status()

        if not resp.text.strip():
            log.debug("%s: empty response body returned from ADP", self.name)
            return []

        raw_json: object = resp.json()
        if not isinstance(raw_json, dict):
            return []

        data = cast(AdpResponse, raw_json)
        reqs = data.get("jobRequisitions", [])
        log.debug("%s: %d requisitions returned", self.name, len(reqs))

        jobs: list[Job] = []
        for req in reqs:
            item_id = str(req.get("itemID", "")).strip()
            if not item_id:
                continue

            title = (req.get("requisitionTitle") or "").strip()
            locations = self._parse_locations(req.get("requisitionLocations"))
            primary_loc = locations[0] if locations else ""

            posted_iso = req.get("postDate") or ""
            posted_days = posted_days_from_iso(posted_iso)

            desc_html = req.get("requisitionDescription") or ""
            description = html_to_text(desc_html)

            job_url = f"{CAREER_URL}?cid={cid}&ccId={cc_id}&jobId={item_id}&lang=en_US"

            jobs.append(
                Job(
                    id=f"{self.slug}:{item_id}",
                    company=self.name,
                    title=title,
                    location=primary_loc,
                    locations=locations,
                    url=job_url,
                    posted_on=relative_day_text(posted_days),
                    posted_days=posted_days,
                    source=self.source,
                    description=description,
                )
            )

        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    @staticmethod
    def _parse_locations(raw_locs: list[AdpLocation] | None) -> list[str]:
        if not raw_locs:
            return []
        loc_strings: list[str] = []
        for loc in raw_locs:
            name_code = loc.get("nameCode")
            if name_code:
                short_name = name_code.get("shortName")
                if short_name:
                    s = str(short_name).strip()
                    if s and s not in loc_strings:
                        loc_strings.append(s)
                        continue

            addr = loc.get("address")
            if addr:
                city = (addr.get("cityName") or "").strip()
                sub = addr.get("countrySubdivisionLevel1")
                state = (sub.get("codeValue") or "").strip() if sub else ""
                country = (addr.get("countryCode") or "").strip()
                parts = [p for p in (city, state, country) if p]
                if parts:
                    s = ", ".join(parts)
                    if s not in loc_strings:
                        loc_strings.append(s)
        return loc_strings
