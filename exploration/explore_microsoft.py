"""EXPLORATION ONLY — not the real scraper. Probes the Microsoft Careers PCSX API.

Run:
    python exploration/explore_microsoft.py
    python exploration/explore_microsoft.py --remote
    python exploration/explore_microsoft.py --query "Azure" --location "Redmond, WA, United States"

Endpoints:
    Search:  GET https://apply.careers.microsoft.com/api/pcsx/search?domain=microsoft.com
    Details: GET https://apply.careers.microsoft.com/api/pcsx/position_details?domain=microsoft.com&position_id={id}

Documentation:
    See exploration/microsoft_api.md for full field mappings and details.
"""

from __future__ import annotations

import argparse

import requests

SEARCH_URL = "https://apply.careers.microsoft.com/api/pcsx/search"
DETAIL_URL = "https://apply.careers.microsoft.com/api/pcsx/position_details"
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
}


def probe(
    location: str | None = None,
    query_text: str | None = None,
    remote: bool = False,
    limit: int = 5,
) -> None:
    params: dict[str, str | int] = {
        "domain": "microsoft.com",
        "start": 0,
        "sort_by": "timestamp",
    }
    if remote:
        params["location"] = "Remote"
    elif location:
        params["location"] = location
    if query_text:
        params["query"] = query_text

    resp = requests.get(SEARCH_URL, headers=HEADERS, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json().get("data", {})

    total = data.get("count", 0)
    positions = data.get("positions", [])
    print(f"Total matched jobs: {total}")
    print(f"Showing first {min(len(positions), limit)} results:\n")

    for i, p in enumerate(positions[:limit], 1):
        job_id = p.get("id")
        name = p.get("name")
        locs = p.get("standardizedLocations") or p.get("locations") or []
        loc_str = ", ".join(locs) if locs else "Unknown"
        work_site = p.get("workLocationOption")
        department = p.get("department")
        rel_url = p.get("positionUrl") or f"/careers/job/{job_id}"
        full_url = f"https://apply.careers.microsoft.com{rel_url}"

        print(f"{i}. {name}")
        print(f"   ID:          {job_id}")
        print(f"   Department:  {department}")
        print(f"   Location:    {loc_str}")
        print(f"   Work Site:   {work_site}")
        print(f"   URL:         {full_url}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Probe Microsoft Careers PCSX API")
    parser.add_argument("--location", help="Location filter, e.g. 'United States' or 'Redmond'")
    parser.add_argument("--query", dest="query_text", help="Keyword search, e.g. 'Azure'")
    parser.add_argument("--remote", action="store_true", help="Filter for remote roles")
    parser.add_argument("--limit", type=int, default=5, help="Number of results to display")
    args = parser.parse_args()

    probe(
        location=args.location,
        query_text=args.query_text,
        remote=args.remote,
        limit=args.limit,
    )
