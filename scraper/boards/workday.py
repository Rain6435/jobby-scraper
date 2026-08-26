"""Workday career page scraper.

Workday exposes an undocumented public API per company:
    POST https://<company>.wd<N>.myworkdayjobs.com/wday/cxs/<company>/<tenant>/jobs
Body: {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}
Response: {"total": N, "jobPostings": [...]} where each posting has
title, postedOn, locationsText, externalPath, bulletFields.

The list endpoint only reports "12 Locations" for multi-location postings, and
never includes the description — both live on the detail endpoint. The detail
fetch is skipped for a posting already known from the previous run (see
BaseScraper._cached_detail) — otherwise it's called unconditionally, ~3x the
request volume of a list-only scrape:
    GET <url minus "/jobs"><externalPath>
→ {"jobPostingInfo": {"location": "...", "additionalLocations": [...], "jobDescription": "<html>..."}}

Every posting is fetched every run, up to MAX_JOBS — no age-based cutoff or
early-pagination-stop. A job leaves the pool once it stops appearing here,
not because it crossed a fixed day count (see scraper/main.py's full-replace
semantics: a full run's stored set is exactly this run's `current`).
`posted_days` is still parsed and stored on Job (it's what
scraper/db.py::write_jobs derives posted_date from), just no longer used to
filter or skip anything here.

Some tenants' search index carries dangling entries — confirmed on Airbus's
(2026-08): a posting with only `{"bulletFields": [...]}` and every other
field absent, still searchable by that requisition id, but whose own detail
endpoint 404s with "not found: Job_Posting_Anchor_ID=…" — i.e. the list/
search index and the actual posting store have drifted apart tenant-side.
There's no valid detail to ever fetch for these, so postings with no title
are skipped before attempting one.
"""

from __future__ import annotations

import logging
import re

import requests

from scraper.boards.base import BaseScraper, make_session
from scraper.models import Job
from scraper.text import html_to_text

PAGE_SIZE = 20
MAX_JOBS = 500  # safety cap against runaway pagination
TIMEOUT = 30

log = logging.getLogger("scraper.workday")

_POSTED_RE = re.compile(r"(\d+)\+?\s+days?\s+ago", re.IGNORECASE)
_MULTI_LOC_RE = re.compile(r"^\d+\s+locations$", re.IGNORECASE)


def parse_posted_days(posted_on: str) -> int | None:
    """'Posted Today' → 0, 'Posted Yesterday' → 1, 'Posted 3 Days Ago' → 3,
    'Posted 30+ Days Ago' → 30. Unknown formats → None."""
    text = posted_on.lower()
    if "today" in text:
        return 0
    if "yesterday" in text:
        return 1
    match = _POSTED_RE.search(text)
    if match:
        return int(match.group(1))
    return None


class WorkdayScraper(BaseScraper):
    source = "workday"

    def fetch_jobs(self) -> list[Job]:
        url = self.company["url"]
        careers_base = self.company.get("careers_base", "").rstrip("/")
        detail_base = url[: -len("/jobs")] if url.endswith("/jobs") else url
        slug = self.slug

        jobs: list[Job] = []
        offset = 0
        total = None
        session = make_session()
        session.headers.update({"Accept": "application/json"})

        while total is None or (offset < total and len(jobs) < MAX_JOBS):
            log.debug("%s: fetching offset=%d", self.name, offset)
            resp = session.post(
                url,
                json={
                    "appliedFacets": {},
                    "limit": PAGE_SIZE,
                    "offset": offset,
                    "searchText": "",
                },
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            if total is None:
                # Workday only reports "total" on the first page; later pages
                # return total=0, so never overwrite it.
                total = data.get("total", 0)
                log.debug("%s: total=%d postings reported", self.name, total)
            postings = data.get("jobPostings", [])
            if not postings:
                log.debug("%s: empty page at offset=%d, stopping", self.name, offset)
                break

            for posting in postings:
                title = posting.get("title", "").strip()
                if not title:
                    # Some tenants' search index carries dangling entries —
                    # confirmed on Airbus's: a real, searchable-by-id
                    # requisition (bulletFields present) whose OWN detail
                    # endpoint 404s with "not found: Job_Posting_Anchor_ID=…",
                    # i.e. the list/search index and the actual posting store
                    # have drifted apart tenant-side. There is no valid detail
                    # to fetch for these — skip before wasting a doomed
                    # detail GET (and the resulting misleading "Detail fetch
                    # failed" warning) on a posting with nothing to show.
                    log.debug(
                        "%s: skipping posting with no title (bulletFields=%s)",
                        self.name, posting.get("bulletFields"),
                    )
                    continue

                posted_on = posting.get("postedOn", "").strip()
                posted_days = parse_posted_days(posted_on)

                external_path = posting.get("externalPath", "")
                bullet_fields = posting.get("bulletFields") or []
                external_id = bullet_fields[0] if bullet_fields else external_path
                job_id = f"{slug}:{external_id}"

                cached = self._cached_detail(job_id)
                if cached is not None:
                    # Already scraped last run — reuse its detail-only
                    # fields instead of re-fetching them.
                    locations, description = cached.locations, cached.description
                else:
                    locations, description = self._fetch_detail(
                        session, detail_base, external_path,
                        posting.get("locationsText", "").strip(),
                    )
                jobs.append(
                    Job(
                        id=job_id,
                        company=self.name,
                        title=title,
                        location=locations[0] if locations else "",
                        locations=locations,
                        url=f"{careers_base}{external_path}" if careers_base else external_path,
                        posted_on=posted_on,
                        posted_days=posted_days,
                        source=self.source,
                        description=description,
                    )
                )

            offset += PAGE_SIZE

        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    def _fetch_detail(
        self, session: requests.Session, detail_base: str,
        external_path: str, locations_text: str,
    ) -> tuple[list[str], str]:
        """Fetch the job detail endpoint for every posting (not just
        multi-location ones) to resolve 'N Locations' placeholders and get the
        full description. Returns (locations, description); on any failure,
        falls back to ([locations_text] or [], "") so a bad detail fetch never
        drops the job or crashes the run.
        """
        fallback_locations = [locations_text] if locations_text else []
        try:
            resp = session.get(f"{detail_base}{external_path}", timeout=TIMEOUT)
            resp.raise_for_status()
            info = resp.json().get("jobPostingInfo", {})
            if _MULTI_LOC_RE.match(locations_text):
                locations = [info.get("location", "")] + list(info.get("additionalLocations", []))
                locations = [loc for loc in locations if loc] or fallback_locations
            else:
                locations = fallback_locations
            description = html_to_text(info.get("jobDescription", ""))
            return locations, description
        except Exception:
            log.warning("Detail fetch failed for %s%s", detail_base, external_path)
            return fallback_locations, ""
