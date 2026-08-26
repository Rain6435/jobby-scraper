"""Canadian Museums Association "Jobs in Heritage" board scraper.

Not a per-employer integration, like usajobs/climatebase — one config entry
covers the whole board's listing. Confirmed live via plain `curl` (matching
FIELD_EXPANSION_RESEARCH.md's earlier robots.txt finding for museums.ca):
no CAPTCHA, no bot-detection challenge anywhere in the flow — both the list
page and each posting's detail page return real content to a bare
`requests` GET.

List page (server-rendered HTML, no JS/API needed):
    GET https://museums.ca/site/aboutthecma/careersheritageycw/jobsinheritage
Each posting is a `div.row.careerList` containing five `div.col-sm-*` cells
in a fixed order — title, organization, location, job type, application
deadline — each wrapping one anchor to the same detail URL
(`companyRosterDetails.html?companyId=<id>&companyRosterId=87`). The
deadline is an application deadline, not a posting date — no real posted
date is exposed anywhere on this board, so posted_on/posted_days are left
empty/None like bamboohr.py/rippling.py (age tracked via first_seen
instead, per BaseScraper's documented convention).

Detail page: `<h1>` is the title (already known from the list page, not
re-parsed); the full description — LOCATION/JOB TYPE/LANGUAGE/SALARY/
DEADLINE fields plus free-text body — lives inside one `<table>` element;
html_to_text's tag-stripping over the whole table's HTML gives a clean,
readable plain-text description without needing to parse each row
individually.

Only ~20 postings live at build time (a specialized single-association
board, not a large aggregator) — thin but genuine, matching the same
small-but-real-slice precedent as this project's other niche sources
(Climatebase for environmental_science, AAFS Career Center for
forensic_science). Config: {"board": "cma_heritage", "name": "..."}."""

from __future__ import annotations

import logging
import re
from html import unescape

import requests

from scraper.boards.base import BaseScraper, make_session
from scraper.models import Job
from scraper.text import html_to_text

LIST_URL = "https://museums.ca/site/aboutthecma/careersheritageycw/jobsinheritage"
TIMEOUT = 30

_CAREER_ROW_RE = re.compile(
    r'<div class="row p-2 careerList">(.*?)</div>\s*(?=<!--ola:rule|<div class="row p-2 careerList">|$)',
    re.DOTALL,
)
_CELL_RE = re.compile(r'<a href="([^"]+)"[^>]*>([^<]*)</a>')
_COMPANY_ID_RE = re.compile(r"companyId=(\d+)")

log = logging.getLogger("scraper.cma_heritage")


class CmaHeritageScraper(BaseScraper):
    source = "cma_heritage"

    def fetch_jobs(self) -> list[Job]:
        session = make_session()
        resp = session.get(LIST_URL, timeout=TIMEOUT)
        resp.raise_for_status()

        postings = self._extract_postings(resp.text)
        log.debug("%s: %d posting(s) found", self.name, len(postings))

        jobs: list[Job] = []
        for posting in postings:
            description = self._fetch_description(session, posting["url"])
            jobs.append(
                Job(
                    id=f"{self.slug}:{posting['company_id']}",
                    company=posting["company"],
                    title=posting["title"],
                    location=posting["location"],
                    locations=[posting["location"]] if posting["location"] else [],
                    url=posting["url"],
                    posted_on="",
                    posted_days=None,
                    source=self.source,
                    description=description,
                )
            )
        return jobs

    @staticmethod
    def _extract_postings(html: str) -> list[dict[str, str]]:
        postings: list[dict[str, str]] = []
        for row_match in _CAREER_ROW_RE.finditer(html):
            cells = _CELL_RE.findall(row_match.group(1))
            if len(cells) < 3:
                continue
            url, title = cells[0]
            _, company = cells[1]
            _, location = cells[2]
            company_id_match = _COMPANY_ID_RE.search(url)
            if not company_id_match or not title.strip():
                continue
            postings.append(
                {
                    "url": url,
                    "title": unescape(title.strip()),
                    "company": unescape(company.strip()),
                    "location": unescape(location.strip()),
                    "company_id": company_id_match.group(1),
                }
            )
        return postings

    @staticmethod
    def _fetch_description(session: requests.Session, url: str) -> str:
        """Best-effort: returns "" on any failure rather than dropping the
        posting, matching this codebase's fail-soft-on-missing-optional-
        field pattern."""
        try:
            resp = session.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            table_match = re.search(r"<table.*?</table>", resp.text, re.DOTALL)
            if not table_match:
                return ""
            return html_to_text(table_match.group(0))
        except Exception as e:
            log.warning("cma_heritage: detail fetch failed for %s: %s", url, e)
            return ""
