#!/usr/bin/env python3
"""Probe script for Shopify's in-house careers platform.

Shopify hosts its careers site at https://www.shopify.com/careers
and serves job detail and posting metadata via React Router .data routes:
    https://www.shopify.com/careers/{slug}_{uuid}.data

Usage:
    python exploration/explore_shopify.py
    python exploration/explore_shopify.py --location "Canada"
    python exploration/explore_shopify.py --details
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser

BASE_URL = "https://www.shopify.com"
CAREERS_URL = f"{BASE_URL}/careers"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class ShopifyListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.jobs: list[dict[str, str]] = []
        self.current_job: dict[str, str] | None = None
        self.in_h4 = False
        self.in_loc = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "a" and "/careers/" in attrs_dict.get("href", ""):
            href = attrs_dict["href"]
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
        sub = raw[len("Remote - "):].strip()
        return f"Remote, {sub}"
    return raw


def fetch_shopify_detail(path: str) -> tuple[str | None, str]:
    url = f"{BASE_URL}{path}.data"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    pub_date = None
    for i, item in enumerate(data):
        if item == "publishedDate" and i + 1 < len(data):
            val = data[i + 1]
            if isinstance(val, str) and len(val) == 10 and val[4] == "-":
                pub_date = val
                break

    desc = ""
    for i, item in enumerate(data):
        if item in ("descriptionPlain", "descriptionHtml") and i + 1 < len(data):
            val = data[i + 1]
            if isinstance(val, str) and len(val) > len(desc):
                desc = val
    if not desc:
        desc = max((s for s in data if isinstance(s, str)), key=len, default="")

    return pub_date, desc


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe Shopify Careers")
    parser.add_argument("--location", help="Filter by location substring")
    parser.add_argument("--details", action="store_true", help="Fetch per-job detail and date")
    parser.add_argument("--limit", type=int, default=10, help="Max jobs to print")
    args = parser.parse_args()

    print(f"Fetching {CAREERS_URL}...")
    req = urllib.request.Request(CAREERS_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="ignore")

    p = ShopifyListParser()
    p.feed(html)
    print(f"Found {len(p.jobs)} total openings.")

    filtered = p.jobs
    if args.location:
        filtered = [
            j for j in filtered
            if args.location.lower() in j["location"].lower()
        ]
    print(f"Matching openings: {len(filtered)}\n")

    for i, j in enumerate(filtered[:args.limit], 1):
        url = f"{BASE_URL}{j['path']}"
        loc = clean_shopify_location(j["location"])
        print(f"[{i}] {j['title']}")
        print(f"    ID: {j['id']}")
        print(f"    Location: {loc}")
        print(f"    URL: {url}")
        if args.details:
            date, desc = fetch_shopify_detail(j["path"])
            print(f"    Date: {date}")
            print(f"    Desc preview: {desc[:120].strip()}...")
        print()


if __name__ == "__main__":
    main()
