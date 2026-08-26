"""Personio public job board scraper.

One unauthenticated GET returns every open position as XML — no pagination,
no per-job detail calls:
    GET https://<company>.jobs.personio.de/xml
Root <workzag-jobs> holds repeated <position> children: id, name (title),
office (primary location), additionalOffices/office (secondary locations),
createdAt (ISO-8601 with offset), jobDescriptions/jobDescription (repeated
name+value HTML sections). There is no job URL in the feed — it's built as
https://<company>.jobs.personio.de/job/<id>. Config:
{"board": "personio", "company": "<subdomain>"}.

Uses stdlib xml.etree.ElementTree rather than a JSON parser — Python 3.8+
disables DTD/external-entity resolution by default, so this is safe against
untrusted network XML without an extra dependency (matches scraper/text.py's
no-external-dependency approach to HTML parsing).
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import posted_days_from_iso, relative_day_text
from scraper.models import Job
from scraper.text import html_to_text

API = "https://{company}.jobs.personio.de/xml"
JOB_URL = "https://{company}.jobs.personio.de/job/{id}"
TIMEOUT = 30

log = logging.getLogger("scraper.personio")


class PersonioScraper(BaseScraper):
    source = "personio"

    def fetch_jobs(self) -> list[Job]:
        company = self.company["company"]
        session = make_session()
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/xml"})

        log.debug("%s: fetching job list", self.name)
        resp = session.get(API.format(company=company), timeout=TIMEOUT)
        resp.raise_for_status()
        # Parse raw bytes, not resp.text — the server's Content-Type header omits
        # a charset, so requests falls back to guessing ISO-8859-1 even though the
        # body is UTF-8 (per its own XML declaration); ElementTree reads that
        # declaration correctly when given bytes.
        root = ET.fromstring(resp.content)
        positions = root.findall("position")
        log.debug("%s: %d positions returned", self.name, len(positions))

        jobs: list[Job] = []
        for pos in positions:
            job_id = pos.findtext("id", "")
            locations = self._locations(pos)
            posted_days = posted_days_from_iso(pos.findtext("createdAt", ""))
            jobs.append(
                Job(
                    id=f"{self.slug}:{job_id}",
                    company=self.name,
                    title=(pos.findtext("name") or "").strip(),
                    location=locations[0] if locations else "",
                    locations=locations,
                    url=JOB_URL.format(company=company, id=job_id),
                    posted_on=relative_day_text(posted_days),
                    posted_days=posted_days,
                    source=self.source,
                    description=self._description(pos),
                )
            )
        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    @staticmethod
    def _locations(pos: ET.Element) -> list[str]:
        """Primary office plus any additionalOffices, flattened to strings."""
        locs = [pos.findtext("office")]
        locs += [o.text for o in pos.findall("additionalOffices/office")]
        return [loc for loc in locs if loc]

    @staticmethod
    def _description(pos: ET.Element) -> str:
        """Concatenate each jobDescriptions/jobDescription's name (heading) and
        HTML value into one block, then strip to plain text."""
        parts = []
        for section in pos.findall("jobDescriptions/jobDescription"):
            heading = (section.findtext("name") or "").strip()
            value = (section.findtext("value") or "").strip()
            if heading:
                parts.append(f"<h3>{heading}</h3>{value}")
            elif value:
                parts.append(value)
        return html_to_text("".join(parts))
