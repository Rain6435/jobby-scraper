"""Shopify in-house careers platform scraper (shopify.com/careers).

Shopify operates an in-house careers platform built on React Router / Remix:
    List: GET https://www.shopify.com/careers
    Detail: GET https://www.shopify.com/careers/{slug}_{uuid}.data

The list page provides the live catalog of open positions, structured
geographic locations (e.g. Remote - Canada, Toronto, Montreal), and titles.
Individual posting detail routes provide the ISO publishedDate and full
job descriptions.

Config entry:
    {"board": "shopify", "name": "Shopify"}
    {"board": "shopify", "name": "Shopify", "location": "Canada"}
    {"board": "shopify", "name": "Shopify", "fetch_details": false}
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from typing import TypedDict, cast

from requests.exceptions import RequestException

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import posted_days_from_iso, relative_day_text
from scraper.models import Job
from scraper.text import html_to_text

BASE_URL = "https://www.shopify.com"
CAREERS_URL = f"{BASE_URL}/careers"
TIMEOUT = 20
DETAIL_WORKERS = 6

log = logging.getLogger("scraper.shopify")


class RawShopifyItem(TypedDict):
    path: str
    slug: str
    id: str
    title: str
    location: str


class ShopifyListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.jobs: list[RawShopifyItem] = []
        self.current_job: RawShopifyItem | None = None
        self.in_h4 = False
        self.in_loc = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if tag == "a" and href and "/careers/" in href:
            if "_" in href:
                slug, _, jid = href.rpartition("/")[-1].rpartition("_")
                if len(jid) == 36:
                    self.current_job = {
                        "path": href,
                        "slug": slug,
                        "id": jid,
                        "title": "",
                        "location": "",
                    }
        elif self.current_job:
            if tag == "h4":
                self.in_h4 = True
            elif tag == "span" and "uppercase" in (attrs_dict.get("class") or ""):
                self.in_loc = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.current_job:
            if self.current_job["title"]:
                self.jobs.append(self.current_job)
            self.current_job = None
        elif tag == "h4":
            self.in_h4 = False
        elif tag == "span":
            self.in_loc = False

    def handle_data(self, data: str) -> None:
        if self.current_job:
            if self.in_h4:
                self.current_job["title"] += data.strip()
            elif self.in_loc:
                self.current_job["location"] += data.strip()


def clean_shopify_location(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("Remote - "):
        sub = raw[len("Remote - ") :].strip()
        return f"Remote, {sub}"
    return raw


def parse_shopify_detail(data: Sequence[object]) -> tuple[str | None, str]:
    pub_date: str | None = None
    for i, item in enumerate(data):
        if item == "publishedDate" and i + 1 < len(data):
            val = data[i + 1]
            if isinstance(val, str) and len(val) == 10 and val[4] == "-":
                pub_date = val
                break

    desc: str = ""
    for i, item in enumerate(data):
        if item in ("descriptionPlain", "descriptionHtml") and i + 1 < len(data):
            val = data[i + 1]
            if isinstance(val, str) and len(val) > len(desc):
                desc = val
    if not desc:
        desc = max((s for s in data if isinstance(s, str)), key=len, default="")

    return pub_date, html_to_text(desc) if desc else ""


class ShopifyScraper(BaseScraper):
    source = "shopify"

    def fetch_jobs(self) -> list[Job]:
        session = make_session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            }
        )

        location_filter = cast(str, self.company.get("location") or "").strip().lower()
        keyword_filter = cast(str, self.company.get("keyword") or "").strip().lower()
        fetch_details = self.company.get("fetch_details")
        if fetch_details is None:
            fetch_details = True

        log.debug("%s: fetching careers page from %s", self.name, CAREERS_URL)
        resp = session.get(CAREERS_URL, timeout=TIMEOUT)
        resp.raise_for_status()

        parser = ShopifyListParser()
        parser.feed(resp.text)

        log.debug("%s: parsed %d postings from HTML", self.name, len(parser.jobs))

        filtered_items: list[RawShopifyItem] = []
        for item in parser.jobs:
            title = item["title"].strip()
            loc_raw = item["location"].strip()
            if not title:
                continue

            if keyword_filter and keyword_filter not in title.lower():
                continue
            if location_filter and location_filter not in loc_raw.lower():
                continue

            filtered_items.append(item)

        log.debug("%s: %d postings after filtering", self.name, len(filtered_items))

        # Optional detail fetching
        details_map: dict[str, tuple[str | None, str]] = {}
        if fetch_details and filtered_items:
            log.debug(
                "%s: fetching details for %d jobs concurrently", self.name, len(filtered_items)
            )

            def _get_detail(path: str) -> tuple[str, str | None, str]:
                url = f"{BASE_URL}{path}.data"
                try:
                    r = session.get(url, timeout=TIMEOUT)
                    r.raise_for_status()
                    d: object = r.json()
                    if isinstance(d, list):
                        pdate, desc = parse_shopify_detail(cast(list[object], d))
                        return path, pdate, desc
                except (RequestException, ValueError) as err:
                    log.warning("%s: failed to fetch detail for %s: %s", self.name, path, err)
                return path, None, ""

            with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
                for path, pdate, desc in executor.map(
                    _get_detail, [it["path"] for it in filtered_items]
                ):
                    details_map[path] = (pdate, desc)

        jobs: list[Job] = []
        for item in filtered_items:
            jid = item["id"]
            title = item["title"].strip()
            clean_loc = clean_shopify_location(item["location"])
            url = f"{BASE_URL}{item['path']}"

            pub_date, desc = details_map.get(item["path"], (None, ""))

            posted_days: int | None = None
            posted_date: str | None = None
            posted_on: str = ""
            if pub_date:
                posted_date = pub_date
                posted_days = posted_days_from_iso(pub_date)
                if posted_days is not None:
                    posted_on = relative_day_text(posted_days)

            jobs.append(
                Job(
                    id=f"{self.slug}:{jid}",
                    company=self.name,
                    title=title,
                    location=clean_loc,
                    locations=[clean_loc] if clean_loc else [],
                    url=url,
                    posted_on=posted_on,
                    posted_days=posted_days,
                    posted_date=posted_date,
                    source=self.source,
                    description=desc,
                )
            )

        log.debug("%s: successfully built %d Job objects", self.name, len(jobs))
        return jobs
