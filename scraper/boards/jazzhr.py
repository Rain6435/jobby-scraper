"""JazzHR public XML job feed scraper.

One unauthenticated GET returns every open position as XML — no pagination,
no per-job detail calls:
    GET https://app.jazz.co/feeds/export/jobs/<company>
Root <jobs> holds repeated <job> children: id, title, department, url,
city, state, country, description (HTML). Config:
{"board": "jazzhr", "company": "<subdomain>"}.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import cast

from scraper.boards.base import BaseScraper, make_session
from scraper.config_types import JazzHrConfig
from scraper.models import Job
from scraper.text import html_to_text

API = "https://app.jazz.co/feeds/export/jobs/{company}"
TIMEOUT = 30

log = logging.getLogger("scraper.jazzhr")


class JazzHrScraper(BaseScraper):
    source = "jazzhr"

    def fetch_jobs(self) -> list[Job]:
        cfg: JazzHrConfig = cast(JazzHrConfig, self.company)
        company = cfg["company"]
        session = make_session()
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/xml, text/xml"})

        log.debug("%s: fetching job list", self.name)
        resp = session.get(API.format(company=company), timeout=TIMEOUT)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        job_nodes = root.findall(".//job")
        log.debug("%s: %d job nodes returned", self.name, len(job_nodes))

        jobs: list[Job] = []
        for node in job_nodes:
            job_id = (node.findtext("id") or "").strip()
            if not job_id:
                continue

            locations = self._locations(node)
            url = (node.findtext("url") or "").strip()
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
                    posted_on="",
                    posted_days=None,
                    source=self.source,
                    description=html_to_text(desc_html),
                )
            )

        log.debug("%s: fetched %d jobs", self.name, len(jobs))
        return jobs

    @staticmethod
    def _locations(node: ET.Element) -> list[str]:
        city = (node.findtext("city") or "").strip()
        state = (node.findtext("state") or "").strip()
        country = (node.findtext("country") or "").strip()

        loc_parts: list[str] = []
        if city:
            loc_parts.append(city)
        if state:
            loc_parts.append(state)
        if country and country.upper() not in ("US", "USA", "UNITED STATES"):
            loc_parts.append(country)

        if loc_parts:
            return [", ".join(loc_parts)]
        if country:
            return [country]
        return []
