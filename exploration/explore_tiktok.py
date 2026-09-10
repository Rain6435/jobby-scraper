"""Interactive CLI exploration script for the TikTok Careers API.

Usage:
    python exploration/explore_tiktok.py
    python exploration/explore_tiktok.py --keyword "machine learning"
    python exploration/explore_tiktok.py --limit 5
"""

from __future__ import annotations

import argparse
import json

import requests

API_SEARCH = "https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts"
API_FILTERS = "https://api.lifeattiktok.com/api/v1/public/supplier/config/job/filters"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "website-path": "tiktok",
    "Referer": "https://lifeattiktok.com/search",
}


def build_location_string(city_info: dict | None) -> str:
    if not city_info:
        return "Remote"
    parts: list[str] = []
    curr = city_info
    while curr and isinstance(curr, dict):
        name = curr.get("en_name") or curr.get("i18n_name") or curr.get("name")
        if name:
            parts.append(str(name))
        curr = curr.get("parent")
    return ", ".join(parts) if parts else "Remote"


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe TikTok Careers API")
    parser.add_argument("--keyword", default="", help="Search keyword")
    parser.add_argument("--limit", type=int, default=5, help="Number of items to return")
    parser.add_argument("--offset", type=int, default=0, help="Offset")
    parser.add_argument("--filters", action="store_true", help="Print available filter categories")
    parser.add_argument("--raw", action="store_true", help="Dump raw first job JSON")
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update(HEADERS)

    if args.filters:
        print("Fetching filter metadata...")
        resp = session.post(API_FILTERS, json={})
        resp.raise_for_status()
        d = resp.json().get("data", {})
        print("Categories:", len(d.get("job_type_list", [])))
        for cat in d.get("job_type_list", []):
            print(f"  - {cat.get('en_name')} (ID: {cat.get('id')})")
        print("\nCities count:", len(d.get("city_list", [])))
        return

    payload = {
        "keyword": args.keyword,
        "limit": args.limit,
        "offset": args.offset,
    }

    print(f"Sending search request (keyword='{args.keyword}', limit={args.limit}, offset={args.offset})...")
    resp = session.post(API_SEARCH, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    code = data.get("code")
    data_obj = data.get("data", {})
    count = data_obj.get("count", 0)
    jobs = data_obj.get("job_post_list", [])

    print(f"Response code: {code} | Total global postings: {count:,} | Returned: {len(jobs)}")
    print("-" * 70)

    if args.raw and jobs:
        print(json.dumps(jobs[0], indent=2))
        return

    for idx, j in enumerate(jobs, start=1):
        jid = j.get("id", "")
        title = j.get("title", "")
        loc = build_location_string(j.get("city_info"))
        cat = (j.get("job_category") or {}).get("en_name", "")
        recruit = (j.get("recruit_type") or {}).get("en_name", "")
        desc_len = len(j.get("description", ""))
        req_len = len(j.get("requirement", ""))
        url = f"https://lifeattiktok.com/position/{jid}"

        print(f"[{idx}] {title}")
        print(f"    ID: {jid} | Category: {cat} | Type: {recruit}")
        print(f"    Location: {loc}")
        print(f"    URL: {url}")
        print(f"    Description: {desc_len} chars | Requirements: {req_len} chars")
        print()


if __name__ == "__main__":
    main()
