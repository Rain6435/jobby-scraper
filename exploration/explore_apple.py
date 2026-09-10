"""EXPLORATION ONLY — not the real scraper. Probes Apple's careers hydration data.

Run:
    python exploration/explore_apple.py
    python exploration/explore_apple.py --search "machine learning"
    python exploration/explore_apple.py --location "united-states-USA"

Endpoint:
    GET https://jobs.apple.com/en-us/search?page={page}

Documentation:
    See exploration/apple_api.md for full field mappings and details.
"""

from __future__ import annotations

import argparse
import json
import re

import requests

BASE_URL = "https://jobs.apple.com/en-us/search"
HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def probe(
    search_query: str | None = None,
    location: str | None = None,
    limit: int = 5,
) -> None:
    params: dict[str, str | int] = {"page": 1}
    if search_query:
        params["search"] = search_query
    if location:
        params["location"] = location

    resp = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=20)
    resp.raise_for_status()

    match = re.search(
        r"window\.__staticRouterHydrationData\s*=\s*JSON\.parse\(([\"\x27].*?[\"\x27])\);",
        resp.text,
    )
    if not match:
        print("Error: Could not find __staticRouterHydrationData on Apple jobs page.")
        return

    raw_json_str = json.loads(match.group(1))
    data = json.loads(raw_json_str) if isinstance(raw_json_str, str) else raw_json_str
    search_data = data.get("loaderData", {}).get("search", {})

    total = search_data.get("totalRecords", 0)
    results = search_data.get("searchResults", [])

    print(f"Total matched jobs: {total}")
    print(f"Showing first {min(len(results), limit)} results:\n")

    for i, j in enumerate(results[:limit], 1):
        pid = j.get("positionId")
        title = j.get("postingTitle")
        slug_title = j.get("transformedPostingTitle") or ""
        url = f"https://jobs.apple.com/en-us/details/{pid}/{slug_title}"
        posted = j.get("postingDate")
        team = (j.get("team") or {}).get("teamName")

        loc_names = [
            loc.get("name")
            or ", ".join(
                filter(
                    None,
                    [loc.get("city"), loc.get("stateProvince"), loc.get("countryName")],
                )
            )
            for loc in j.get("locations") or []
        ]
        loc_str = "; ".join(filter(None, loc_names)) or "Unknown"

        print(f"{i}. {title}")
        print(f"   ID:       {pid}")
        print(f"   Team:     {team}")
        print(f"   Location: {loc_str}")
        print(f"   Posted:   {posted}")
        print(f"   URL:      {url}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Probe Apple Careers Jobs Page")
    parser.add_argument("--search", help="Keyword search, e.g. 'machine learning'")
    parser.add_argument("--location", help="Location key, e.g. 'united-states-USA'")
    parser.add_argument("--limit", type=int, default=5, help="Number of jobs to display")
    args = parser.parse_args()

    probe(
        search_query=args.search,
        location=args.location,
        limit=args.limit,
    )
