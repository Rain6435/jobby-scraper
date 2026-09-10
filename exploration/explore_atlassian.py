#!/usr/bin/env python3
"""Probe script for Atlassian's custom Careers API.

Atlassian serves all open job postings in a single JSON payload from:
https://www.atlassian.com/endpoint/careers/listings

No authentication, tokens, or sessions required.
Includes rich HTML descriptions, responsibilities, qualifications, compensation,
structured locations, category taxonomy, and posting update dates.

Usage:
    python exploration/explore_atlassian.py
    python exploration/explore_atlassian.py --category Engineering
    python exploration/explore_atlassian.py --location "Remote"
    python exploration/explore_atlassian.py --keyword "Python"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone

ATLASSIAN_LISTINGS_URL = "https://www.atlassian.com/endpoint/careers/listings"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def clean_atlassian_location(raw: str) -> str:
    """Clean Atlassian's verbose location string into a concise, standard format.

    Examples:
        'Austin - United States -   Austin, Texas 78702 United States' -> 'Austin, United States'
        'Remote - Americas - Remote' -> 'Remote, Americas'
        'Remote - Remote' -> 'Remote'
        'Mountain View - United States or Remote - ...' -> 'Mountain View, United States or Remote'
    """
    parts = [re.sub(r"\s+", " ", p).strip() for p in raw.split(" - ") if p.strip()]
    if not parts:
        return "Remote"
    if len(parts) == 1:
        return parts[0]
    if parts[0].lower() == "remote":
        if len(parts) > 1 and parts[1].lower() != "remote":
            return f"Remote, {parts[1]}"
        return "Remote"

    city = parts[0]
    country = parts[1] if len(parts) > 1 else ""
    if country and country.lower() != city.lower():
        return f"{city}, {country}"
    return city


def parse_atlassian_date(date_str: str | None) -> datetime | None:
    """Parse Atlassian updatedDate string, e.g. '2026-09-08 01:00 AM'."""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str.strip(), "%Y-%m-%d %I:%M %p")
        return dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def fetch_atlassian_listings() -> list[dict]:
    """Fetch all open listings from Atlassian's careers endpoint."""
    req = urllib.request.Request(
        ATLASSIAN_LISTINGS_URL,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe Atlassian Careers API")
    parser.add_argument("--category", help="Filter by category (e.g. Engineering, Sales)")
    parser.add_argument("--location", help="Filter by location substring (e.g. Remote, Austin)")
    parser.add_argument("--keyword", help="Filter by keyword in title")
    parser.add_argument("--limit", type=int, default=10, help="Max jobs to print (default 10)")
    parser.add_argument("--json", action="store_true", help="Dump sample job as JSON")
    args = parser.parse_args()

    print(f"Fetching listings from {ATLASSIAN_LISTINGS_URL}...")
    try:
        listings = fetch_atlassian_listings()
    except Exception as exc:
        print(f"Error fetching listings: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Fetched {len(listings)} total openings.")

    filtered = listings
    if args.category:
        filtered = [
            j for j in filtered
            if args.category.lower() in (j.get("category") or "").lower()
        ]
    if args.location:
        filtered = [
            j for j in filtered
            if any(args.location.lower() in loc.lower() for loc in j.get("locations", []))
        ]
    if args.keyword:
        filtered = [
            j for j in filtered
            if args.keyword.lower() in (j.get("title") or "").lower()
        ]

    print(f"Matching jobs after filters: {len(filtered)}\n")

    if args.json and filtered:
        print(json.dumps(filtered[0], indent=2))
        return

    now = datetime.now(timezone.utc)
    for i, j in enumerate(filtered[:args.limit], 1):
        job_id = j.get("id")
        title = j.get("title", "Unknown Title")
        category = j.get("category", "")
        raw_locs = j.get("locations", [])
        cleaned_locs = [clean_atlassian_location(loc) for loc in raw_locs]
        portal_url = j.get("portalJobPost", {}).get("portalUrl") or j.get("applyUrl", "")
        updated_raw = j.get("portalJobPost", {}).get("updatedDate")
        dt = parse_atlassian_date(updated_raw)
        days_ago = (now - dt).days if dt else "?"

        print(f"[{i}] {title} (ID: {job_id})")
        print(f"    Category: {category}")
        print(f"    Locations: {', '.join(cleaned_locs)}")
        print(f"    Updated: {updated_raw} ({days_ago} days ago)")
        print(f"    URL: {portal_url}")
        print()


if __name__ == "__main__":
    main()
