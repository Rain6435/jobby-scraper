"""Canadian Institute of Planners (CIP) National Planning Job Board scraper.

Not a per-employer integration — one config entry covers the whole board.
Confirmed live via `curl`: no CAPTCHA, no bot-detection challenge, though
it does 403 the bare `python-requests` User-Agent (fixed with the same
`Mozilla/5.0` header idc_career_centre.py and several other boards already
use). Backed by the same **WP Job Manager** WordPress plugin/feed shape as
idc_career_centre.py — parsing is shared via wp_job_manager.py:

    GET https://www.cip-icu.ca/?feed=job_feed&job_types=consultancy,contract,full-time,internship,part-time,request-for-proposals-rfp,student-co-op-position,temporary

No pagination param found — the feed always returns WordPress's default 10
most recent postings; thin but real (Planner I/II, Development Planner,
Commissioner Planning & Building — real municipal/provincial employers:
City of Mississauga, City of Hamilton, Regional Municipality of Wood
Buffalo, etc.), matching this project's precedent for shipping small
genuine slices.

Directly targets `urban_planning`, a field this project's research (see
FIELD_EXPANSION_RESEARCH.md) tried and dropped entirely for zero GC Jobs
coverage (confirms the doc's own finding: planning is a municipal/
provincial labor market GC Jobs, federal-only, structurally cannot reach).
Many real postings here are bare "Planner I"/"Planner II" with no
disambiguating phrase — deliberately NOT matched by a bare "planner"
taxonomy hint (would collide with Financial Planner/Event Planner/Wedding
Planner), so some real postings from this board won't classify into
urban_planning; accepted tradeoff, same discipline as every other
bare-word trap avoided elsewhere in this taxonomy. Config:
{"board": "cip_planning", "name": "..."}."""

from __future__ import annotations

import logging

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.wp_job_manager import parse_wp_job_manager_feed
from scraper.models import Job

FEED_URL = (
    "https://www.cip-icu.ca/?feed=job_feed"
    "&job_types=consultancy%2Ccontract%2Cfull-time%2Cinternship%2Cpart-time"
    "%2Crequest-for-proposals-rfp%2Cstudent-co-op-position%2Ctemporary"
)
TIMEOUT = 30

log = logging.getLogger("scraper.cip_planning")


class CipPlanningScraper(BaseScraper):
    source = "cip_planning"

    def fetch_jobs(self) -> list[Job]:
        session = make_session()
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/rss+xml"})
        resp = session.get(FEED_URL, timeout=TIMEOUT)
        resp.raise_for_status()

        jobs = parse_wp_job_manager_feed(resp.text, self.source, self.slug, self.name)
        log.debug("%s: %d posting(s) found", self.name, len(jobs))
        return jobs
