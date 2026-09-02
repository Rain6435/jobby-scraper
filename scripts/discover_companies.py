#!/usr/bin/env python3
"""Autonomous Job Board & Company Discovery Tool for Jobby-Scraper.

Probes target companies and slugs across all supported ATS platforms:
- Greenhouse (greenhouse)
- Ashby (ashby)
- Lever (lever)
- BambooHR (bamboohr)
- SmartRecruiters (smartrecruiters)
- Rippling (rippling)
- Recruitee (recruitee)
- Workable (workable)
- Breezy (breezy)
- Workday (workday)

Features:
- Fast concurrent ATS probing across candidate slugs and boards
- Live scraper validation via scraper.boards.*
- Deduplication against existing config.json entries
- Safe, formatted appending to config.json
- Automated test suite verification with pytest
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def slugify(text: str) -> list[str]:
    """Generate candidate slug variations from a company name."""
    clean = text.lower().strip()
    # Remove common corporate suffixes
    clean = re.sub(r"\b(inc|llc|ltd|corp|corporation|group|technologies|solutions|software|ai|labs|studio|studios|canada|health|systems)\b", "", clean)
    clean = re.sub(r"[^\w\s-]", "", clean).strip()

    words = clean.split()
    if not words:
        raw = re.sub(r"[^\w]", "", text.lower())
        return [raw] if raw else []

    slug_hyphen = "-".join(words)
    slug_nospace = "".join(words)
    slug_underscore = "_".join(words)

    candidates = [slug_hyphen, slug_nospace, slug_underscore]

    # Also add full raw name
    raw_nospace = re.sub(r"[^\w]", "", text.lower())
    if raw_nospace not in candidates:
        candidates.append(raw_nospace)

    return list(dict.fromkeys(candidates))


def probe_greenhouse(slug: str, timeout: float = 3.0) -> dict[str, Any] | None:
    try:
        r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("jobs", [])
            if jobs:
                sample = jobs[0].get("title", "")
                loc = jobs[0].get("location", {}).get("name", "")
                return {"board": "greenhouse", "token": slug, "count": len(jobs), "sample": sample, "location": loc}
    except Exception:
        pass
    return None


def probe_ashby(slug: str, timeout: float = 3.0) -> dict[str, Any] | None:
    try:
        r = requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", params={"includeCompensation": "true"}, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("jobs", [])
            if jobs:
                sample = jobs[0].get("title", "")
                loc = jobs[0].get("location", "")
                return {"board": "ashby", "slug": slug, "count": len(jobs), "sample": sample, "location": loc}
    except Exception:
        pass
    return None


def probe_lever(slug: str, timeout: float = 3.0) -> dict[str, Any] | None:
    try:
        r = requests.get(f"https://api.lever.co/v0/postings/{slug}?mode=json", headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                sample = data[0].get("text", "")
                loc = data[0].get("categories", {}).get("location", "")
                return {"board": "lever", "company": slug, "count": len(data), "sample": sample, "location": loc}
    except Exception:
        pass
    return None


def probe_bamboohr(slug: str, timeout: float = 3.0) -> dict[str, Any] | None:
    try:
        r = requests.get(f"https://{slug}.bamboohr.com/careers/list", headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("result", [])
            if jobs:
                sample = jobs[0].get("jobOpeningName", "")
                city = jobs[0].get("location", {}).get("city", "")
                state = jobs[0].get("location", {}).get("state", "")
                loc = f"{city}, {state}".strip(", ")
                return {"board": "bamboohr", "company": slug, "count": len(jobs), "sample": sample, "location": loc}
    except Exception:
        pass
    return None


def probe_smartrecruiters(slug: str, timeout: float = 3.0) -> dict[str, Any] | None:
    try:
        r = requests.get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1", headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("content", [])
            total = data.get("totalFound", 0)
            if jobs and total > 0:
                sample = jobs[0].get("name", "")
                loc = jobs[0].get("location", {}).get("fullLocation", "")
                return {"board": "smartrecruiters", "company": slug, "count": total, "sample": sample, "location": loc}
    except Exception:
        pass
    return None


def probe_rippling(slug: str, timeout: float = 3.0) -> dict[str, Any] | None:
    try:
        r = requests.get(f"https://ats.rippling.com/api/v2/board/{slug}/jobs", headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("jobs", [])
            if jobs:
                sample = jobs[0].get("name", "")
                locs = jobs[0].get("locations", [])
                loc = locs[0].get("name", "") if locs else ""
                return {"board": "rippling", "board_id": slug, "count": len(jobs), "sample": sample, "location": loc}
    except Exception:
        pass
    return None


def probe_recruitee(slug: str, timeout: float = 3.0) -> dict[str, Any] | None:
    try:
        r = requests.get(f"https://{slug}.recruitee.com/api/offers", headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            offers = data.get("offers", [])
            if offers:
                sample = offers[0].get("title", "")
                city = offers[0].get("city", "")
                country = offers[0].get("country", "")
                loc = f"{city}, {country}".strip(", ")
                return {"board": "recruitee", "company": slug, "count": len(offers), "sample": sample, "location": loc}
    except Exception:
        pass
    return None


def probe_workable(slug: str, timeout: float = 3.0) -> dict[str, Any] | None:
    try:
        r = requests.get(f"https://apply.workable.com/api/v3/accounts/{slug}/jobs", headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            total = data.get("total", len(results))
            if results and total > 0:
                sample = results[0].get("title", "")
                city = results[0].get("city", "")
                country = results[0].get("country", "")
                loc = f"{city}, {country}".strip(", ")
                return {"board": "workable", "company": slug, "count": total, "sample": sample, "location": loc}
    except Exception:
        pass
    return None


def probe_breezy(slug: str, timeout: float = 3.0) -> dict[str, Any] | None:
    try:
        r = requests.get(f"https://{slug}.breezy.hr/json", headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                sample = data[0].get("name", "")
                loc = data[0].get("location", {}).get("name", "")
                return {"board": "breezy", "company": slug, "count": len(data), "sample": sample, "location": loc}
    except Exception:
        pass
    return None


def probe_personio(slug: str, timeout: float = 3.0) -> dict[str, Any] | None:
    try:
        r = requests.get(f"https://{slug}.jobs.personio.de/xml", headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(r.content)
            positions = root.findall("position")
            if positions:
                sample = positions[0].findtext("name", "")
                loc = positions[0].findtext("office", "")
                return {"board": "personio", "company": slug, "count": len(positions), "sample": sample, "location": loc}
    except Exception:
        pass
    return None


def probe_teamtailor(slug: str, timeout: float = 3.0) -> dict[str, Any] | None:
    try:
        r = requests.get(f"https://{slug}.teamtailor.com/jobs.json", headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            if items:
                sample = items[0].get("title", "")
                return {"board": "teamtailor", "company": slug, "count": len(items), "sample": sample, "location": ""}
    except Exception:
        pass
    return None


PROBERS = {
    "greenhouse": probe_greenhouse,
    "ashby": probe_ashby,
    "lever": probe_lever,
    "bamboohr": probe_bamboohr,
    "smartrecruiters": probe_smartrecruiters,
    "rippling": probe_rippling,
    "recruitee": probe_recruitee,
    "workable": probe_workable,
    "breezy": probe_breezy,
    "personio": probe_personio,
    "teamtailor": probe_teamtailor,
}


def load_existing_config() -> tuple[list[dict[str, Any]], set[str]]:
    """Load config.json and build lookup keys for deduplication."""
    if not CONFIG_PATH.exists():
        return [], set()

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    companies = data.get("companies", [])
    signatures = set()

    for c in companies:
        signatures.add(c.get("name", "").lower())
        board = c.get("board", "")
        if "token" in c:
            signatures.add(f"greenhouse:{c['token'].lower()}")
        if "slug" in c:
            signatures.add(f"ashby:{c['slug'].lower()}")
        if "company" in c:
            signatures.add(f"{board}:{c['company'].lower()}")
        if "board_id" in c:
            signatures.add(f"rippling:{c['board_id'].lower()}")
        if "url" in c:
            signatures.add(f"workday:{c['url'].lower()}")

    return companies, signatures


def probe_candidate_slug(slug: str, allowed_boards: list[str] | None = None) -> list[dict[str, Any]]:
    """Probe all supported boards for a given slug."""
    boards_to_test = allowed_boards if allowed_boards else list(PROBERS.keys())
    matches = []
    for b in boards_to_test:
        fn = PROBERS.get(b)
        if fn:
            res = fn(slug)
            if res:
                matches.append(res)
    return matches


def probe_company(
    name: str,
    explicit_slugs: list[str] | None = None,
    allowed_boards: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Generate candidate slugs for a company and probe ATS endpoints."""
    candidate_slugs = set(explicit_slugs or [])
    for s in slugify(name):
        candidate_slugs.add(s)

    results = []
    for slug in candidate_slugs:
        matches = probe_candidate_slug(slug, allowed_boards=allowed_boards)
        for m in matches:
            res = {"name": name, **m}
            results.append(res)
    return results


def verify_live_scraper(cfg: dict[str, Any]) -> tuple[bool, int, str]:
    """Verify live scraping using jobby-scraper's native board scraper."""
    board = cfg.get("board")
    clean_cfg = {k: v for k, v in cfg.items() if k not in ("count", "sample", "location")}

    try:
        if board == "greenhouse":
            from scraper.boards.greenhouse import GreenhouseScraper
            scraper = GreenhouseScraper(clean_cfg)
        elif board == "ashby":
            from scraper.boards.ashby import AshbyScraper
            scraper = AshbyScraper(clean_cfg)
        elif board == "lever":
            from scraper.boards.lever import LeverScraper
            scraper = LeverScraper(clean_cfg)
        elif board == "bamboohr":
            from scraper.boards.bamboohr import BambooHRScraper
            scraper = BambooHRScraper(clean_cfg)
        elif board == "smartrecruiters":
            from scraper.boards.smartrecruiters import SmartRecruitersScraper
            scraper = SmartRecruitersScraper(clean_cfg)
        elif board == "rippling":
            from scraper.boards.rippling import RipplingScraper
            scraper = RipplingScraper(clean_cfg)
        elif board == "recruitee":
            from scraper.boards.recruitee import RecruiteeScraper
            scraper = RecruiteeScraper(clean_cfg)
        elif board == "workable":
            from scraper.boards.workable import WorkableScraper
            scraper = WorkableScraper(clean_cfg)
        elif board == "breezy":
            from scraper.boards.breezy import BreezyScraper
            scraper = BreezyScraper(clean_cfg)
        elif board == "workday":
            from scraper.boards.workday import WorkdayScraper
            scraper = WorkdayScraper(clean_cfg)
        else:
            return False, 0, f"Unsupported board {board}"

        jobs = scraper.fetch_jobs()
        sample = jobs[0].title if jobs else "No jobs"
        return True, len(jobs), sample
    except Exception as e:
        return False, 0, str(e)


def append_to_config(new_configs: list[dict[str, Any]]) -> int:
    """Safely append new company configurations into config.json."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    existing_companies = data.get("companies", [])
    existing_signatures = {c.get("name", "").lower() for c in existing_companies}

    added = 0
    for cfg in new_configs:
        clean = {k: v for k, v in cfg.items() if k not in ("count", "sample", "location")}
        if clean.get("name", "").lower() not in existing_signatures:
            existing_companies.append(clean)
            existing_signatures.add(clean.get("name", "").lower())
            added += 1

    data["companies"] = existing_companies

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return added


def main():
    parser = argparse.ArgumentParser(description="Autonomous Job Board Discovery & Expansion Tool")
    parser.add_argument("--company", "-c", type=str, help="Company name to probe")
    parser.add_argument("--slug", "-s", type=str, help="Specific slug(s), comma-separated")
    parser.add_argument("--file", "-f", type=str, help="File containing company names or slugs (one per line)")
    parser.add_argument("--board", "-b", type=str, help="Limit search to specific board (greenhouse, ashby, lever, etc.)")
    parser.add_argument("--workday-url", type=str, help="Workday wday/cxs API URL")
    parser.add_argument("--workday-base", type=str, help="Workday careers base URL")
    parser.add_argument("--apply", "-a", action="store_true", help="Automatically append verified companies to config.json")
    parser.add_argument("--verify", action="store_true", default=True, help="Verify live scraper integration (default: True)")
    parser.add_argument("--test", action="store_true", help="Run pytest test suite after modifying config")
    parser.add_argument("--workers", "-w", type=int, default=20, help="Concurrency workers")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = parser.parse_args()

    allowed_boards = [b.strip() for b in args.board.split(",")] if args.board else None

    # Load existing signatures
    _, existing_signatures = load_existing_config()

    candidates: list[tuple[str, list[str]]] = []

    if args.workday_url:
        name = args.company or "Workday Company"
        cfg = {
            "name": name,
            "board": "workday",
            "url": args.workday_url,
            "careers_base": args.workday_base or args.workday_url.replace("/wday/cxs/", "/en-US/").replace("/jobs", ""),
        }
        ok, count, sample = verify_live_scraper(cfg)
        if ok:
            print(f"VERIFIED WORKDAY: {name} -> {count} jobs | Sample: \"{sample}\"")
            if args.apply:
                added = append_to_config([cfg])
                print(f"Added {added} company to config.json")
                if args.test:
                    subprocess.run([sys.executable, "-m", "pytest", "tests/test_workday.py"], check=True)
            return
        else:
            print(f"FAILED WORKDAY: {name} -> {sample}", file=sys.stderr)
            sys.exit(1)

    if args.company:
        slugs = [s.strip() for s in args.slug.split(",")] if args.slug else []
        candidates.append((args.company, slugs))

    if args.slug and not args.company:
        for s in args.slug.split(","):
            s = s.strip()
            if s:
                candidates.append((s.replace("-", " ").title(), [s]))

    if args.file:
        file_path = Path(args.file)
        if file_path.exists():
            for line in file_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    candidates.append((line, []))

    if not candidates:
        parser.print_help()
        sys.exit(0)

    print(f"Probing {len(candidates)} company candidates across ATS platforms (workers={args.workers})...")

    discovered: list[dict[str, Any]] = []

    def process_candidate(item: tuple[str, list[str]]) -> list[dict[str, Any]]:
        name, explicit_slugs = item
        if name.lower() in existing_signatures:
            return []
        matches = probe_company(name, explicit_slugs=explicit_slugs, allowed_boards=allowed_boards)
        valid = []
        for m in matches:
            board = m["board"]
            key = f"{board}:{m.get('token') or m.get('slug') or m.get('company') or m.get('board_id')}".lower()
            if key not in existing_signatures:
                valid.append(m)
        return valid

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(process_candidate, c) for c in candidates]
        for f in concurrent.futures.as_completed(futs):
            res = f.result()
            discovered.extend(res)

    print(f"\nFound {len(discovered)} potential new job boards!")

    verified_list = []
    for d in discovered:
        clean = {k: v for k, v in d.items() if k not in ("count", "sample", "location")}
        ok, cnt, sample = verify_live_scraper(clean)
        if ok and cnt > 0:
            print(f"  [VALID] {d['name']} ({d['board']}: {clean.get('token') or clean.get('slug') or clean.get('company') or clean.get('board_id')}) -> {cnt} jobs | \"{sample}\"")
            clean["count"] = cnt
            clean["sample"] = sample
            verified_list.append(clean)
        elif ok:
            print(f"  [EMPTY] {d['name']} ({d['board']}) -> 0 jobs (skipped)")
        else:
            print(f"  [INVALID] {d['name']} ({d['board']}) -> {sample}")

    if args.json:
        print(json.dumps(verified_list, indent=2))

    if args.apply and verified_list:
        added = append_to_config(verified_list)
        print(f"\nSuccessfully added {added} new companies to {CONFIG_PATH.name}!")
        if args.test:
            print("Running test suite...")
            subprocess.run([sys.executable, "-m", "pytest", "tests/test_workday.py", "tests/test_greenhouse.py", "tests/test_lever.py", "tests/test_ashby.py", "tests/test_bamboohr.py"], check=True)
    elif verified_list and not args.apply:
        print(f"\nTip: Run with '--apply' to append these {len(verified_list)} verified companies into config.json.")


if __name__ == "__main__":
    main()
