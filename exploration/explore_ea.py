"""Interactive CLI exploration script for the Electronic Arts (EA) careers portal.

Usage:
    python exploration/explore_ea.py
    python exploration/explore_ea.py --search "engineer"
    python exploration/explore_ea.py --limit 5 --details
"""

from __future__ import annotations

import argparse
import re

import requests

from scraper.text import html_to_text

SEARCH_URL = "https://jobs.ea.com/en_US/careers/SearchJobs"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe Electronic Arts Careers portal")
    parser.add_argument("--search", default="", help="Keyword or title filter")
    parser.add_argument("--offset", type=int, default=0, help="Offset index")
    parser.add_argument("--limit", type=int, default=5, help="Number of jobs to print")
    parser.add_argument("--details", action="store_true", help="Fetch description for first job")
    args = parser.parse_args()

    params: dict[str, str | int] = {
        "jobRecordsPerPage": 20,
        "jobOffset": args.offset,
    }
    if args.search:
        params["search"] = args.search

    session = requests.Session()
    session.headers.update(HEADERS)

    print(f"Querying EA jobs (search='{args.search}', offset={args.offset})...")
    resp = session.get(SEARCH_URL, params=params, timeout=20)
    resp.raise_for_status()

    # Extract total results count
    total_count = 0
    m_total = re.search(r"aria-label=[\'\"]([0-9,]+)\s+results[\'\"]", resp.text)
    if m_total:
        total_count = int(m_total.group(1).replace(",", ""))

    # Extract articles
    articles = re.findall(r"<article class=\"article article--result[^\"]*\"[^>]*>(.*?)</article>", resp.text, re.DOTALL)
    print(f"Total matching positions: {total_count:,} | Returned on page: {len(articles)}")
    print("-" * 70)

    jobs = []
    for idx, art in enumerate(articles[: args.limit], start=1):
        m_url = re.search(r"href=\"(https://jobs\.ea\.com/en_US/careers/JobDetail/[^\"]+/(\d+))\"", art)
        m_title = re.search(r"<a class=\"link link_result\"[^>]*>\s*([^<]+)\s*</a>", art)
        m_loc = re.search(r"<span class=\"list-item-location\">([^<]+)</span>", art)
        m_type = re.search(r"<span class=\"list-item-workerType\">([^<]+)</span>", art)
        m_dept = re.search(r"<span class=\"list-item-department\">([^<]+)</span>", art)

        url = m_url.group(1) if m_url else ""
        jid = m_url.group(2) if m_url else ""
        title = m_title.group(1).strip() if m_title else ""
        loc = m_loc.group(1).strip() if m_loc else "Remote"
        wtype = m_type.group(1).strip() if m_type else ""
        dept = m_dept.group(1).strip() if m_dept else ""

        jobs.append((jid, url))
        print(f"[{idx}] {title}")
        print(f"    ID: {jid} | Dept: {dept} | Type: {wtype}")
        print(f"    Location: {loc}")
        print(f"    URL: {url}")
        print()

    if args.details and jobs:
        first_id, first_url = jobs[0]
        print(f"Fetching description for role {first_id} ({first_url})...")
        d_resp = session.get(first_url, timeout=20)
        d_resp.raise_for_status()
        fields = re.findall(r"<div class=\"article__content__view__field__value\">(.*?)</div>", d_resp.text, re.DOTALL)
        clean_fields = [html_to_text(f) for f in fields]
        longest = max(clean_fields, key=len) if clean_fields else ""
        print(f"Extracted description ({len(longest):,} chars):")
        print(longest[:400])


if __name__ == "__main__":
    main()
