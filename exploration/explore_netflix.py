"""Interactive CLI exploration script for the Netflix Careers API.

Usage:
    python exploration/explore_netflix.py
    python exploration/explore_netflix.py --query "engineer"
    python exploration/explore_netflix.py --limit 5
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

import requests

SEARCH_URL = "https://explore.jobs.netflix.net/api/apply/v2/jobs"
DETAIL_URL = "https://explore.jobs.netflix.net/api/apply/v2/jobs/{id}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe Netflix Careers API")
    parser.add_argument("--query", default="", help="Keyword or title filter")
    parser.add_argument("--location", default="", help="Location filter")
    parser.add_argument("--limit", type=int, default=5, help="Number of positions to show")
    parser.add_argument("--details", action="store_true", help="Fetch full description for first item")
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update(HEADERS)

    params: dict[str, object] = {
        "domain": "netflix.com",
        "start": 0,
        "num": args.limit,
    }
    if args.query:
        params["query"] = args.query
    if args.location:
        params["location"] = args.location

    print(f"Querying Netflix careers (query='{args.query}', location='{args.location}')...")
    resp = session.get(SEARCH_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    count = data.get("count", 0)
    positions = data.get("positions", [])

    print(f"Total live postings: {count:,} | Returned: {len(positions)}")
    print("-" * 70)

    for idx, pos in enumerate(positions, start=1):
        pid = pos.get("id")
        name = pos.get("name")
        locations = pos.get("locations") or [pos.get("location")]
        dept = pos.get("department")
        t_create = pos.get("t_create")
        created_str = ""
        if t_create:
            dt = datetime.fromtimestamp(t_create, tz=UTC)
            created_str = dt.strftime("%Y-%m-%d")

        url = pos.get("canonicalPositionUrl") or f"https://explore.jobs.netflix.net/careers/job/{pid}"

        print(f"[{idx}] {name}")
        print(f"    ID: {pid} | Dept: {dept} | Posted: {created_str}")
        print(f"    Locations: {locations}")
        print(f"    URL: {url}")
        print()

    if args.details and positions:
        first_id = positions[0].get("id")
        print(f"Fetching full details for ID {first_id}...")
        d_resp = session.get(DETAIL_URL.format(id=first_id), params={"domain": "netflix.com"}, timeout=15)
        d_resp.raise_for_status()
        d_data = d_resp.json()
        print("Detail keys:", list(d_data.keys()))
        print("Description preview (first 300 chars):")
        print(d_data.get("job_description", "")[:300])


if __name__ == "__main__":
    main()
