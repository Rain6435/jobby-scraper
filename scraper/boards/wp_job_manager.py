"""Shared parsing helpers for boards backed by the WP Job Manager WordPress
plugin's standard `?feed=job_feed` RSS output.

Extracted after idc_career_centre.py and cip_planning.py turned out to be
the same underlying plugin/feed shape on two different WordPress sites
(idcanada.org, cip-icu.ca) — confirmed live: identical `<item>` structure,
identical `<job_listing:company>`/`<job_listing:location>` namespaced
elements, identical `<content:encoded>` HTML body, identical `p=<id>`
`<guid>` pattern. A third WP Job Manager site would only need its own
`FEED_URL` + a thin `BaseScraper` subclass reusing `parse_wp_job_manager_feed`.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape

from scraper.boards.greenhouse import relative_day_text
from scraper.models import Job
from scraper.text import html_to_text

_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.DOTALL)
_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL)
_LINK_RE = re.compile(r"<link>(.*?)</link>", re.DOTALL)
_PUBDATE_RE = re.compile(r"<pubDate>(.*?)</pubDate>", re.DOTALL)
_CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)
_COMPANY_RE = re.compile(r"<job_listing:company>(.*?)</job_listing:company>", re.DOTALL)
_LOCATION_RE = re.compile(r"<job_listing:location>(.*?)</job_listing:location>", re.DOTALL)
_CONTENT_RE = re.compile(r"<content:encoded>(.*?)</content:encoded>", re.DOTALL)
_GUID_ID_RE = re.compile(r"p=(\d+)")


def _text(pattern: re.Pattern[str], item: str) -> str:
    match = pattern.search(item)
    if not match:
        return ""
    raw = match.group(1).strip()
    cdata = _CDATA_RE.match(raw)
    return unescape(cdata.group(1).strip() if cdata else raw)


def _posted_days_from_rfc2822(pub_date: str) -> int | None:
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


def parse_wp_job_manager_feed(
    feed_xml: str, source: str, slug: str, default_company: str
) -> list[Job]:
    """Parse a WP Job Manager `job_feed` RSS response into normalized Jobs.

    default_company is used when an item has no `<job_listing:company>`
    (matches other boards' fall-back-to-board-name convention)."""
    jobs: list[Job] = []
    for item in _ITEM_RE.findall(feed_xml):
        link = _text(_LINK_RE, item)
        id_match = _GUID_ID_RE.search(item)
        if not link or not id_match:
            continue
        location = _text(_LOCATION_RE, item)
        posted_days = _posted_days_from_rfc2822(_text(_PUBDATE_RE, item))
        jobs.append(
            Job(
                id=f"{slug}:{id_match.group(1)}",
                company=_text(_COMPANY_RE, item) or default_company,
                title=_text(_TITLE_RE, item),
                location=location,
                locations=[location] if location else [],
                url=link,
                posted_on=relative_day_text(posted_days),
                posted_days=posted_days,
                source=source,
                description=html_to_text(_text(_CONTENT_RE, item)),
            )
        )
    return jobs
