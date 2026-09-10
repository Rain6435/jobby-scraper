"""EXPLORATION ONLY — not the real scraper. Probes the Amazon Jobs search API.

Run:
    python exploration/explore_amazon.py
    python exploration/explore_amazon.py --category software-development --country USA
    python exploration/explore_amazon.py --business amazon-web-services

Endpoint:
    GET https://www.amazon.jobs/en/search.json
    Parameters:
      offset, result_limit (max 100), sort=recent
      category[], country[], business_category[]

Documentation:
    See exploration/amazon_api.md for full field mappings and details.
"""

from __future__ import annotations

import argparse
import json

import requests

BASE_URL = "https://www.amazon.jobs/en/search.json"
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
}


def probe(
    country: str | None = None,
    category: str | None = None,
    business: str | None = None,
    limit: int = 5,
) -> None:
    params: list[tuple[str, str | int]] = [
        ("offset", 0),
        ("result_limit", min(limit, 100)),
        ("sort", "recent"),
        ("facets[]", "category"),
        ("facets[]", "business_category"),
    ]
    if country:
        params.append(("country[]", country))
    if category:
        params.append(("category[]", category))
    if business:
        params.append(("business_category[]", business))

    resp = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    hits = data.get("hits", 0)
    jobs = data.get("jobs", [])
    print(f"Total matched jobs: {hits}")
    print(f"Showing first {len(jobs)} results:\n")

    for i, j in enumerate(jobs[:limit], 1):
        job_id = j.get("id_icims") or j.get("id")
        title = j.get("title")
        loc = j.get("normalized_location") or j.get("location")
        posted = j.get("posted_date")
        path = j.get("job_path")
        company = j.get("company_name")

        all_locs: list[str] = []
        for l_raw in j.get("locations") or []:
            try:
                l_obj = json.loads(l_raw)
                nl = l_obj.get("normalizedLocation") or l_obj.get("location")
                if nl:
                    all_locs.append(nl)
            except Exception:
                if l_raw:
                    all_locs.append(l_raw)

        print(f"{i}. {title}")
        print(f"   ID:          {job_id}")
        print(f"   Company:     {company}")
        print(f"   Location:    {loc}")
        if len(all_locs) > 1:
            print(f"   All Locs:    {all_locs}")
        print(f"   Posted Date: {posted}")
        print(f"   URL:         https://www.amazon.jobs{path}\n")

    facets = data.get("facets", {})
    if facets:
        print("Facet Highlights:")
        for k, v in facets.items():
            if isinstance(v, list):
                top = [f"{list(b.keys())[0]} ({list(b.values())[0]})" for b in v[:4]]
                print(f"  {k}: {', '.join(top)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Probe Amazon Jobs API")
    parser.add_argument("--country", help="Filter by country, e.g. USA or CAN")
    parser.add_argument("--category", help="Filter by category, e.g. software-development")
    parser.add_argument("--business", help="Filter by business line, e.g. amazon-web-services")
    parser.add_argument("--limit", type=int, default=5, help="Number of results to display")
    args = parser.parse_args()

    probe(
        country=args.country,
        category=args.category,
        business=args.business,
        limit=args.limit,
    )
