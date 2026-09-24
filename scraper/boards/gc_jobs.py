"""Government of Canada (GC Jobs / Emplois GC) portal scraper.

The Public Service Resourcing System (PSRS-SRFP) powers the official
Government of Canada career portal at emploisfp-psjobs.cfp-psc.gc.ca.

Scraping requires a 3-step session handshake:
    1. GET https://emploisfp-psjobs.cfp-psc.gc.ca/psrs-srfp/applicant/page2440?toggleLanguage={lang}
       Establishes JSESSIONID cookie.
    2. GET .../page2440?toggleLanguage={lang}&ajaxSetInternalAccess=1
       Enables search result visibility.
    3. GET .../page2440?toggleLanguage={lang}&isSecondPartOfPage=1&isInitialNetworkCheck=1
       Returns page 1 of all open public competitions (~400-500 live jobs).

Pagination:
    GET .../page2440?requestedPage={p}&tab=1&log=false&isSecondPartOfPage=1

Detail posters (no session required):
    GET https://emploisfp-psjobs.cfp-psc.gc.ca/psrs-srfp/applicant/page1800?poster={poster}&toggleLanguage={lang}

Config entry:
    {"board": "gc_jobs", "name": "Government of Canada"}
    {"board": "gc_jobs", "name": "Statistics Canada", "department": "Statistics Canada"}
    {"board": "gc_jobs", "name": "Health Canada", "department": "Health Canada", "location": "Ottawa"}
"""

from __future__ import annotations

import logging
import math
import re
from html import unescape
from typing import cast

import requests

from scraper.boards.base import BaseScraper, make_session
from scraper.config_types import GCJobsConfig
from scraper.models import Job
from scraper.text import html_to_text

BASE_URL = "https://emploisfp-psjobs.cfp-psc.gc.ca/psrs-srfp/applicant/page2440"
POSTER_URL = "https://emploisfp-psjobs.cfp-psc.gc.ca/psrs-srfp/applicant/page1800"
PAGE_SIZE = 20
DEFAULT_MAX_PAGES = 25  # ~500 jobs by default (full federal listing is ~400-450)
TIMEOUT = 30

log = logging.getLogger("scraper.gc_jobs")


def _split_locations(loc_str: str) -> list[str]:
    """Split location text containing multiple municipalities into individual locations."""
    if not loc_str or loc_str == "⭐":
        return []
    if ")," in loc_str:
        parts: list[str] = []
        for piece in loc_str.split("),"):
            cleaned = piece.strip()
            if not cleaned:
                continue
            if not cleaned.endswith(")"):
                cleaned += ")"
            parts.append(cleaned)
        return parts
    return [loc_str.strip()]


class GCJobsScraper(BaseScraper):
    source = "gc_jobs"

    def __init__(
        self,
        company: GCJobsConfig,
        settings: dict[str, object] | None = None,
        previous: dict[str, Job] | None = None,
    ) -> None:
        super().__init__(company, settings, previous)
        self._gc_config: GCJobsConfig = company

    def fetch_jobs(self) -> list[Job]:
        session = make_session()
        lang = self._gc_config.get("language") or "en"
        accept_lang = "fr-CA,fr;q=0.9,en;q=0.8" if lang == "fr" else "en-CA,en;q=0.9,fr;q=0.8"
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": accept_lang,
            }
        )

        # Step 1: Initialize session to establish JSESSIONID cookie
        try:
            r1 = session.get(f"{BASE_URL}?toggleLanguage={lang}", timeout=TIMEOUT)
            r1.raise_for_status()
        except requests.RequestException as e:
            log.warning("Failed to initialize GC Jobs session: %s", e)
            return []

        # Step 2: Set internal access state via XMLHttpRequest
        try:
            session.get(
                f"{BASE_URL}?toggleLanguage={lang}&ajaxSetInternalAccess=1",
                headers={
                    "Referer": r1.url,
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                },
                timeout=TIMEOUT,
            )
        except requests.RequestException as e:
            log.warning("Failed to set GC Jobs access state: %s", e)
            return []

        # Step 3: Fetch page 1 of search results
        try:
            r3 = session.get(
                f"{BASE_URL}?toggleLanguage={lang}&isSecondPartOfPage=1&isInitialNetworkCheck=1",
                headers={"Referer": r1.url},
                timeout=TIMEOUT,
            )
            r3.raise_for_status()
        except requests.RequestException as e:
            log.warning("Failed to fetch initial GC Jobs results: %s", e)
            return []

        # Determine total page count from open jobs count
        total_pages = 1
        count_match = re.search(r"searchResultTabSelected.*?\((\d+)\)", r3.text, re.DOTALL)
        if not count_match:
            count_match = re.search(r"\(([\d\s]+)\)", r3.text)
        if count_match:
            try:
                total_jobs = int(count_match.group(1).replace(" ", ""))
                total_pages = math.ceil(total_jobs / PAGE_SIZE)
            except ValueError:
                total_pages = 1

        max_pages = self._gc_config.get("max_pages") or DEFAULT_MAX_PAGES
        pages_to_fetch = min(total_pages, max_pages)

        # Parse page 1 results
        raw_items: list[tuple[str, str, str, str, str, str, str]] = self._parse_result_page(r3.text)

        # Fetch subsequent pages
        for page_num in range(2, pages_to_fetch + 1):
            page_url = f"{BASE_URL}?requestedPage={page_num}&tab=1&log=false&isSecondPartOfPage=1"
            try:
                p_resp = session.get(page_url, headers={"Referer": r1.url}, timeout=TIMEOUT)
                p_resp.raise_for_status()
                items = self._parse_result_page(p_resp.text)
                if not items:
                    break
                raw_items.extend(items)
            except requests.RequestException as e:
                log.warning("Failed to fetch GC Jobs page %d: %s", page_num, e)
                break

        # Apply filters (department, location, title)
        dept_filter = (self._gc_config.get("department") or "").strip().lower()
        loc_filter = (self._gc_config.get("location") or "").strip().lower()
        title_filter = (self._gc_config.get("title") or "").strip().lower()

        filtered_items: list[tuple[str, str, str, str, str, str, str]] = []
        for item in raw_items:
            _, title, dept, loc, _, _, _ = item
            if title_filter and title_filter not in title.lower():
                continue
            if dept_filter and dept_filter not in dept.lower():
                continue
            if loc_filter and loc_filter not in loc.lower():
                continue
            filtered_items.append(item)

        should_fetch_details = self._gc_config.get("fetch_details", False)
        details: dict[str, tuple[object, ...]] = {}
        if should_fetch_details and filtered_items:
            job_ids = [f"{self.slug}:{poster_id}" for poster_id, _, _, _, _, _, _ in filtered_items]
            details = self._fetch_details_concurrent(
                job_ids,
                ("description",),
                lambda full_id: self._fetch_detail(session, full_id.split(":", 1)[1], lang),
                max_workers=8,
            )

        jobs: list[Job] = []
        for poster_id, title, dept, loc, closing_date, language, salary in filtered_items:
            full_id = f"{self.slug}:{poster_id}"
            locations = _split_locations(loc)
            primary_location = locations[0] if locations else loc

            description = ""
            if full_id in details:
                description = cast(str, details[full_id][0])

            if not description:
                desc_parts: list[str] = []
                if dept:
                    desc_parts.append(f"Department: {dept}")
                if loc:
                    desc_parts.append(f"Location: {loc}")
                if language:
                    desc_parts.append(f"Language: {language}")
                if salary:
                    desc_parts.append(f"Salary: {salary}")
                if closing_date:
                    desc_parts.append(f"Closing date: {closing_date}")
                description = " | ".join(desc_parts)

            # Use department as company if available, fallback to config name
            company_name = dept or self.name

            jobs.append(
                Job(
                    id=full_id,
                    company=company_name,
                    title=title,
                    location=primary_location,
                    locations=locations,
                    url=f"{POSTER_URL}?poster={poster_id}&toggleLanguage={lang}",
                    posted_on=f"Closing: {closing_date}" if closing_date else "",
                    source=self.source,
                    description=description,
                    # company is the department (dept or self.name fallback
                    # above); company_group is always the config entry's own
                    # name so every department's jobs can still be found
                    # under one "Government of Canada" umbrella downstream.
                    company_group=self.name,
                )
            )

        log.info("Scraped %d jobs for %s", len(jobs), self.name)
        return jobs

    def _parse_result_page(self, html: str) -> list[tuple[str, str, str, str, str, str, str]]:
        """Extract (poster_id, title, dept, location, closing_date, language, salary) from HTML."""
        blocks = html.split('<li class="searchResult">')[1:]
        results: list[tuple[str, str, str, str, str, str, str]] = []

        for raw_block in blocks:
            block = raw_block.split("</li>")[0]
            m_poster = re.search(
                r"href=[\"\'][^\"\']*poster=(\d+)[^\"\']*[\"\'][^>]*>(.*?)</a>",
                block,
                re.DOTALL,
            )
            if not m_poster:
                continue

            poster_id = m_poster.group(1).strip()
            raw_title = m_poster.group(2)
            title = unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
            if not poster_id or not title:
                continue

            cells = re.findall(r"<div class=[\"\']tableCell[\"\']>(.*?)</div>", block, re.DOTALL)
            dept_parts: list[str] = []
            location_parts: list[str] = []
            closing_date = ""
            language = ""
            salary = ""

            if len(cells) >= 1:
                lines0 = [
                    line.strip() for line in html_to_text(cells[0]).splitlines() if line.strip()
                ]
                for line in lines0:
                    line_lower = line.lower()
                    if "closing date:" in line_lower or "date de clôture" in line_lower:
                        closing_date = line.split(":", 1)[1].strip()
                    elif not dept_parts:
                        dept_parts.append(line)
                    elif line.startswith("-") or line.startswith("–"):
                        dept_parts.append(line.lstrip("-– ").strip())
                    else:
                        location_parts.append(line)

            if len(cells) >= 2:
                lines1 = [
                    line.strip() for line in html_to_text(cells[1]).splitlines() if line.strip()
                ]
                for line in lines1:
                    if "$" in line:
                        salary = line
                    elif not language:
                        language = line

            dept = " - ".join(dept_parts)
            location = ", ".join(location_parts)
            results.append((poster_id, title, dept, location, closing_date, language, salary))

        return results

    def _fetch_detail(
        self, session: requests.Session, poster_id: str, lang: str
    ) -> tuple[object, ...]:
        """Fetch and extract clean plain-text role description from poster detail page."""
        url = f"{POSTER_URL}?poster={poster_id}&toggleLanguage={lang}"
        try:
            resp = session.get(url, timeout=TIMEOUT)
            if resp.status_code != 200:
                return ("",)
            raw_html = resp.text
            main_match = re.search(r"<main\b[^>]*>(.*?)</main>", raw_html, re.DOTALL)
            content = main_match.group(1) if main_match else raw_html
            content = re.sub(
                r"<(script|style|nav|footer|header)\b[^>]*>.*?</\1>",
                "",
                content,
                flags=re.DOTALL,
            )
            return (html_to_text(content),)
        except requests.RequestException as e:
            log.debug("Failed to fetch detail for GC Jobs poster %s: %s", poster_id, e)
            return ("",)
