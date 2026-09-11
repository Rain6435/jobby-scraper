#!/usr/bin/env python3
"""Probe script for Jibe (iCIMS Talent Acquisition) enterprise portals (e.g. GitHub, PepsiCo, Costco).

Jibe powers candidate search portals for enterprise employers:
    https://{tenant}.jibeapply.com/api/jobs?page={page}&limit={limit}
    https://{custom_domain}/api/jobs?page={page}&limit={limit}

Usage:
    python exploration/explore_jibe.py --tenant githubinc
    python exploration/explore_jibe.py --tenant pepsico
    python exploration/explore_jibe.py --url https://www.github.careers
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def fetch_jibe_page(base_url: str, page: int = 1, limit: int = 50) -> tuple[int, list[dict]]:
    api_url = f"{base_url.rstrip('/')}/api/jobs?page={page}&limit={limit}"
    req = urllib.request.Request(
        api_url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"Error fetching {api_url}: {exc}", file=sys.stderr)
        return 0, []

    total = data.get("totalCount", 0)
    raw_jobs = data.get("jobs", [])
    jobs = [j.get("data", {}) for j in raw_jobs if isinstance(j, dict)]
    return total, jobs


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe Jibe enterprise career portals")
    parser.add_argument("--tenant", help="Jibe tenant subdomain, e.g. 'githubinc', 'pepsico'")
    parser.add_argument("--url", help="Full custom career base URL, e.g. 'https://www.github.careers'")
    parser.add_argument("--limit", type=int, default=10, help="Max jobs to fetch/display")
    args = parser.parse_args()

    if args.url:
        base_url = args.url.rstrip("/")
    elif args.tenant:
        base_url = f"https://{args.tenant}.jibeapply.com"
    else:
        parser.error("Either --tenant or --url must be specified.")

    print(f"Target Jibe portal: {base_url}")
    t0 = time.time()
    total, jobs = fetch_jibe_page(base_url, page=1, limit=args.limit)
    elapsed = time.time() - t0

    print(f"Reported totalCount: {total}")
    print(f"Fetched {len(jobs)} jobs in {elapsed:.2f}s")
    print("-" * 60)

    for j in jobs[: args.limit]:
        req_id = j.get("req_id") or j.get("slug", "unknown")
        title = j.get("title", "Untitled")
        loc = j.get("location_name") or j.get("full_location", "Unknown")
        date = j.get("create_date") or j.get("posted_date", "No date")
        canonical = j.get("canonical_url") or j.get("meta_data", {}).get("canonical_url", "")
        print(f"[{req_id}] {title}")
        print(f"  Location: {loc}")
        print(f"  Posted:   {date}")
        print(f"  URL:      {canonical}")
        desc = j.get("description", "")[:120].replace("\n", " ")
        print(f"  Teaser:   {repr(desc)}")
        print()


if __name__ == "__main__":
    main()
