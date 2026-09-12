"""Québec emploi / Emploi-Québec portal scraper.

Québec emploi is the official provincial employment platform of the
Government of Quebec (plateforme d'emploi du Gouvernement du Québec).

Search endpoint (unauthenticated JSON REST API):
    POST https://www.quebecemploi.gouv.qc.ca/search/postingFilteredAI
    Payload:
    {
      "sort": {"type": "AUTO"},
      "langue": "fr" | "en",
      "page": 1,
      "filter": {
        "inputSearch": "<keyword>",
        "adminRegion": ["06", ...],
        ...
      }
    }

Detail endpoint:
    GET https://www.quebecemploi.gouv.qc.ca/manitouLS/cache/postingJsonCS/{job_id}/{lang}
    Returns structured JSON with Schema.org JobPosting in googleForJob.key
    and labeled sections in body.

Web posting URL:
    https://www.quebecemploi.gouv.qc.ca/plateforme-emploi/poste/{job_id}

Config entries:
    {"board": "quebec_emploi", "name": "Québec emploi"}
    {"board": "quebec_emploi", "name": "Québec emploi Montréal", "region": "06"}
    {"board": "quebec_emploi", "name": "Québec emploi Tech", "query": "informatique"}
"""

from __future__ import annotations

import json
import logging
import re
from html import unescape
from typing import cast

import requests

from scraper.boards.base import BaseScraper, make_session
from scraper.config_types import QuebecEmploiConfig
from scraper.models import Job
from scraper.text import html_to_text

SEARCH_URL = "https://www.quebecemploi.gouv.qc.ca/search/postingFilteredAI"
DETAIL_URL = "https://www.quebecemploi.gouv.qc.ca/manitouLS/cache/postingJsonCS/{job_id}/{lang}"
POSTING_URL = "https://www.quebecemploi.gouv.qc.ca/plateforme-emploi/poste/{job_id}"
DEFAULT_MAX_PAGES = 10
TIMEOUT = 30

log = logging.getLogger("scraper.quebec_emploi")

ADMIN_REGION_MAP: dict[str, str] = {
    "01": "01",
    "bas-saint-laurent": "01",
    "02": "02",
    "saguenay-lac-saint-jean": "02",
    "saguenay–lac-saint-jean": "02",
    "saguenay": "02",
    "03": "03",
    "capitale-nationale": "03",
    "quebec": "03",
    "québec": "03",
    "04": "04",
    "mauricie": "04",
    "05": "05",
    "estrie": "05",
    "06": "06",
    "montreal": "06",
    "montréal": "06",
    "07": "07",
    "outaouais": "07",
    "gatineau": "07",
    "08": "08",
    "abitibi-temiscamingue": "08",
    "abitibi-témiscamingue": "08",
    "09": "09",
    "cote-nord": "09",
    "côte-nord": "09",
    "10": "10",
    "nord-du-quebec": "10",
    "nord-du-québec": "10",
    "11": "11",
    "gaspesie-iles-de-la-madeleine": "11",
    "gaspésie–îles-de-la-madeleine": "11",
    "gaspesie": "11",
    "gaspésie": "11",
    "12": "12",
    "chaudiere-appalaches": "12",
    "chaudière-appalaches": "12",
    "13": "13",
    "laval": "13",
    "14": "14",
    "lanaudiere": "14",
    "lanaudière": "14",
    "15": "15",
    "laurentides": "15",
    "16": "16",
    "monteregie": "16",
    "montérégie": "16",
    "17": "17",
    "centre-du-quebec": "17",
    "centre-du-québec": "17",
}


def _resolve_admin_regions(
    region_str: str | None,
    regions_list: list[str] | None,
    location_str: str | None,
) -> list[str]:
    """Resolve user-configured region strings into 2-digit adminRegion codes."""
    resolved: list[str] = []
    candidates: list[str] = []

    if regions_list:
        candidates.extend(regions_list)
    if region_str:
        candidates.append(region_str)
    if location_str:
        candidates.append(location_str)

    for item in candidates:
        norm = item.strip().lower()
        if norm in ADMIN_REGION_MAP:
            code = ADMIN_REGION_MAP[norm]
            if code not in resolved:
                resolved.append(code)

    return resolved


class QuebecEmploiScraper(BaseScraper):
    source = "quebec_emploi"

    def __init__(self, company: QuebecEmploiConfig) -> None:
        super().__init__(company)
        self._qc_config: QuebecEmploiConfig = company
        if "qu-bec" in self.slug:
            self.slug = self.slug.replace("qu-bec", "quebec")

    def fetch_jobs(self) -> list[Job]:
        session = make_session()
        lang = self._qc_config.get("language") or "fr"
        accept_lang = "fr-CA,fr;q=0.9,en;q=0.8" if lang == "fr" else "en-CA,en;q=0.9,fr;q=0.8"
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Accept-Language": accept_lang,
            }
        )

        query = self._qc_config.get("query") or ""
        title_filter = self._qc_config.get("title") or ""
        location_filter = self._qc_config.get("location") or ""
        region_filter = self._qc_config.get("region") or ""
        regions_filter = self._qc_config.get("regions") or []
        max_pages = self._qc_config.get("max_pages") or DEFAULT_MAX_PAGES
        fetch_details = bool(self._qc_config.get("fetch_details", False))

        resolved_regions = _resolve_admin_regions(
            region_filter or None,
            regions_filter or None,
            location_filter or None,
        )

        # Use query if provided, else title_filter as search input
        search_input = query or title_filter

        raw_items: list[dict[str, object]] = []

        for page in range(1, max_pages + 1):
            payload = {
                "sort": {"type": "AUTO"},
                "langue": lang,
                "page": page,
                "filter": {
                    "inputSearch": search_input,
                    "address": "",
                    "localisation": {"longitude": "", "latitude": "", "distance": 20},
                    "adminRegion": resolved_regions,
                    "offerType": [],
                    "commitment": [],
                    "jobDuration": [],
                    "levelEducation": [],
                    "studyDiscipline": [],
                    "mrc": [],
                    "bsq": [],
                    "scian": [],
                    "postedSince": "",
                    "excludeAgencies": False,
                    "isUkrainian": False,
                    "isExperimente": False,
                    "isSubsidized": False,
                    "isTrainingProgram": False,
                },
            }

            try:
                resp = session.post(SEARCH_URL, json=payload, timeout=TIMEOUT)
                resp.raise_for_status()
                data = cast(dict[str, object], resp.json())
            except (requests.RequestException, ValueError) as e:
                log.warning("Quebec emploi request failed on page %d: %s", page, e)
                break

            items_raw = data.get("items")
            if not isinstance(items_raw, list) or not items_raw:
                break

            page_items: list[dict[str, object]] = []
            items_list = cast(list[object], items_raw)
            for it in items_list:
                if isinstance(it, dict):
                    page_items.append(cast(dict[str, object], it))

            raw_items.extend(page_items)

            # If fewer items than a standard full block or end reached, stop
            if len(page_items) == 0:
                break

        jobs: list[Job] = []
        loc_filter_norm = location_filter.strip().lower()
        title_filter_norm = title_filter.strip().lower()

        for item in raw_items:
            job_id_val = item.get("ide_affch")
            if job_id_val is None:
                continue
            job_id = str(job_id_val).strip()
            if not job_id:
                continue

            raw_title = str(item.get("titre") or "").strip()
            employer = str(item.get("employeur") or "").strip()
            city = str(item.get("nom_ville") or "").strip()
            expiration = str(item.get("expiration_date") or "").strip()

            # Client-side filtering when specific constraints configured
            if title_filter_norm and title_filter_norm not in raw_title.lower():
                continue

            if loc_filter_norm and not resolved_regions and loc_filter_norm not in city.lower():
                continue

            company_name = employer or self.name
            loc_label = f"{city}, QC" if city else "Québec, QC"
            job_url = POSTING_URL.format(job_id=job_id)
            posted_text = f"Expires: {expiration}" if expiration else ""

            desc_chunks: list[str] = []
            if employer:
                desc_chunks.append(f"Employeur: {employer}")
            if city:
                desc_chunks.append(f"Ville: {city}")
            if expiration:
                desc_chunks.append(f"Date d'expiration: {expiration}")
            base_description = " | ".join(desc_chunks)

            if fetch_details:
                detail_desc, detail_date = self._fetch_detail(session, job_id, lang)
                if detail_desc:
                    base_description = detail_desc
                if detail_date:
                    posted_text = detail_date

            jobs.append(
                Job(
                    id=f"{self.slug}:{job_id}",
                    company=company_name,
                    title=raw_title,
                    location=loc_label,
                    locations=[loc_label],
                    url=job_url,
                    posted_on=posted_text,
                    source=self.source,
                    description=base_description,
                )
            )

        log.info("Scraped %d jobs for %s", len(jobs), self.name)
        return jobs

    def _fetch_detail(
        self,
        session: requests.Session,
        job_id: str,
        lang: str,
    ) -> tuple[str, str]:
        """Fetch job posting detail including full description and date."""
        url = DETAIL_URL.format(job_id=job_id, lang=lang)
        try:
            resp = session.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            data = cast(dict[str, object], resp.json())
        except (requests.RequestException, ValueError) as e:
            log.debug("Detail fetch failed for job %s: %s", job_id, e)
            return "", ""

        detail_desc = ""
        detail_date = ""

        # Check Schema.org JobPosting JSON-LD inside googleForJob
        g_for_job = data.get("googleForJob")
        if isinstance(g_for_job, dict):
            g_dict = cast(dict[str, object], g_for_job)
            script_raw = str(g_dict.get("key") or "")
            match = re.search(r"<script[^>]*>(.*?)</script>", script_raw, re.DOTALL)
            if match:
                try:
                    ld = cast(dict[str, object], json.loads(match.group(1)))
                    raw_desc = ld.get("description")
                    if isinstance(raw_desc, str) and raw_desc.strip():
                        detail_desc = html_to_text(unescape(raw_desc))
                    posted = ld.get("datePosted")
                    if isinstance(posted, str) and posted.strip():
                        detail_date = posted.strip()
                except ValueError:
                    pass

        # Fallback to body sections if description empty
        if not detail_desc:
            body_list = data.get("body")
            if isinstance(body_list, list):
                chunks: list[str] = []
                body_entries = cast(list[object], body_list)
                for entry in body_entries:
                    if isinstance(entry, dict):
                        entry_dict = cast(dict[str, object], entry)
                        label = str(entry_dict.get("label") or "")
                        content = str(entry_dict.get("content") or "")
                        text_val = html_to_text(unescape(content)).strip()
                        if text_val:
                            chunks.append(f"{label}:\n{text_val}")
                if chunks:
                    detail_desc = "\n\n".join(chunks)

        return detail_desc, detail_date
