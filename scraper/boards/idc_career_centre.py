"""Interior Designers of Canada (IDC) Career Centre board scraper.

Not a per-employer integration, like usajobs/climatebase/cma_heritage — one
config entry covers the whole board. Confirmed live via `curl`: no
CAPTCHA, no bot-detection challenge — but it does 403 the bare
`python-requests` User-Agent specifically (same as several other boards in
this codebase — ashby.py, greenhouse.py, etc. — already set a
`Mozilla/5.0` User-Agent for the same reason). Backed by the **WP Job
Manager** WordPress plugin's standard RSS feed (a documented, well-known
plugin pattern — not a bespoke/reverse-engineered API); parsing is shared
with cip_planning.py via wp_job_manager.py, since both sites turned out to
run the same plugin/feed shape:

    GET https://idcanada.org/?feed=job_feed&job_types=contract,freelance,full-time,internship,part-time,temporary

No pagination param found — the feed always returns WordPress's default 10
most recent postings; thin but real, matching this project's precedent for
shipping small genuine slices.

Directly targets `interior_design`, a field this project's research (see
FIELD_EXPANSION_RESEARCH.md) tried and dropped entirely for zero GC Jobs
coverage — this is now that field's first real source. Config:
{"board": "idc_career_centre", "name": "..."}."""

from __future__ import annotations

import logging

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.wp_job_manager import parse_wp_job_manager_feed
from scraper.models import Job

FEED_URL = (
    "https://idcanada.org/?feed=job_feed"
    "&job_types=contract%2Cfreelance%2Cfull-time%2Cinternship%2Cpart-time%2Ctemporary"
)
TIMEOUT = 30

log = logging.getLogger("scraper.idc_career_centre")


class IdcCareerCentreScraper(BaseScraper):
    source = "idc_career_centre"

    def fetch_jobs(self) -> list[Job]:
        session = make_session()
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/rss+xml"})
        resp = session.get(FEED_URL, timeout=TIMEOUT)
        resp.raise_for_status()

        jobs = parse_wp_job_manager_feed(resp.text, self.source, self.slug, self.name)
        log.debug("%s: %d posting(s) found", self.name, len(jobs))
        return jobs
