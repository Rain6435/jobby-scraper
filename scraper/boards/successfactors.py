"""SAP SuccessFactors job board scraper.

Supports Career Site Builder (CSB) and SuccessFactors RSS feeds:
    GET https://<domain>/services/rss/job/?locale=en_US
Config:
{"board": "successfactors", "company": "<company_id>", "domain": "<custom_domain>"}
"""

from __future__ import annotations

import email.utils
import logging
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import cast

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import relative_day_text
from scraper.config_types import SuccessFactorsConfig
from scraper.models import Job
from scraper.text import html_to_text

TIMEOUT = 30
log = logging.getLogger("scraper.successfactors")


def posted_days_from_rfc(date_str: str) -> int | None:
    """Parse RFC 2822 / 822 date string (e.g. 'Mon, 02 Mar 2026 12:00:00 GMT') to days ago."""
    if not date_str:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        now = datetime.now(UTC)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        days = (now - dt).days
        return max(0, days)
    except Exception:
        return None


class SuccessFactorsScraper(BaseScraper):
    source = "successfactors"

    def fetch_jobs(self) -> list[Job]:
        cfg: SuccessFactorsConfig = cast(SuccessFactorsConfig, self.company)
        company = cfg["company"]
        domain = cfg.get("domain") or f"jobs.{company}.com"

        url = f"https://{domain}/services/rss/job/?locale=en_US"

        session = make_session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            }
        )

        log.debug("%s: fetching RSS feed from %s", self.name, url)
        resp = session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()

        jobs: list[Job] = []
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as e:
            log.warning("%s: failed to parse RSS XML: %s", self.name, e)
            return []

        channel = root.find("channel")
        items = channel.findall("item") if channel is not None else root.findall(".//item")

        for item in items:
            title_el = item.find("title")
            link_el = item.find("link")
            guid_el = item.find("guid")
            pubdate_el = item.find("pubDate")
            desc_el = item.find("description")
            category_el = item.find("category")
            location_el = item.find("location")

            title = (title_el.text or "").strip() if title_el is not None else ""
            link = (link_el.text or "").strip() if link_el is not None else ""
            guid = (guid_el.text or "").strip() if guid_el is not None else ""
            pub_date = (pubdate_el.text or "").strip() if pubdate_el is not None else ""
            desc_html = (desc_el.text or "").strip() if desc_el is not None else ""
            location = (location_el.text or "").strip() if location_el is not None else ""
            category = (category_el.text or "").strip() if category_el is not None else ""

            raw_id = guid or link or title
            if not raw_id or not title:
                continue

            # Strip URL prefix and query params for id if guid was a full URL
            clean_id = raw_id.split("?")[0].rstrip("/").split("/")[-1] if "/" in raw_id else raw_id
            if not clean_id:
                clean_id = raw_id

            posted_days = posted_days_from_rfc(pub_date)
            description = html_to_text(desc_html)

            # If location wasn't in explicit tag, fallback to category or parse from title
            loc_str = location or category
            if not loc_str:
                m = re.search(r"\(([^()]+)\)\s*$", title)
                if m:
                    loc_str = m.group(1).strip()
                    title = re.sub(r"\s*\([^()]+\)\s*$", "", title).strip()

            jobs.append(
                Job(
                    id=f"{self.slug}:{clean_id}",
                    company=self.name,
                    title=title,
                    location=loc_str,
                    locations=[loc_str] if loc_str else [],
                    url=link,
                    posted_on=relative_day_text(posted_days),
                    posted_days=posted_days,
                    source=self.source,
                    description=description,
                )
            )

        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs
