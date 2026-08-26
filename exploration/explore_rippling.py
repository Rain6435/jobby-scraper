"""EXPLORATION ONLY — not the real scraper. Probes the Rippling ATS API.

Run: python exploration/explore_rippling.py [board_id]
Default: octasic-inc  (a Montreal company — rich, relevant test data)

Two endpoints:
  /api/v2/board/{board}/jobs?page=&pageSize=   -> paginated list; ALREADY has
                                                  structured locations (city/state/country)
  /api/v2/board/{board}/jobs/{uuid}            -> adds description + createdOn (posting date)

So location/title come free from the list; only the posting date and description
need the per-job detail call.
"""

import sys
import time
import requests

BOARD = sys.argv[1] if len(sys.argv) > 1 else "octasic-inc"
BASE = f"https://ats.rippling.com/api/v2/board/{BOARD}/jobs"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def fetch_list():
    """Walk every page; returns the combined items list."""
    items, page = [], 0
    while True:
        data = requests.get(BASE, params={"page": page, "pageSize": 50},
                            headers=HEADERS, timeout=25).json()
        items += data["items"]
        if page >= data["totalPages"] - 1:
            break
        page += 1
    return items


def fetch_detail(job_id):
    r = requests.get(f"{BASE}/{job_id}", headers=HEADERS, timeout=25)
    r.raise_for_status()
    return r.json()


def main():
    jobs = fetch_list()
    print(f"board={BOARD}  jobs={len(jobs)}\n")

    for j in jobs[:6]:
        locs = [l.get("name") for l in j.get("locations", [])]
        print(f"  {j['name'][:40]:40}  {locs}")

    sample = jobs[0]
    detail = fetch_detail(sample["id"])
    print(f"\ndetail keys: {list(detail.keys())}")
    print(f"  createdOn (posting date) = {detail.get('createdOn')}")
    print(f"  workLocations = {detail.get('workLocations')}")
    time.sleep(0.3)  # be polite


if __name__ == "__main__":
    main()
