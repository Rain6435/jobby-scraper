"""EXPLORATION ONLY — not the real scraper. Probes Valve Software's careers site.

Run:
    python exploration/explore_valve.py
    python exploration/explore_valve.py --limit 3

Endpoints:
    List:   GET https://www.valvesoftware.com/en/jobs
    Detail: GET https://www.valvesoftware.com/en/jobs?job_id={job_id}

Documentation:
    See exploration/valve_api.md for full details.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import requests  # noqa: E402

from scraper.text import html_to_text  # noqa: E402

BASE_URL = "https://www.valvesoftware.com/en/jobs"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def probe(limit: int = 5) -> None:
    resp = requests.get(BASE_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    pattern = r"<a[^>]+href=[\"\x27]https://www\.valvesoftware\.com/en/jobs\?job_id=(\d+)[\"\x27][^>]*>(.*?)</a>"
    items = re.findall(pattern, resp.text, re.DOTALL)

    print(f"Total Valve openings: {len(items)}")
    print(f"Showing first {min(len(items), limit)}:\n")

    for i, (job_id, inner) in enumerate(items[:limit], 1):
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()
        url = f"https://www.valvesoftware.com/en/jobs?job_id={job_id}"

        # Fetch detail sample
        r_det = requests.get(url, headers=HEADERS, timeout=15)
        m = re.search(r"<div class=[\"\x27]job_description_intro[\"\x27]>(.*?)</div>", r_det.text, re.DOTALL)
        desc = html_to_text(m.group(1)) if m else ""

        print(f"{i}. {title}")
        print(f"   ID:       {job_id}")
        print("   Location: Bellevue, WA")
        print(f"   URL:      {url}")
        print(f"   Excerpt:  {desc[:140]}...\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Probe Valve Software Careers")
    parser.add_argument("--limit", type=int, default=3, help="Number of roles to probe")
    args = parser.parse_args()

    probe(limit=args.limit)
