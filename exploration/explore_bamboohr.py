"""EXPLORATION ONLY — not the real scraper. Probes the BambooHR careers API.

Run: python exploration/explore_bamboohr.py [company_subdomain]
Default: euna

Two endpoints:
  /careers/list            -> all openings, but NO posting date
  /careers/{id}/detail     -> result.jobOpening.datePosted  (one call PER job)

NOTE: the date is nested at result.jobOpening.datePosted, NOT result.datePosted
as Job_Scraper.md implies. Multi-location roles appear as SEPARATE list rows
(same jobOpeningName, different id + location).
"""

import sys
import time
import requests

COMPANY = sys.argv[1] if len(sys.argv) > 1 else "euna"
BASE = f"https://{COMPANY}.bamboohr.com/careers"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def fetch_list():
    r = requests.get(f"{BASE}/list", headers=HEADERS, timeout=25)
    r.raise_for_status()
    return r.json()["result"]


def fetch_detail(job_id):
    r = requests.get(f"{BASE}/{job_id}/detail", headers=HEADERS, timeout=25)
    r.raise_for_status()
    return r.json()["result"]


def main():
    jobs = fetch_list()
    print(f"company={COMPANY}  openings={len(jobs)}")
    print("(no page params observed — /list appears to return everything)\n")

    for j in jobs[:6]:
        loc = j.get("location") or {}
        where = ", ".join(filter(None, [loc.get("city"), loc.get("state")]))
        print(f"  id={j['id']:>5}  {j['jobOpeningName'][:38]:38}  {where}")

    # Date requires one detail call per job.
    sample = jobs[0]
    detail = fetch_detail(sample["id"])
    jo = detail["jobOpening"]
    print(f"\ndetail['{sample['id']}'] -> result keys: {list(detail.keys())}")
    print(f"  jobOpening.datePosted = {jo.get('datePosted')}")
    print(f"  apply url (jobOpeningShareUrl) = {jo.get('jobOpeningShareUrl')}")
    time.sleep(0.3)  # be polite


if __name__ == "__main__":
    main()
