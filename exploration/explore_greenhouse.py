"""EXPLORATION ONLY — not the real scraper. Probes the Greenhouse public API.

Run: python exploration/explore_greenhouse.py [board_token]
Default token: asana

Greenhouse is the easiest of the three boards: one unauthenticated GET returns
every job with its description and posting date. No pagination, no per-job calls.
"""

import sys
import requests

TOKEN = sys.argv[1] if len(sys.argv) > 1 else "asana"
BASE = f"https://boards-api.greenhouse.io/v1/boards/{TOKEN}"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def fetch_all(with_content=True):
    """All jobs in a single response. `content=true` adds the HTML description."""
    params = {"content": "true"} if with_content else {}
    r = requests.get(f"{BASE}/jobs", params=params, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return r.json()


def main():
    data = fetch_all(with_content=True)
    jobs = data["jobs"]
    print(f"board={TOKEN}  meta.total={data['meta']['total']}  returned={len(jobs)}")
    print("(single response — no pagination)\n")

    for j in jobs[:8]:
        print(f"  id={j['id']}  req={j.get('requisition_id')!r:>12}  "
              f"first_published={j.get('first_published')}  "
              f"loc={j['location']['name']!r}")
        print(f"     {j['title']}")
        print(f"     apply: {j['absolute_url']}")

    # Fields worth mapping later (see README).
    j0 = jobs[0]
    print("\njob keys:", list(j0.keys()))


if __name__ == "__main__":
    main()
