#!/usr/bin/env python3
"""Autonomous S&P 500 Multi-ATS Company Scout & Verification Tool.

Surveys S&P 500 multinationals across all sectors:
- Information Technology
- Health Care & Life Sciences
- Financials & Insurance
- Consumer Discretionary & Staples
- Industrials, Aerospace & Defense
- Energy, CleanTech & Utilities
- Materials & Chemicals
- Communication Services & Media
- Real Estate & Infrastructure

Probes all supported ATS platforms:
- Greenhouse (greenhouse)
- Ashby (ashby)
- Lever (lever)
- BambooHR (bamboohr)
- SmartRecruiters (smartrecruiters)
- Workday (workday)
- Rippling (rippling)
- Recruitee (recruitee)
- Workable (workable)
- Breezy (breezy)
- Personio (personio)
- Teamtailor (teamtailor)
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CONFIG_PATH = REPO_ROOT / "config.json"
SP500_PATH = REPO_ROOT / "sp500_constituents.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

WD_CLUSTERS = [1, 2, 3, 5, 10, 12, 102, 103, 105]
WD_SITE_PATTERNS = [
    "{tenant}",
    "{tenant}_Careers",
    "{tenant}Careers",
    "{tenant}ExternalCareerSite",
    "{tenant}_External_Career_Site",
    "{tenant}_Career_Site",
    "{tenant}_jobs",
    "{tenant}jobs",
    "{tenant}_External",
    "External",
    "External_Careers",
    "External_Career_Site",
    "Careers",
    "Career",
    "search",
    "jobs",
    "Global_Careers",
    "Corporate",
    "Enterprise",
    "US",
    "Global",
    "external_careers",
]


def generate_candidate_slugs(name: str, symbol: str) -> list[str]:
    """Generate candidate slug variations for a company."""
    clean = name.lower().strip()
    clean = re.sub(
        r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|group|technologies|technology|solutions|software|ai|labs|systems|the|co|company|holdings|plc|class a|class b|class c)\b",
        "",
        clean,
    )
    clean = re.sub(r"[^\w\s-]", "", clean).strip()

    words = clean.split()
    candidates: list[str] = []

    if words:
        candidates.append("-".join(words))
        candidates.append("".join(words))
        candidates.append("_".join(words))

    raw_nospace = re.sub(r"[^\w]", "", name.lower())
    if raw_nospace:
        candidates.append(raw_nospace)

    raw_hyphen = re.sub(r"[^\w\s-]", "", name.lower()).strip()
    if raw_hyphen:
        candidates.append("-".join(raw_hyphen.split()))

    if len(symbol) >= 4:
        candidates.append(symbol.lower())

    return list(dict.fromkeys(c for c in candidates if c))


def probe_workday_tenant(
    tenant: str, name: str, session: requests.Session
) -> dict[str, Any] | None:
    for wd in WD_CLUSTERS:
        for pat in WD_SITE_PATTERNS:
            site = pat.format(tenant=tenant)
            url = f"https://{tenant}.wd{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
            try:
                r = session.post(
                    url,
                    json={"limit": 1, "offset": 0, "searchText": "", "appliedFacets": {}},
                    timeout=1.8,
                )
                if r.status_code == 200:
                    data = r.json()
                    total = data.get("total", 0)
                    postings = data.get("jobPostings", [])
                    if total > 0 and postings:
                        sample = postings[0].get("title", "")
                        return {
                            "name": name,
                            "board": "workday",
                            "url": url,
                            "careers_base": f"https://{tenant}.wd{wd}.myworkdayjobs.com/en-US/{site}",
                            "count": total,
                            "sample": sample,
                        }
            except Exception:
                pass
    return None


def probe_greenhouse(slug: str, session: requests.Session) -> dict[str, Any] | None:
    try:
        r = session.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", timeout=2.5)
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("jobs", [])
            if jobs:
                return {
                    "board": "greenhouse",
                    "token": slug,
                    "count": len(jobs),
                    "sample": jobs[0].get("title", ""),
                }
    except Exception:
        pass
    return None


def probe_ashby(slug: str, session: requests.Session) -> dict[str, Any] | None:
    try:
        r = session.get(
            f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
            params={"includeCompensation": "true"},
            timeout=2.5,
        )
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("jobs", [])
            if jobs:
                return {
                    "board": "ashby",
                    "slug": slug,
                    "count": len(jobs),
                    "sample": jobs[0].get("title", ""),
                }
    except Exception:
        pass
    return None


def probe_lever(slug: str, session: requests.Session) -> dict[str, Any] | None:
    try:
        r = session.get(f"https://api.lever.co/v0/postings/{slug}?mode=json", timeout=2.5)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                return {
                    "board": "lever",
                    "company": slug,
                    "count": len(data),
                    "sample": data[0].get("text", ""),
                }
    except Exception:
        pass
    return None


def probe_smartrecruiters(slug: str, session: requests.Session) -> dict[str, Any] | None:
    try:
        r = session.get(
            f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1",
            timeout=2.5,
        )
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("content", [])
            total = data.get("totalFound", 0)
            if jobs and total > 0:
                return {
                    "board": "smartrecruiters",
                    "company": slug,
                    "count": total,
                    "sample": jobs[0].get("name", ""),
                }
    except Exception:
        pass
    return None


def probe_bamboohr(slug: str, session: requests.Session) -> dict[str, Any] | None:
    try:
        r = session.get(f"https://{slug}.bamboohr.com/careers/list", timeout=2.5)
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("result", [])
            if jobs:
                return {
                    "board": "bamboohr",
                    "company": slug,
                    "count": len(jobs),
                    "sample": jobs[0].get("jobOpeningName", ""),
                }
    except Exception:
        pass
    return None


def probe_rippling(slug: str, session: requests.Session) -> dict[str, Any] | None:
    try:
        r = session.get(f"https://ats.rippling.com/api/v2/board/{slug}/jobs", timeout=2.5)
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("jobs", [])
            if jobs:
                return {
                    "board": "rippling",
                    "board_id": slug,
                    "count": len(jobs),
                    "sample": jobs[0].get("name", ""),
                }
    except Exception:
        pass
    return None


def probe_workable(slug: str, session: requests.Session) -> dict[str, Any] | None:
    try:
        r = session.get(f"https://apply.workable.com/api/v3/accounts/{slug}/jobs", timeout=2.5)
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            total = data.get("total", len(results))
            if results and total > 0:
                return {
                    "board": "workable",
                    "company": slug,
                    "count": total,
                    "sample": results[0].get("title", ""),
                }
    except Exception:
        pass
    return None


def probe_personio(slug: str, session: requests.Session) -> dict[str, Any] | None:
    try:
        r = session.get(f"https://{slug}.jobs.personio.de/xml", timeout=2.5)
        if r.status_code == 200:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(r.content)
            positions = root.findall("position")
            if positions:
                return {
                    "board": "personio",
                    "company": slug,
                    "count": len(positions),
                    "sample": positions[0].findtext("name", ""),
                }
    except Exception:
        pass
    return None


def probe_recruitee(slug: str, session: requests.Session) -> dict[str, Any] | None:
    try:
        r = session.get(f"https://{slug}.recruitee.com/api/offers", timeout=2.5)
        if r.status_code == 200:
            data = r.json()
            offers = data.get("offers", [])
            if offers:
                return {
                    "board": "recruitee",
                    "company": slug,
                    "count": len(offers),
                    "sample": offers[0].get("title", ""),
                }
    except Exception:
        pass
    return None


def probe_teamtailor(slug: str, session: requests.Session) -> dict[str, Any] | None:
    try:
        r = session.get(f"https://{slug}.teamtailor.com/jobs.json", timeout=2.5)
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            if items:
                return {
                    "board": "teamtailor",
                    "company": slug,
                    "count": len(items),
                    "sample": items[0].get("title", ""),
                }
    except Exception:
        pass
    return None


def probe_breezy(slug: str, session: requests.Session) -> dict[str, Any] | None:
    try:
        r = session.get(f"https://{slug}.breezy.hr/json", timeout=2.5)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                return {
                    "board": "breezy",
                    "company": slug,
                    "count": len(data),
                    "sample": data[0].get("name", ""),
                }
    except Exception:
        pass
    return None


def probe_pinpoint(slug: str, session: requests.Session) -> dict[str, Any] | None:
    try:
        r = session.get(f"https://{slug}.pinpointhq.com/postings.json", timeout=2.5)
        if r.status_code == 200:
            data = r.json()
            postings = data if isinstance(data, list) else data.get("data", [])
            if postings:
                return {
                    "board": "pinpoint",
                    "company": slug,
                    "count": len(postings),
                    "sample": postings[0].get("title", ""),
                }
    except Exception:
        pass
    return None


def probe_jobvite(slug: str, session: requests.Session) -> dict[str, Any] | None:
    try:
        r = session.get(f"https://app.jobvite.com/CompanyJobs/Xml.aspx?c={slug}", timeout=2.5)
        if r.status_code == 200 and b"<job>" in r.content:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(r.content)
            jobs = root.findall(".//job")
            if jobs:
                return {
                    "board": "jobvite",
                    "company_id": slug,
                    "count": len(jobs),
                    "sample": jobs[0].findtext("title", ""),
                }
    except Exception:
        pass
    return None


def probe_jazzhr(slug: str, session: requests.Session) -> dict[str, Any] | None:
    try:
        r = session.get(f"https://app.jazz.co/feeds/export/jobs/{slug}", timeout=2.5)
        if r.status_code == 200 and b"<job>" in r.content:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(r.content)
            jobs = root.findall(".//job")
            if jobs:
                return {
                    "board": "jazzhr",
                    "company": slug,
                    "count": len(jobs),
                    "sample": jobs[0].findtext("title", ""),
                }
    except Exception:
        pass
    return None


def probe_governmentjobs(slug: str, session: requests.Session) -> dict[str, Any] | None:
    try:
        r = session.get(
            f"https://agency.governmentjobs.com/jobfeed_v2.cfm?agency={slug}", timeout=2.5
        )
        if r.status_code == 200 and (b"<item" in r.content or b"<job" in r.content):
            import re

            items = re.findall(r"<item\b.*?>(.*?)</item>", r.text, re.DOTALL)
            if items:
                title_m = re.search(r"<title\b.*?>(.*?)</title>", items[0], re.DOTALL)
                return {
                    "board": "governmentjobs",
                    "agency": slug,
                    "count": len(items),
                    "sample": title_m.group(1).strip() if title_m else "",
                }
    except Exception:
        pass
    return None


def probe_successfactors(slug: str, session: requests.Session) -> dict[str, Any] | None:
    for domain in (f"jobs.{slug}.com", f"{slug}.jobs", f"careers.{slug}.com"):
        try:
            r = session.get(
                f"https://{domain}/services/rss/job/?locale=en_US",
                timeout=2.5,
            )
            if r.status_code == 200 and (b"<rss" in r.content or b"<item" in r.content):
                import re

                items = re.findall(r"<item\b.*?>(.*?)</item>", r.text, re.DOTALL)
                if items:
                    title_m = re.search(r"<title\b.*?>(.*?)</title>", items[0], re.DOTALL)
                    return {
                        "board": "successfactors",
                        "company": slug,
                        "domain": domain,
                        "count": len(items),
                        "sample": title_m.group(1).strip() if title_m else "",
                    }
        except Exception:
            pass
    return None


PROBERS = {
    "smartrecruiters": probe_smartrecruiters,
    "greenhouse": probe_greenhouse,
    "ashby": probe_ashby,
    "lever": probe_lever,
    "bamboohr": probe_bamboohr,
    "rippling": probe_rippling,
    "workable": probe_workable,
    "personio": probe_personio,
    "recruitee": probe_recruitee,
    "teamtailor": probe_teamtailor,
    "breezy": probe_breezy,
    "pinpoint": probe_pinpoint,
    "jobvite": probe_jobvite,
    "jazzhr": probe_jazzhr,
    "governmentjobs": probe_governmentjobs,
    "successfactors": probe_successfactors,
}


def verify_live_scraper(cfg: dict[str, Any]) -> tuple[bool, int, str]:
    board = cfg.get("board")
    clean_cfg = {
        "name": cfg.get("name", ""),
        "board": board,
    }
    for k in (
        "url",
        "careers_base",
        "token",
        "slug",
        "company",
        "board_id",
        "company_id",
        "agency",
        "tenant",
        "site_number",
        "domain",
        "cid",
        "cc_id",
        "guid",
    ):
        if k in cfg:
            clean_cfg[k] = cfg[k]

    try:
        if board == "greenhouse":
            from scraper.boards.greenhouse import GreenhouseScraper

            s = GreenhouseScraper(clean_cfg)
        elif board == "ashby":
            from scraper.boards.ashby import AshbyScraper

            s = AshbyScraper(clean_cfg)
        elif board == "lever":
            from scraper.boards.lever import LeverScraper

            s = LeverScraper(clean_cfg)
        elif board == "bamboohr":
            from scraper.boards.bamboohr import BambooHRScraper

            s = BambooHRScraper(clean_cfg)
        elif board == "smartrecruiters":
            from scraper.boards.smartrecruiters import SmartRecruitersScraper

            s = SmartRecruitersScraper(clean_cfg)
        elif board == "workday":
            from scraper.boards.workday import WorkdayScraper

            s = WorkdayScraper(clean_cfg)
        elif board == "rippling":
            from scraper.boards.rippling import RipplingScraper

            s = RipplingScraper(clean_cfg)
        elif board == "workable":
            from scraper.boards.workable import WorkableScraper

            s = WorkableScraper(clean_cfg)
        elif board == "personio":
            from scraper.boards.personio import PersonioScraper

            s = PersonioScraper(clean_cfg)
        elif board == "recruitee":
            from scraper.boards.recruitee import RecruiteeScraper

            s = RecruiteeScraper(clean_cfg)
        elif board == "teamtailor":
            from scraper.boards.teamtailor import TeamtailorScraper

            s = TeamtailorScraper(clean_cfg)
        elif board == "breezy":
            from scraper.boards.breezy import BreezyScraper

            s = BreezyScraper(clean_cfg)
        elif board == "pinpoint":
            from scraper.boards.pinpoint import PinpointScraper

            s = PinpointScraper(clean_cfg)
        elif board == "jobvite":
            from scraper.boards.jobvite import JobviteScraper

            s = JobviteScraper(clean_cfg)
        elif board == "jazzhr":
            from scraper.boards.jazzhr import JazzHrScraper

            s = JazzHrScraper(clean_cfg)
        elif board == "governmentjobs":
            from scraper.boards.governmentjobs import GovernmentJobsScraper

            s = GovernmentJobsScraper(clean_cfg)
        elif board == "reliefweb":
            from scraper.boards.reliefweb import ReliefwebScraper

            s = ReliefwebScraper(clean_cfg)
        elif board == "oraclecloud":
            from scraper.boards.oraclecloud import OracleCloudScraper

            s = OracleCloudScraper(clean_cfg)
        elif board == "successfactors":
            from scraper.boards.successfactors import SuccessFactorsScraper

            s = SuccessFactorsScraper(clean_cfg)
        elif board == "adp":
            from scraper.boards.adp import AdpScraper

            s = AdpScraper(clean_cfg)
        elif board == "paylocity":
            from scraper.boards.paylocity import PaylocityScraper

            s = PaylocityScraper(clean_cfg)
        elif board == "icims":
            from scraper.boards.icims import IcimsScraper

            s = IcimsScraper(clean_cfg)
        else:
            return False, 0, f"Unsupported board {board}"

        jobs = s.fetch_jobs()
        sample = jobs[0].title if jobs else "No jobs"
        return True, len(jobs), sample
    except Exception as e:
        return False, 0, str(e)


def scout_company(comp: dict[str, str]) -> dict[str, Any] | None:
    session = requests.Session()
    session.headers.update(HEADERS)
    name = comp["name"]
    symbol = comp.get("symbol", "")
    slugs = generate_candidate_slugs(name, symbol)

    # 1. Probe Workday first
    for slug in slugs:
        res = probe_workday_tenant(slug, name, session)
        if res and res.get("count", 0) > 0:
            res["sector"] = comp.get("sector", "")
            res["sub_industry"] = comp.get("sub_industry", "")
            res["symbol"] = symbol
            return res

    # 2. Probe standard ATS
    for slug in slugs:
        for board_name, prober_fn in PROBERS.items():
            res = prober_fn(slug, session)
            if res and res.get("count", 0) > 0:
                # Discard low-count BambooHR/Recruitee/Breezy/Personio collisions with short generic slugs
                if (
                    board_name in ("bamboohr", "recruitee", "breezy", "personio", "workable")
                    and res.get("count", 0) < 15
                ):
                    continue
                res["name"] = name
                res["sector"] = comp.get("sector", "")
                res["sub_industry"] = comp.get("sub_industry", "")
                res["symbol"] = symbol
                return res

    return None


def fetch_sp500_constituents() -> list[dict[str, str]]:
    """Fetch current S&P 500 constituents from local cache or Wikipedia."""
    if SP500_PATH.exists():
        try:
            with open(SP500_PATH) as f:
                return json.load(f)
        except Exception:
            pass

    from bs4 import BeautifulSoup

    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    r = requests.get(url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table", {"id": "constituents"})
    if not table:
        return []
    rows = table.find_all("tr")[1:]
    constituents: list[dict[str, str]] = []
    for row in rows:
        cols = row.find_all(["td", "th"])
        if len(cols) >= 4:
            symbol = cols[0].text.strip()
            name = cols[1].text.strip()
            sector = cols[2].text.strip()
            sub_industry = cols[3].text.strip()
            constituents.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "sector": sector,
                    "sub_industry": sub_industry,
                }
            )
    return constituents


def main():
    parser = argparse.ArgumentParser(description="Scout S&P 500 ATS Boards")
    parser.add_argument("--workers", "-w", type=int, default=30, help="Concurrency workers")
    parser.add_argument(
        "--apply", "-a", action="store_true", help="Append verified companies to config.json"
    )
    parser.add_argument("--test", action="store_true", help="Run CI tests after update")
    parser.add_argument(
        "--limit", type=int, default=None, help="Limit number of companies to scout"
    )
    args = parser.parse_args()

    sp500 = fetch_sp500_constituents()
    if not sp500:
        print("Failed to fetch S&P 500 constituents.", file=sys.stderr)
        sys.exit(1)

    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    existing_names = {c["name"].lower() for c in cfg["companies"]}

    candidates = [c for c in sp500 if c["name"].lower() not in existing_names]
    if args.limit:
        candidates = candidates[: args.limit]
    print(
        f"Probing {len(candidates)} missing S&P 500 multinationals (out of {len(sp500)} total)...\n"
    )

    discovered = []
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(scout_company, c): c for c in candidates}
        for f in concurrent.futures.as_completed(futs):
            res = f.result()
            if res:
                print(
                    f"  [FOUND] {res['name']} ({res['board']}) -> {res['count']} jobs | Sample: {res.get('sample')}"
                )
                discovered.append(res)

    print(
        f"\nProbing finished in {time.time() - t0:.1f}s. Discovered {len(discovered)} potential job boards."
    )
    print("Verifying each discovery via native board scraper...")

    verified = []
    for d in discovered:
        clean = {
            "name": d["name"],
            "board": d["board"],
        }
        if "url" in d:
            clean["url"] = d["url"]
        if "careers_base" in d:
            clean["careers_base"] = d["careers_base"]
        if "token" in d:
            clean["token"] = d["token"]
        if "slug" in d:
            clean["slug"] = d["slug"]
        if "company" in d:
            clean["company"] = d["company"]
        if "board_id" in d:
            clean["board_id"] = d["board_id"]

        ok, count, sample = verify_live_scraper(clean)
        if ok and count > 0:
            d["verified_count"] = count
            d["verified_sample"] = sample
            verified.append(d)
            print(
                f"  [VERIFIED] {d['name']} [{d.get('sector', '')}] ({d['board']}) -> {count} jobs | Sample: {sample}"
            )
        else:
            print(f"  [REJECTED] {d['name']} -> {sample}")

    print(f"\nSuccessfully verified {len(verified)} new S&P 500 multinationals!")

    # Group verified by sector
    sectors: dict[str, list[dict[str, Any]]] = {}
    for v in verified:
        sec = v.get("sector") or "Other"
        sectors.setdefault(sec, []).append(v)

    print("\n" + "=" * 60)
    print("S&P 500 MULTINATIONALS SCOUT SUMMARY BY SECTOR")
    print("=" * 60)
    for sec, comps in sorted(sectors.items()):
        print(f"\n### {sec} ({len(comps)} companies)")
        for c in comps:
            print(
                f'  * {c["name"]} ({c["board"]}) — {c["verified_count"]} active jobs | "{c["verified_sample"]}"'
            )

    if args.apply and verified:
        existing_companies = cfg.get("companies", [])
        existing_signatures = {c.get("name", "").lower() for c in existing_companies}
        added = 0
        for v in verified:
            entry = {
                "name": v["name"],
                "board": v["board"],
            }
            if "url" in v:
                entry["url"] = v["url"]
            if "careers_base" in v:
                entry["careers_base"] = v["careers_base"]
            if "token" in v:
                entry["token"] = v["token"]
            if "slug" in v:
                entry["slug"] = v["slug"]
            if "company" in v:
                entry["company"] = v["company"]
            if "board_id" in v:
                entry["board_id"] = v["board_id"]

            if entry["name"].lower() not in existing_signatures:
                existing_companies.append(entry)
                existing_signatures.add(entry["name"].lower())
                added += 1

        cfg["companies"] = existing_companies
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"\nUpdated {CONFIG_PATH.name} with {added} new verified companies.")

        if args.test:
            print("\nRunning CI tests (pytest)...")
            subprocess.run([sys.executable, "-m", "pytest", "-q"], check=True)


if __name__ == "__main__":
    main()
