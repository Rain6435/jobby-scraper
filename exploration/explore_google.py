"""Interactive CLI exploration script for the Google Careers portal.

Usage:
    python exploration/explore_google.py
    python exploration/explore_google.py --query "deepmind"
    python exploration/explore_google.py --company "DeepMind"
    python exploration/explore_google.py --location "Seattle"
    python exploration/explore_google.py --limit 5
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime

import requests

from scraper.boards.greenhouse import relative_day_text
from scraper.text import html_to_text

BASE_URL = "https://www.google.com/about/careers/applications/jobs/results"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe Google Careers portal")
    parser.add_argument("--query", default="", help="Search query (e.g. software, ai)")
    parser.add_argument("--location", default="", help="Location filter (e.g. Seattle, London)")
    parser.add_argument("--company", default="", help="Company entity (e.g. Google, DeepMind, YouTube)")
    parser.add_argument("--page", type=int, default=1, help="Page number (1-indexed)")
    parser.add_argument("--limit", type=int, default=5, help="Number of items to print")
    args = parser.parse_args()

    params: dict[str, str | int] = {"page": args.page}
    if args.query:
        params["q"] = args.query
    if args.location:
        params["location"] = args.location
    if args.company:
        params["company"] = args.company

    session = requests.Session()
    session.headers.update(HEADERS)

    print(f"Requesting Google careers (page={args.page}, query='{args.query}', company='{args.company}', location='{args.location}')...")
    resp = session.get(BASE_URL, params=params, timeout=20)
    resp.raise_for_status()

    matches = re.findall(
        r"AF_initDataCallback\s*\(\s*\{.*?key:\s*[\'\"](ds:1)[\'\"].*?data:\s*(\[.*?\])\s*,\s*sideChannel:",
        resp.text,
        re.DOTALL,
    )
    if not matches:
        print("Error: Could not locate AF_initDataCallback with key ds:1 in HTML response.")
        return

    data = json.loads(matches[0][1])
    raw_jobs = data[0] if isinstance(data, list) and len(data) > 0 and isinstance(data[0], list) else []
    total_count = data[2] if len(data) > 2 and isinstance(data[2], int) else 0

    print(f"Total matching live jobs: {total_count:,} | Returned on page: {len(raw_jobs)}")
    print("-" * 70)

    for idx, j in enumerate(raw_jobs[: args.limit], start=1):
        job_id = str(j[0])
        title = str(j[1]) if len(j) > 1 and j[1] else ""
        comp = str(j[7]) if len(j) > 7 and j[7] else "Google"

        locs = j[9] if len(j) > 9 and isinstance(j[9], list) else []
        loc_names = [loc[0] for loc in locs if isinstance(loc, list) and len(loc) > 0 and isinstance(loc[0], str)]

        posted_date = ""
        posted_on = ""
        if len(j) > 12 and isinstance(j[12], list) and len(j[12]) > 0 and isinstance(j[12][0], int):
            dt = datetime.fromtimestamp(j[12][0], tz=UTC)
            posted_date = dt.strftime("%Y-%m-%d")
            delta = (datetime.now(tz=UTC) - dt).days
            posted_on = relative_day_text(max(0, delta))

        url = f"https://www.google.com/about/careers/applications/jobs/results/{job_id}"

        # Combine descriptions
        parts: list[str] = []
        if len(j) > 10 and isinstance(j[10], list) and len(j[10]) > 1 and j[10][1]:
            parts.append(str(j[10][1]))
        if len(j) > 3 and isinstance(j[3], list) and len(j[3]) > 1 and j[3][1]:
            parts.append(str(j[3][1]))
        if len(j) > 4 and isinstance(j[4], list) and len(j[4]) > 1 and j[4][1]:
            parts.append(str(j[4][1]))
        desc = html_to_text("\n\n".join(parts))

        print(f"[{idx}] {title}")
        print(f"    ID: {job_id} | Entity: {comp} | Posted: {posted_date} ({posted_on})")
        print(f"    Locations: {loc_names}")
        print(f"    URL: {url}")
        print(f"    Description length: {len(desc):,} chars")
        print()


if __name__ == "__main__":
    main()
