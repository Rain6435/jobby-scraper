#!/usr/bin/env python3
"""Probe script for Phenom People career portals (e.g. OpenText, Bell, Air Canada, Cisco).

Phenom People powers career portals for global and Canadian enterprises.
Job data is embedded directly into server-rendered HTML within `phApp.ddo`:
    https://{domain}/{locale}/search-results?from={offset}&s=1

Usage:
    python exploration/explore_phenom.py --url https://careers.opentext.com/us/en
    python exploration/explore_phenom.py --url https://jobs.bell.ca/ca/en
    python exploration/explore_phenom.py --url https://careers.aircanada.com/ca/en
    python exploration/explore_phenom.py --url https://careers.cisco.com/global/en --location "Canada"
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DDO_PATTERN = re.compile(
    r"phApp\.ddo\s*=\s*(\{.*?\});\s*(?:phApp|window|<\/script>)",
    re.DOTALL,
)


def extract_ddo(html: str) -> dict | None:
    match = DDO_PATTERN.search(html)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def fetch_page(search_base: str, offset: int = 0) -> tuple[int, list[dict]]:
    url = f"{search_base}?from={offset}&s=1" if offset > 0 else search_base
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"Error fetching {url}: {exc}", file=sys.stderr)
        return 0, []

    ddo = extract_ddo(html)
    if not ddo:
        return 0, []

    refine = ddo.get("eagerLoadRefineSearch", {})
    total_hits = refine.get("totalHits", 0)
    jobs = refine.get("data", {}).get("jobs", [])
    return total_hits, jobs


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Phenom People career portal")
    parser.add_argument("--url", required=True, help="Base portal URL or search-results URL")
    parser.add_argument("--location", default="", help="Filter by location substring")
    parser.add_argument("--keyword", default="", help="Filter by keyword substring")
    parser.add_argument("--max-pages", type=int, default=10, help="Max pages to fetch (10 jobs/page)")
    parser.add_argument("--details", action="store_true", help="Fetch full detail description for sample jobs")
    args = parser.parse_args()

    url = args.url.rstrip("/")
    if url.endswith("/search-results"):
        portal_base = url[:-len("/search-results")]
        search_base = url
    else:
        portal_base = url
        search_base = f"{url}/search-results"

    print(f"Target portal: {portal_base}")
    print(f"Search endpoint: {search_base}")

    t0 = time.time()
    total_hits, first_jobs = fetch_page(search_base, 0)
    print(f"Reported totalHits: {total_hits}")
    print(f"Page 1 jobs: {len(first_jobs)}")

    all_jobs = list(first_jobs)
    total_pages = min(math.ceil(total_hits / 10), args.max_pages) if total_hits > 0 else 1
    offsets = [p * 10 for p in range(1, total_pages)]

    if offsets:
        print(f"Fetching {len(offsets)} additional pages concurrently...")
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(fetch_page, search_base, offset) for offset in offsets]
            for f in futures:
                _, page_jobs = f.result()
                all_jobs.extend(page_jobs)

    elapsed = time.time() - t0
    print(f"Fetched total {len(all_jobs)} jobs in {elapsed:.2f}s")

    loc_filt = args.location.lower()
    kw_filt = args.keyword.lower()

    filtered = []
    for j in all_jobs:
        title = j.get("title", "")
        loc = j.get("location", "")
        multi_loc = j.get("multi_location", []) or []
        country = j.get("country", "")
        teaser = j.get("descriptionTeaser", "")

        if loc_filt:
            all_loc_str = " ".join([loc, country] + multi_loc).lower()
            if loc_filt not in all_loc_str:
                continue

        if kw_filt:
            search_str = f"{title} {teaser}".lower()
            if kw_filt not in search_str:
                continue

        filtered.append(j)

    print(f"Matches after filtering: {len(filtered)}")
    print("-" * 60)
    for j in filtered[:5]:
        jid = j.get("jobId") or j.get("jobSeqNo")
        jurl = f"{portal_base}/job/{jid}"
        print(f"[{jid}] {j.get('title')}")
        print(f"  Location: {j.get('location')} (Country: {j.get('country')})")
        print(f"  Posted:   {j.get('postedDate')}")
        print(f"  URL:      {jurl}")
        print(f"  Teaser:   {repr(j.get('descriptionTeaser', '')[:120])}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
