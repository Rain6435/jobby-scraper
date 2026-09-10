"""Jobvite public XML job feed scraper.

One unauthenticated GET returns every open position as XML — no pagination,
no per-job detail calls:
    GET https://app.jobvite.com/CompanyJobs/Xml.aspx?c=<company_id>
Root <result> (or <jobs>) holds repeated <job> children: id, title, location,
date, detail-url, description (HTML). Config:
{"board": "jobvite", "company_id": "<companyEId>"}.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import cast

from scraper.boards.base import BaseScraper, make_session
from scraper.boards.greenhouse import relative_day_text
from scraper.config_types import JobviteConfig
from scraper.models import Job
from scraper.text import html_to_text

API = "https://app.jobvite.com/CompanyJobs/Xml.aspx?c={company_id}"
TIMEOUT = 30

log = logging.getLogger("scraper.jobvite")


def parse_jobvite_date(raw_date: str) -> int | None:
    """Parse various date formats commonly used in Jobvite XML feeds into whole days ago."""
    if not raw_date:
        return None
    cleaned = raw_date.strip()
    # Try ISO-8601
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        delta = datetime.now(UTC) - dt
        return max(delta.days, 0)
    except ValueError:
        pass

    # Try RFC-2822
    try:
        dt = parsedate_to_datetime(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        delta = datetime.now(UTC) - dt
        return max(delta.days, 0)
    except (TypeError, ValueError):
        pass

    # Try standard date patterns: MM/DD/YYYY, YYYY-MM-DD, etc.
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%B %d, %Y"):
        try:
            dt = datetime.strptime(cleaned, fmt).replace(tzinfo=UTC)
            delta = datetime.now(UTC) - dt
            return max(delta.days, 0)
        except ValueError:
            continue

    return None


class JobviteScraper(BaseScraper):
    source = "jobvite"

    def fetch_jobs(self) -> list[Job]:
        cfg: JobviteConfig = cast(JobviteConfig, self.company)
        company_id = cfg["company_id"]
        session = make_session()
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/xml, text/xml"})

        log.debug("%s: fetching job list", self.name)
        resp = session.get(API.format(company_id=company_id), timeout=TIMEOUT)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        job_nodes = root.findall(".//job")
        log.debug("%s: %d job nodes returned", self.name, len(job_nodes))

        jobs: list[Job] = []
        for node in job_nodes:
            job_id = (node.findtext("id") or node.findtext("requisition-id") or "").strip()
            if not job_id:
                continue

            locations = self._locations(node)
            raw_date = (node.findtext("date") or "").strip()
            posted_days = parse_jobvite_date(raw_date)
            url = (node.findtext("detail-url") or "").strip()
            title = (node.findtext("title") or "").strip()
            desc_html = (node.findtext("description") or "").strip()

            jobs.append(
                Job(
                    id=f"{self.slug}:{job_id}",
                    company=self.name,
                    title=title,
                    location=locations[0] if locations else "",
                    locations=locations,
                    url=url,
                    posted_on=relative_day_text(posted_days),
                    posted_days=posted_days,
                    source=self.source,
                    description=html_to_text(desc_html),
                )
            )

        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    @staticmethod
    def _locations(node: ET.Element) -> list[str]:
        raw_loc = (node.findtext("location") or "").strip()
        if not raw_loc:
            return []
        # Location in Jobvite can be a single string or semicolon/newline-separated
        parts = [p.strip() for p in raw_loc.replace(";", "\n").splitlines() if p.strip()]
        return parts if parts else [raw_loc]
