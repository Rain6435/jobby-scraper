"""GovernmentJobs (NEOGOV) public RSS job feed scraper.

One unauthenticated GET returns every open position for an agency as RSS 2.0:
    GET https://agency.governmentjobs.com/<agency>/jobfeed.cfm
Root <rss><channel> holds repeated <item> children: title, link, guid,
pubDate, description (HTML), job:location / location. Config:
{"board": "governmentjobs", "agency": "<agency_slug>"}.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from typing import cast

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import relative_day_text
from scraper.config_types import GovernmentJobsConfig
from scraper.models import Job
from scraper.text import html_to_text

API = "https://agency.governmentjobs.com/jobfeed_v2.cfm?agency={agency}"
TIMEOUT = 30

log = logging.getLogger("scraper.governmentjobs")

_ITEM_RE = re.compile(r"<item\b.*?>(.*?)</item>", re.DOTALL)
_TITLE_RE = re.compile(r"<title\b.*?>(.*?)</title>", re.DOTALL)
_LINK_RE = re.compile(r"<link\b.*?>(.*?)</link>", re.DOTALL)
_GUID_RE = re.compile(r"<guid\b.*?>(.*?)</guid>", re.DOTALL)
_PUBDATE_RE = re.compile(r"<pubDate\b.*?>(.*?)</pubDate>", re.DOTALL)
_LOCATION_RE = re.compile(
    r"<(?:joblisting:|job:)?location\b.*?>(.*?)</(?:joblisting:|job:)?location>", re.DOTALL
)
_DESCRIPTION_RE = re.compile(
    r"<(?:description|content:encoded)\b.*?>(.*?)</(?:description|content:encoded)>", re.DOTALL
)
_CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)
_JOB_ID_RE = re.compile(r"jobId=(\d+)|/jobs/(\d+)")


def _extract_text(pattern: re.Pattern[str], item: str) -> str:
    match = pattern.search(item)
    if not match:
        return ""
    raw = match.group(1).strip()
    cdata = _CDATA_RE.match(raw)
    return unescape(cdata.group(1).strip() if cdata else raw)


def posted_days_from_rfc2822(pub_date: str) -> int | None:
    if not pub_date:
        return None
    try:
        dt = parsedate_to_datetime(pub_date)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - dt
    return max(delta.days, 0)


class GovernmentJobsScraper(BaseScraper):
    source = "governmentjobs"

    def fetch_jobs(self) -> list[Job]:
        cfg: GovernmentJobsConfig = cast(GovernmentJobsConfig, self.company)
        agency = cfg["agency"]
        session = make_session()
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/xml, text/xml"})

        log.debug("%s: fetching job list for agency=%s", self.name, agency)
        resp = session.get(API.format(agency=agency), timeout=TIMEOUT)
        resp.raise_for_status()

        feed_xml = resp.text
        items = _ITEM_RE.findall(feed_xml)
        log.debug("%s: %d items returned", self.name, len(items))

        jobs: list[Job] = []
        for item in items:
            link = _extract_text(_LINK_RE, item)
            guid = _extract_text(_GUID_RE, item)

            job_id = self._extract_job_id(guid, link)
            if not job_id:
                continue

            loc_str = _extract_text(_LOCATION_RE, item)
            locations = [loc_str] if loc_str else []
            pub_date = _extract_text(_PUBDATE_RE, item)
            posted_days = posted_days_from_rfc2822(pub_date)
            title = _extract_text(_TITLE_RE, item)
            desc_html = _extract_text(_DESCRIPTION_RE, item)

            jobs.append(
                Job(
                    id=f"{self.slug}:{job_id}",
                    company=self.name,
                    title=title,
                    location=locations[0] if locations else "",
                    locations=locations,
                    url=link or guid,
                    posted_on=relative_day_text(posted_days),
                    posted_days=posted_days,
                    source=self.source,
                    description=html_to_text(desc_html),
                )
            )

        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    @staticmethod
    def _extract_job_id(guid: str, link: str) -> str:
        for s in (guid, link):
            m = _JOB_ID_RE.search(s)
            if m:
                return m.group(1) or m.group(2)
        if guid and not guid.startswith("http"):
            return guid
        return ""
