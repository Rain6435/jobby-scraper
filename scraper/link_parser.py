"""Single job posting parser by URL.

Extracts normalized Job objects from individual job posting links across major
ATS platforms (Workday, Greenhouse, Ashby, Lever, SmartRecruiters, Rippling,
BambooHR, Workable, Breezy, Recruitee, Personio) via direct API calls, with
automatic fallback to generic Schema.org (JSON-LD) JobPosting and OpenGraph HTML
metadata extraction for arbitrary job links.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from dataclasses import asdict
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlparse

import requests

from scraper.boards.base import make_session, slugify
from scraper.boards.gc_jobs import parse_transition_page
from scraper.boards.greenhouse import posted_days_from_iso
from scraper.boards.lever import posted_days_from_epoch_ms
from scraper.boards.workable import posted_days_from_date_str
from scraper.boards.workday import parse_posted_days
from scraper.config_types import CompanyConfig, ConfigFile
from scraper.models import Job
from scraper.text import html_to_text

log = logging.getLogger("scraper.link_parser")

DEFAULT_TIMEOUT = 25
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


class JobParseError(Exception):
    """Raised when a job posting URL cannot be fetched or parsed."""


class CompanyLookup:
    """Fast in-memory index for resolving companies from config.json."""

    def __init__(self, config_path: Path | str | None = None) -> None:
        self.config_path: Path | str | None = config_path
        self._by_board_key: dict[tuple[str, str], CompanyConfig] = {}
        self._by_host: dict[str, CompanyConfig] = {}
        self._load(config_path or CONFIG_PATH)

    def _load(self, path: Path | str) -> None:
        p = Path(path)
        if not p.is_file():
            return
        try:
            with open(p, encoding="utf-8") as f:
                data: ConfigFile = json.load(f)
            for c in data.get("companies", []):
                board = c.get("board", "").lower()
                name = c.get("name", "")
                if not board or not name:
                    continue

                raw_entry = cast("dict[str, object]", c)

                # Index board-specific identifiers
                ident: str | None = None
                if board == "workday":
                    url = str(raw_entry.get("url") or "")
                    m = re.search(r"myworkdayjobs\.com/wday/cxs/([^/]+)/", url)
                    if m:
                        ident = m.group(1).lower()
                    else:
                        parsed = urlparse(url)
                        ident = parsed.netloc.split(".")[0].lower()
                elif board in ("greenhouse",):
                    ident = str(raw_entry.get("token") or "").lower()
                elif board in ("ashby",):
                    ident = str(raw_entry.get("slug") or "").lower()
                elif board in (
                    "lever",
                    "smartrecruiters",
                    "bamboohr",
                    "workable",
                    "recruitee",
                    "breezy",
                    "personio",
                ):
                    ident = str(raw_entry.get("company") or "").lower()
                elif board == "rippling":
                    ident = str(raw_entry.get("board_id") or "").lower()
                elif board == "gc_jobs":
                    ident = "government-of-canada"
                    self._by_host["emploisfp-psjobs.cfp-psc.gc.ca"] = c

                if ident:
                    self._by_board_key[(board, ident)] = c

                # Index hostname if present in url or careers_base
                for url_key in ("url", "careers_base"):
                    target_url = str(raw_entry.get(url_key) or "")
                    if target_url:
                        host = urlparse(target_url).netloc.lower()
                        if host:
                            self._by_host[host] = c
        except Exception as exc:
            log.warning("Failed to load config.json for company lookup: %s", exc)

    def resolve(
        self,
        board: str,
        identifier: str | None = None,
        host: str | None = None,
    ) -> tuple[str, str, str]:
        """Return (company_name, company_blurb, default_country)."""
        cfg: CompanyConfig | None = None
        if identifier:
            cfg = self._by_board_key.get((board.lower(), identifier.lower()))
        if cfg is None and host:
            cfg = self._by_host.get(host.lower())

        if cfg:
            return (
                cfg.get("name", ""),
                cfg.get("blurb", ""),
                cfg.get("default_country", ""),
            )

        fallback_name = "Unknown"
        if identifier:
            fallback_name = identifier.replace("-", " ").title()
        elif host:
            parts = host.lower().split(".")
            if (
                parts[0]
                in ("careers", "jobs", "recruiting", "apply", "career", "job", "ats", "work")
                and len(parts) > 2
            ):
                fallback_name = parts[1].replace("-", " ").title()
            else:
                fallback_name = parts[0].replace("-", " ").title()
        return fallback_name, "", ""


def _extract_workday_params(url: str) -> tuple[str, str, str, str] | None:
    """Extract (tenant, site, job_path, host) from Workday URL."""
    parsed = urlparse(url)
    host = parsed.netloc
    if "myworkdayjobs.com" not in host:
        return None

    tenant = host.split(".")[0]
    path = parsed.path

    # Case 1: Already CXS API URL: /wday/cxs/<tenant>/<site>/job/<job_path>
    cxs_m = re.match(
        r"^/wday/cxs/(?P<tenant>[^/]+)/(?P<site>[^/]+)/(?:job|details)/(?P<path>.+)$",
        path,
        re.IGNORECASE,
    )
    if cxs_m:
        return cxs_m.group("tenant"), cxs_m.group("site"), cxs_m.group("path"), host

    # Case 2: Standard public URL: /(?:en-[A-Za-z]{2,4}/)?<site>/(?:job|details)/<job_path>
    std_m = re.match(
        r"^(?:/[a-z]{2}(?:-[A-Za-z]{2,4})?)?/(?P<site>[^/]+)/(?:job|details)/(?P<path>.+)$",
        path,
        re.IGNORECASE,
    )
    if std_m:
        return tenant, std_m.group("site"), std_m.group("path"), host

    return None


def _parse_workday(
    url: str,
    session: requests.Session,
    lookup: CompanyLookup,
) -> Job | None:
    params = _extract_workday_params(url)
    if not params:
        return None
    tenant, site, job_path, host = params

    api_url = f"https://{host}/wday/cxs/{tenant}/{site}/job/{job_path}"
    headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
    try:
        resp = session.get(api_url, headers=headers, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        raw_json: object = resp.json()
        payload = cast("dict[str, object]", raw_json) if isinstance(raw_json, dict) else {}
    except Exception as exc:
        raise JobParseError(f"Workday API request failed for {url}: {exc}") from exc

    raw_info = payload.get("jobPostingInfo")
    info = cast("dict[str, object]", raw_info) if isinstance(raw_info, dict) else {}
    if not info:
        raise JobParseError(f"Workday response contains no jobPostingInfo for {url}")

    title = str(info.get("title") or "").strip() or "Unknown Title"
    job_req_id = str(info.get("jobReqId") or "").strip()
    if not job_req_id:
        job_req_id = job_path.rsplit("_", 1)[-1]

    company_name, company_blurb, default_country = lookup.resolve("workday", tenant, host)
    slug = slugify(company_name)

    loc = str(info.get("location") or "").strip()
    raw_add_locs = info.get("additionalLocations")
    add_locs: list[str] = []
    if isinstance(raw_add_locs, list):
        for item in cast("list[object]", raw_add_locs):
            val = str(item).strip()
            if val:
                add_locs.append(val)
    locations = ([loc] if loc else []) + add_locs

    raw_posted = str(info.get("postedOn") or "").strip()
    posted_days = parse_posted_days(raw_posted)
    desc_html = str(info.get("jobDescription") or "")
    description = html_to_text(desc_html)

    external_path = str(info.get("externalPath") or f"/job/{job_path}")
    canonical_url = f"https://{host}/en-US/{site}{external_path}"

    return Job(
        id=f"{slug}:{job_req_id}",
        company=company_name,
        title=title,
        location=locations[0] if locations else "",
        locations=locations,
        url=canonical_url,
        posted_on=raw_posted,
        posted_days=posted_days,
        source="workday",
        description=description,
        company_blurb=company_blurb,
        default_country=default_country,
    )


def _parse_greenhouse(
    url: str,
    session: requests.Session,
    lookup: CompanyLookup,
) -> Job | None:
    parsed = urlparse(url)
    if not parsed.netloc.endswith("greenhouse.io"):
        return None

    token: str | None = None
    job_id: str | None = None

    if "embed/job_app" in parsed.path:
        qs = parse_qs(parsed.query)
        token = qs.get("for", [None])[0]
        job_id = qs.get("token", [None])[0]
    else:
        m = re.match(r"^/([^/?#]+)/jobs/(\d+)", parsed.path)
        if m:
            token, job_id = m.group(1), m.group(2)

    if not token or not job_id:
        return None

    api_url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{job_id}?questions=false"
    try:
        resp = session.get(api_url, headers={"Accept": "application/json"}, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        raw_json: object = resp.json()
        payload = cast("dict[str, object]", raw_json) if isinstance(raw_json, dict) else {}
    except Exception as exc:
        raise JobParseError(f"Greenhouse API request failed for {url}: {exc}") from exc

    title = str(payload.get("title") or "").strip() or "Unknown Title"
    company_name, company_blurb, default_country = lookup.resolve(
        "greenhouse", token, parsed.netloc
    )
    slug = slugify(company_name)

    loc_obj = payload.get("location")
    primary_loc = ""
    if isinstance(loc_obj, dict):
        loc_dict = cast("dict[str, object]", loc_obj)
        primary_loc = str(loc_dict.get("name") or "").strip()

    offices: list[str] = []
    raw_offices = payload.get("offices")
    if isinstance(raw_offices, list):
        for off in cast("list[object]", raw_offices):
            if isinstance(off, dict):
                off_dict = cast("dict[str, object]", off)
                loc_val = off_dict.get("location")
                if loc_val:
                    offices.append(str(loc_val).strip())
    locations = ([primary_loc] if primary_loc else []) + [o for o in offices if o != primary_loc]

    first_published = str(payload.get("first_published") or "").strip()
    posted_days = posted_days_from_iso(first_published) if first_published else None
    content_html = str(payload.get("content") or "")
    description = html_to_text(content_html)
    canonical_url = str(payload.get("absolute_url") or url)

    return Job(
        id=f"{slug}:{job_id}",
        company=company_name,
        title=title,
        location=locations[0] if locations else "",
        locations=locations,
        url=canonical_url,
        posted_on=first_published,
        posted_days=posted_days,
        source="greenhouse",
        description=description,
        company_blurb=company_blurb,
        default_country=default_country,
    )


def _parse_ashby(
    url: str,
    session: requests.Session,
    lookup: CompanyLookup,
) -> Job | None:
    parsed = urlparse(url)
    if parsed.netloc != "jobs.ashbyhq.com":
        return None

    m = re.match(r"^/([^/?#]+)/([a-f0-9-]+)", parsed.path)
    if not m:
        return None
    slug_param, job_id = m.group(1), m.group(2)

    api_url = f"https://api.ashbyhq.com/posting-api/job-board/{slug_param}?includeCompensation=true"
    try:
        resp = session.get(api_url, headers={"Accept": "application/json"}, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        raw_json: object = resp.json()
        board_data = cast("dict[str, object]", raw_json) if isinstance(raw_json, dict) else {}
    except Exception as exc:
        raise JobParseError(f"Ashby API request failed for {url}: {exc}") from exc

    raw_postings = board_data.get("jobs")
    target: dict[str, object] | None = None
    if isinstance(raw_postings, list):
        for p in cast("list[object]", raw_postings):
            if isinstance(p, dict):
                p_dict = cast("dict[str, object]", p)
                if str(p_dict.get("id")) == job_id or str(p_dict.get("jobUrl") or "").rstrip(
                    "/"
                ) == url.rstrip("/"):
                    target = p_dict
                    break

    if not target:
        raise JobParseError(f"Job ID {job_id} not found on Ashby board {slug_param}")

    title = str(target.get("title") or "").strip() or "Unknown Title"
    company_name, company_blurb, default_country = lookup.resolve(
        "ashby", slug_param, parsed.netloc
    )
    comp_slug = slugify(company_name)

    loc = str(target.get("location") or "").strip()
    sec_locs: list[str] = []
    raw_sec = target.get("secondaryLocations")
    if isinstance(raw_sec, list):
        for s in cast("list[object]", raw_sec):
            if isinstance(s, dict):
                s_dict = cast("dict[str, object]", s)
                val = s_dict.get("location")
                if val:
                    sec_locs.append(str(val).strip())
    locations = ([loc] if loc else []) + sec_locs

    published_at = str(target.get("publishedAt") or "").strip()
    posted_days = posted_days_from_iso(published_at) if published_at else None

    desc = str(target.get("descriptionPlain") or "").strip()
    if not desc:
        desc = html_to_text(str(target.get("descriptionHtml") or ""))

    canonical_url = str(target.get("jobUrl") or url)

    return Job(
        id=f"{comp_slug}:{job_id}",
        company=company_name,
        title=title,
        location=locations[0] if locations else "",
        locations=locations,
        url=canonical_url,
        posted_on=published_at,
        posted_days=posted_days,
        source="ashby",
        description=desc,
        company_blurb=company_blurb,
        default_country=default_country,
    )


def _parse_lever(
    url: str,
    session: requests.Session,
    lookup: CompanyLookup,
) -> Job | None:
    parsed = urlparse(url)
    if parsed.netloc != "jobs.lever.co":
        return None

    m = re.match(r"^/([^/?#]+)/([a-f0-9-]+)", parsed.path)
    if not m:
        return None
    company_slug, job_id = m.group(1), m.group(2)

    api_url = f"https://api.lever.co/v0/postings/{company_slug}/{job_id}"
    try:
        resp = session.get(api_url, headers={"Accept": "application/json"}, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        raw_json: object = resp.json()
        payload = cast("dict[str, object]", raw_json) if isinstance(raw_json, dict) else {}
    except Exception as exc:
        raise JobParseError(f"Lever API request failed for {url}: {exc}") from exc

    title = str(payload.get("text") or "").strip() or "Unknown Title"
    company_name, company_blurb, default_country = lookup.resolve(
        "lever", company_slug, parsed.netloc
    )
    comp_slug = slugify(company_name)

    raw_cats = payload.get("categories")
    cats = cast("dict[str, object]", raw_cats) if isinstance(raw_cats, dict) else {}
    primary_loc = str(cats.get("location") or "").strip()
    raw_all_locs = cats.get("allLocations")
    all_locs: list[str] = []
    if isinstance(raw_all_locs, list):
        for item in cast("list[object]", raw_all_locs):
            val = str(item).strip()
            if val and val != primary_loc:
                all_locs.append(val)
    locations = ([primary_loc] if primary_loc else []) + all_locs

    created_at = payload.get("createdAt")
    posted_days = posted_days_from_epoch_ms(created_at) if isinstance(created_at, int) else None

    desc = str(payload.get("descriptionPlain") or "").strip()
    if not desc:
        desc = html_to_text(str(payload.get("description") or ""))

    canonical_url = str(payload.get("hostedUrl") or url)

    return Job(
        id=f"{comp_slug}:{job_id}",
        company=company_name,
        title=title,
        location=locations[0] if locations else "",
        locations=locations,
        url=canonical_url,
        posted_on=str(created_at) if created_at else "",
        posted_days=posted_days,
        source="lever",
        description=desc,
        company_blurb=company_blurb,
        default_country=default_country,
    )


def _parse_smartrecruiters(
    url: str,
    session: requests.Session,
    lookup: CompanyLookup,
) -> Job | None:
    parsed = urlparse(url)
    if parsed.netloc != "jobs.smartrecruiters.com":
        return None

    m = re.match(r"^/([^/?#]+)/([^/?#]+)", parsed.path)
    if not m:
        return None
    company_slug, raw_id = m.group(1), m.group(2)
    posting_id = raw_id.split("-")[0] if "-" in raw_id else raw_id

    api_url = f"https://api.smartrecruiters.com/v1/companies/{company_slug}/postings/{posting_id}"
    try:
        resp = session.get(api_url, headers={"Accept": "application/json"}, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        raw_json: object = resp.json()
        payload = cast("dict[str, object]", raw_json) if isinstance(raw_json, dict) else {}
    except Exception as exc:
        raise JobParseError(f"SmartRecruiters API request failed for {url}: {exc}") from exc

    title = str(payload.get("name") or "").strip() or "Unknown Title"
    company_name, company_blurb, default_country = lookup.resolve(
        "smartrecruiters", company_slug, parsed.netloc
    )
    comp_slug = slugify(company_name)

    raw_loc = payload.get("location")
    loc_obj = cast("dict[str, object]", raw_loc) if isinstance(raw_loc, dict) else {}
    full_loc = str(loc_obj.get("fullLocation") or "").strip()
    locations = [full_loc] if full_loc else []

    released_date = str(payload.get("releasedDate") or "").strip()
    posted_days = posted_days_from_iso(released_date) if released_date else None

    raw_ad = payload.get("jobAd")
    ad_dict = cast("dict[str, object]", raw_ad) if isinstance(raw_ad, dict) else {}
    raw_sections = ad_dict.get("sections")
    sections = cast("dict[str, object]", raw_sections) if isinstance(raw_sections, dict) else {}
    raw_desc = sections.get("jobDescription")
    desc_dict = cast("dict[str, object]", raw_desc) if isinstance(raw_desc, dict) else {}
    desc_html = str(desc_dict.get("text") or "")
    description = html_to_text(desc_html)
    canonical_url = str(payload.get("postingUrl") or url)

    return Job(
        id=f"{comp_slug}:{posting_id}",
        company=company_name,
        title=title,
        location=locations[0] if locations else "",
        locations=locations,
        url=canonical_url,
        posted_on=released_date,
        posted_days=posted_days,
        source="smartrecruiters",
        description=description,
        company_blurb=company_blurb,
        default_country=default_country,
    )


def _parse_rippling(
    url: str,
    session: requests.Session,
    lookup: CompanyLookup,
) -> Job | None:
    parsed = urlparse(url)
    if parsed.netloc != "ats.rippling.com":
        return None

    m = re.match(r"^/([^/?#]+)/jobs/([^/?#]+)", parsed.path)
    if not m:
        return None
    board_id, job_id = m.group(1), m.group(2)

    api_url = f"https://ats.rippling.com/api/v2/board/{board_id}/jobs/{job_id}"
    try:
        resp = session.get(
            api_url,
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        raw_json: object = resp.json()
        payload = cast("dict[str, object]", raw_json) if isinstance(raw_json, dict) else {}
    except Exception as exc:
        raise JobParseError(f"Rippling API request failed for {url}: {exc}") from exc

    title = str(payload.get("name") or "").strip() or "Unknown Title"
    company_name, company_blurb, default_country = lookup.resolve(
        "rippling", board_id, parsed.netloc
    )
    comp_slug = slugify(company_name)

    raw_loc = payload.get("location")
    loc_obj = cast("dict[str, object]", raw_loc) if isinstance(raw_loc, dict) else {}
    loc_parts: list[str] = []
    for k in ("city", "state", "country"):
        v = str(loc_obj.get(k) or "").strip()
        if v:
            loc_parts.append(v)
    loc_str = ", ".join(loc_parts)
    locations = [loc_str] if loc_str else []

    desc_raw = payload.get("description")
    if isinstance(desc_raw, dict):
        desc_dict = cast("dict[str, object]", desc_raw)
        desc_html = str(desc_dict.get("role") or "")
    else:
        desc_html = str(desc_raw or "")
    description = html_to_text(desc_html)

    return Job(
        id=f"{comp_slug}:{job_id}",
        company=company_name,
        title=title,
        location=locations[0] if locations else "",
        locations=locations,
        url=url,
        posted_on="",
        posted_days=None,
        source="rippling",
        description=description,
        company_blurb=company_blurb,
        default_country=default_country,
    )


def _parse_bamboohr(
    url: str,
    session: requests.Session,
    lookup: CompanyLookup,
) -> Job | None:
    parsed = urlparse(url)
    if not parsed.netloc.endswith(".bamboohr.com"):
        return None
    subdomain = parsed.netloc.split(".")[0]

    job_id: str | None = None
    m = re.match(r"^/careers/(\d+)", parsed.path)
    if m:
        job_id = m.group(1)
    elif "view.php" in parsed.path:
        qs = parse_qs(parsed.query)
        job_id = qs.get("id", [None])[0]

    if not job_id:
        return None

    api_url = f"https://{subdomain}.bamboohr.com/careers/{job_id}/detail"
    try:
        resp = session.get(api_url, headers={"Accept": "application/json"}, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        raw_json: object = resp.json()
        payload = cast("dict[str, object]", raw_json) if isinstance(raw_json, dict) else {}
    except Exception as exc:
        raise JobParseError(f"BambooHR detail request failed for {url}: {exc}") from exc

    raw_res = payload.get("result")
    res_dict = cast("dict[str, object]", raw_res) if isinstance(raw_res, dict) else {}
    raw_opening = res_dict.get("jobOpening")
    opening = cast("dict[str, object]", raw_opening) if isinstance(raw_opening, dict) else {}
    if not opening:
        raise JobParseError(f"BambooHR response contains no jobOpening data for {url}")

    title = str(opening.get("jobOpeningName") or "").strip() or "Unknown Title"
    company_name, company_blurb, default_country = lookup.resolve(
        "bamboohr", subdomain, parsed.netloc
    )
    comp_slug = slugify(company_name)

    raw_loc = opening.get("location")
    loc_obj = cast("dict[str, object]", raw_loc) if isinstance(raw_loc, dict) else {}
    loc_parts: list[str] = []
    for k in ("city", "state"):
        v = str(loc_obj.get(k) or "").strip()
        if v:
            loc_parts.append(v)
    loc_str = ", ".join(loc_parts)
    locations = [loc_str] if loc_str else []

    date_posted = str(opening.get("datePosted") or "").strip()
    posted_days = posted_days_from_iso(date_posted) if date_posted else None

    desc_html = str(opening.get("description") or "")
    description = html_to_text(desc_html)
    canonical_url = str(opening.get("jobOpeningShareUrl") or url)

    return Job(
        id=f"{comp_slug}:{job_id}",
        company=company_name,
        title=title,
        location=locations[0] if locations else "",
        locations=locations,
        url=canonical_url,
        posted_on=date_posted,
        posted_days=posted_days,
        source="bamboohr",
        description=description,
        company_blurb=company_blurb,
        default_country=default_country,
    )


def _parse_workable(
    url: str,
    session: requests.Session,
    lookup: CompanyLookup,
) -> Job | None:
    parsed = urlparse(url)
    if parsed.netloc != "apply.workable.com":
        return None

    m = re.match(r"^(?:/([^/?#]+))?/j/([^/?#]+)", parsed.path)
    if not m:
        return None
    company_slug, shortcode = m.group(1), m.group(2)

    if company_slug:
        api_url = f"https://apply.workable.com/api/v2/accounts/{company_slug}/jobs/{shortcode}"
        try:
            resp = session.get(
                api_url, headers={"Accept": "application/json"}, timeout=DEFAULT_TIMEOUT
            )
            if resp.status_code == 200:
                raw_json: object = resp.json()
                payload = cast("dict[str, object]", raw_json) if isinstance(raw_json, dict) else {}
                title = str(payload.get("title") or "").strip() or "Unknown Title"
                company_name, company_blurb, default_country = lookup.resolve(
                    "workable", company_slug, parsed.netloc
                )
                comp_slug = slugify(company_name)

                locations: list[str] = []
                raw_locations = payload.get("locations")
                if isinstance(raw_locations, list):
                    for loc in cast("list[object]", raw_locations):
                        if isinstance(loc, dict):
                            loc_dict = cast("dict[str, object]", loc)
                            parts = [
                                str(loc_dict.get(k) or "").strip()
                                for k in ("city", "region", "country")
                                if loc_dict.get(k)
                            ]
                            if parts:
                                locations.append(", ".join(parts))

                pub_date = str(payload.get("published_on") or "").strip()
                posted_days = posted_days_from_date_str(pub_date) if pub_date else None
                description = html_to_text(str(payload.get("description") or ""))

                return Job(
                    id=f"{comp_slug}:{shortcode}",
                    company=company_name,
                    title=title,
                    location=locations[0] if locations else "",
                    locations=locations,
                    url=url,
                    posted_on=pub_date,
                    posted_days=posted_days,
                    source="workable",
                    description=description,
                    company_blurb=company_blurb,
                    default_country=default_country,
                )
        except Exception as exc:
            log.debug("Workable v2 API failed for %s (%s); will fallback to HTML", url, exc)

    return None


def _parse_gc_jobs(
    url: str,
    session: requests.Session,
    lookup: CompanyLookup,
) -> Job | None:
    """Parse a Government of Canada (GC Jobs) poster link, resolving transition pages."""
    parsed = urlparse(url)
    if "emploisfp-psjobs.cfp-psc.gc.ca" not in parsed.netloc:
        return None

    qs = parse_qs(parsed.query)
    poster_id = qs.get("poster", [""])[0]
    if not poster_id:
        m = re.search(r"poster=(\d+)", url)
        if m:
            poster_id = m.group(1)

    lang = qs.get("toggleLanguage", ["en"])[0]
    canonical_url = (
        f"https://emploisfp-psjobs.cfp-psc.gc.ca/psrs-srfp/applicant/page1800?poster={poster_id}&toggleLanguage={lang}"
        if poster_id
        else url
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": (
            "fr-CA,fr;q=0.9,en;q=0.8" if lang == "fr" else "en-CA,en;q=0.9,fr;q=0.8"
        ),
    }
    try:
        resp = session.get(canonical_url, headers=headers, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        raise JobParseError(f"Failed to fetch GC Jobs poster {url}: {exc}") from exc

    html = resp.text
    transition = parse_transition_page(html)
    if transition:
        target_url, link_title = transition
        log.info("Detected GC Jobs transition page pointing to %s", target_url)
        try:
            job = parse_job_url(target_url, session=session, config_path=lookup.config_path)
            if not job.company_group:
                job.company_group = "Government of Canada"
            if not job.title or job.title in ("Job Posting", "Career Center"):
                job.title = link_title or job.title
            if (
                "Communications Security Establishment" in job.description
                or "Centre de la sécurité des télécommunications" in job.description
            ):
                job.company = "Communications Security Establishment Canada"
                parts = job.id.split(":", 1)
                job.id = (
                    f"communications-security-establishment:{parts[1]}"
                    if len(parts) > 1
                    else job.id
                )
            elif job.company in ("Unknown", "Careers", "Apply", "Phe", "Cse Cst"):
                job.company = "Government of Canada"
            return job
        except Exception as exc:
            log.warning(
                "Could not fully parse transition destination %s: %s; synthesizing job",
                target_url,
                exc,
            )
            slug = slugify("Government of Canada")
            ident = poster_id or hashlib.sha256(target_url.encode()).hexdigest()[:12]
            return Job(
                id=f"{slug}:{ident}",
                company="Government of Canada",
                title=link_title or "Job Posting",
                location="",
                locations=[],
                url=target_url,
                posted_on="",
                source="gc_jobs",
                company_group="Government of Canada",
                description=f"External competition link: {target_url}",
            )

    # Standard non-transition poster
    main_m = re.search(r"<main\b[^>]*>(.*?)</main>", html, re.DOTALL | re.IGNORECASE)
    main_html = main_m.group(1) if main_m else html

    title_m = re.search(r"<h1[^>]*>(.*?)</h1>", main_html, re.DOTALL)
    title = html_to_text(title_m.group(1)).strip() if title_m else "Job Posting"

    dept_m = re.search(r"<h2 class=[\"']pst-h2[\"'][^>]*>(.*?)</h2>", main_html, re.DOTALL)
    dept = html_to_text(dept_m.group(1)).strip() if dept_m else ""
    if dept:
        dept = re.sub(r"\s+", " ", dept).strip()

    close_m = re.search(r"Closing date:\s*([^<]+)", main_html, re.IGNORECASE)
    closing_date = close_m.group(1).strip() if close_m else ""

    loc_m = re.search(r"<b>Location</b>\s*<br>(.*?)</div>", main_html, re.DOTALL | re.IGNORECASE)
    location = html_to_text(loc_m.group(1)).strip() if loc_m else ""

    content = re.sub(
        r"<(script|style|nav|footer|header)\b[^>]*>.*?</\1>", "", main_html, flags=re.DOTALL
    )
    description = html_to_text(content)

    company_name = dept or "Government of Canada"
    company_slug = slugify("Government of Canada")
    ident = poster_id or hashlib.sha256(canonical_url.encode()).hexdigest()[:12]

    _, blurb, _ = lookup.resolve("gc_jobs", "government-of-canada")

    return Job(
        id=f"{company_slug}:{ident}",
        company=company_name,
        title=title,
        location=location,
        locations=[location] if location else [],
        url=canonical_url,
        posted_on=f"Closing: {closing_date}" if closing_date else "",
        source="gc_jobs",
        description=description,
        company_group="Government of Canada",
        company_blurb=blurb,
    )


def _extract_json_ld_job_posting(html: str) -> dict[str, object] | None:
    """Extract Schema.org JobPosting dict from HTML script tags."""
    pattern = re.compile(
        r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        re.DOTALL | re.IGNORECASE,
    )
    for m in pattern.finditer(html):
        try:
            raw_parsed: object = json.loads(m.group(1).strip())
        except Exception:
            continue

        raw_items: list[object] = (
            cast("list[object]", raw_parsed) if isinstance(raw_parsed, list) else [raw_parsed]
        )
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            item_dict = cast("dict[str, object]", item)
            item_type = item_dict.get("@type")
            if item_type == "JobPosting" or (
                isinstance(item_type, list) and "JobPosting" in item_type
            ):
                return item_dict
            raw_graph = item_dict.get("@graph")
            if isinstance(raw_graph, list):
                for sub in cast("list[object]", raw_graph):
                    if isinstance(sub, dict):
                        sub_dict = cast("dict[str, object]", sub)
                        sub_type = sub_dict.get("@type")
                        if sub_type == "JobPosting" or (
                            isinstance(sub_type, list) and "JobPosting" in sub_type
                        ):
                            return sub_dict
    return None


def _parse_generic_html(
    url: str,
    resp: requests.Response,
    lookup: CompanyLookup,
    session: requests.Session | None = None,
) -> Job:
    """Parse generic web page via Schema.org JSON-LD or HTML metadata."""
    html = resp.text
    final_url = resp.url or url
    parsed_url = urlparse(final_url)
    host = parsed_url.netloc

    # Check for transition / redirect pages
    trans = parse_transition_page(html)
    if trans:
        target_url, _ = trans
        if target_url and target_url != final_url:
            log.info("Transition page detected at %s -> redirecting to %s", final_url, target_url)
            return parse_job_url(target_url, session=session, config_path=lookup.config_path)

    ld = _extract_json_ld_job_posting(html)
    if ld:
        raw_title = ld.get("title") or ld.get("name") or ""
        title = str(raw_title).strip()
        hiring_org = ld.get("hiringOrganization")
        company_name = ""
        if isinstance(hiring_org, dict):
            org_dict = cast("dict[str, object]", hiring_org)
            company_name = str(org_dict.get("name") or "").strip()
        elif isinstance(hiring_org, str):
            company_name = hiring_org.strip()

        if not company_name:
            company_name, _, _ = lookup.resolve("generic", host=host)

        slug = slugify(company_name)

        locations: list[str] = []
        loc_val = ld.get("jobLocation")
        loc_items: list[object] = (
            cast("list[object]", loc_val)
            if isinstance(loc_val, list)
            else ([loc_val] if loc_val else [])
        )
        for li in loc_items:
            if isinstance(li, dict):
                li_dict = cast("dict[str, object]", li)
                addr = li_dict.get("address")
                if isinstance(addr, dict):
                    addr_dict = cast("dict[str, object]", addr)
                    parts = [
                        str(addr_dict.get(k) or "").strip()
                        for k in ("addressLocality", "addressRegion", "addressCountry")
                        if addr_dict.get(k)
                    ]
                    if parts:
                        locations.append(", ".join(parts))
                elif isinstance(addr, str) and addr.strip():
                    locations.append(addr.strip())
            elif isinstance(li, str) and li.strip():
                locations.append(li.strip())

        if ld.get("jobLocationType") == "TELECOMMUTE" or "remote" in title.lower():
            if not any("remote" in x.lower() for x in locations):
                locations.append("Remote")

        date_posted = str(ld.get("datePosted") or "").strip()
        posted_days = posted_days_from_iso(date_posted) if date_posted else None

        desc_raw = str(ld.get("description") or "")
        description = html_to_text(desc_raw)

        ident_obj = ld.get("identifier")
        ident_str = ""
        if isinstance(ident_obj, dict):
            id_dict = cast("dict[str, object]", ident_obj)
            ident_str = str(id_dict.get("value") or "").strip()
        elif isinstance(ident_obj, (str, int)):
            ident_str = str(ident_obj).strip()

        if not ident_str:
            ident_str = hashlib.sha256(final_url.encode()).hexdigest()[:12]

        return Job(
            id=f"{slug}:{ident_str}",
            company=company_name,
            title=title or "Job Posting",
            location=locations[0] if locations else "",
            locations=locations,
            url=final_url,
            posted_on=date_posted,
            posted_days=posted_days,
            source="schema.org",
            description=description,
        )

    # Fallback to OpenGraph / HTML metadata
    og_title_m = re.search(
        r"<meta[^>]*property=[\"']og:title[\"'][^>]*content=[\"']([^\"']+)[\"']", html, re.I
    )
    title_tag_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.DOTALL)
    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.DOTALL)

    raw_title = ""
    if og_title_m:
        raw_title = og_title_m.group(1).strip()
    elif title_tag_m:
        raw_title = html_to_text(title_tag_m.group(1)).strip()
    elif h1_m:
        raw_title = html_to_text(h1_m.group(1)).strip()

    og_site_m = re.search(
        r"<meta[^>]*property=[\"']og:site_name[\"'][^>]*content=[\"']([^\"']+)[\"']", html, re.I
    )
    company_name = og_site_m.group(1).strip() if og_site_m else ""
    if not company_name:
        company_name, _, _ = lookup.resolve("generic", host=host)

    og_desc_m = re.search(
        r"<meta[^>]*property=[\"']og:description[\"'][^>]*content=[\"']([^\"']+)[\"']", html, re.I
    )
    meta_desc_m = re.search(
        r"<meta[^>]*name=[\"']description[\"'][^>]*content=[\"']([^\"']+)[\"']", html, re.I
    )
    description = ""
    if og_desc_m:
        description = html_to_text(og_desc_m.group(1))
    elif meta_desc_m:
        description = html_to_text(meta_desc_m.group(1))

    if not raw_title and not description:
        raise JobParseError(f"Could not extract meaningful job data or metadata from {final_url}")

    slug = slugify(company_name)
    ident_str = hashlib.sha256(final_url.encode()).hexdigest()[:12]

    return Job(
        id=f"{slug}:{ident_str}",
        company=company_name,
        title=raw_title or "Job Posting",
        location="",
        locations=[],
        url=final_url,
        posted_on="",
        posted_days=None,
        source="html",
        description=description,
    )


def parse_job_url(
    url: str,
    *,
    session: requests.Session | None = None,
    config_path: Path | str | None = None,
) -> Job:
    """Parse a single job posting by direct link into a normalized Job object.

    Detects the board type from URL patterns and queries direct ATS endpoints
    where possible (Workday, Greenhouse, Ashby, Lever, SmartRecruiters, Rippling,
    BambooHR, Workable). Automatically resolves canonical company names and blurbs
    from config.json when available. Falls back to Schema.org (JSON-LD) JobPosting
    or OpenGraph HTML parsing for arbitrary URLs.
    """
    clean_url = url.strip()
    if not clean_url:
        raise ValueError("Job URL cannot be empty")

    s = session or make_session()
    lookup = CompanyLookup(config_path)

    # 1. Try ATS parsers on input URL
    for parser_fn in (
        _parse_workday,
        _parse_greenhouse,
        _parse_ashby,
        _parse_lever,
        _parse_smartrecruiters,
        _parse_rippling,
        _parse_bamboohr,
        _parse_workable,
        _parse_gc_jobs,
    ):
        result = parser_fn(clean_url, s, lookup)
        if result is not None:
            return result

    # 2. If not matched, fetch URL (following redirects) to handle vanity URLs or generic pages
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    }
    try:
        resp = s.get(clean_url, headers=headers, timeout=DEFAULT_TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
    except Exception as exc:
        raise JobParseError(f"Failed to fetch page at {clean_url}: {exc}") from exc

    # Check if redirected URL matches an ATS pattern
    if resp.url and resp.url != clean_url:
        for parser_fn in (
            _parse_workday,
            _parse_greenhouse,
            _parse_ashby,
            _parse_lever,
            _parse_smartrecruiters,
            _parse_rippling,
            _parse_bamboohr,
            _parse_workable,
            _parse_gc_jobs,
        ):
            redirected_result = parser_fn(resp.url, s, lookup)
            if redirected_result is not None:
                return redirected_result

    # 3. Parse via Schema.org JSON-LD or HTML meta tags
    return _parse_generic_html(clean_url, resp, lookup, session=s)


def job_to_dict(job: Job) -> dict[str, object]:
    """Serialize Job dataclass to a JSON-compatible dict."""
    return asdict(job)


def main() -> None:
    """CLI entry point for link parser."""
    parser = argparse.ArgumentParser(
        description="Parse an individual job posting link into a normalized Job record."
    )
    parser.add_argument("url", nargs="?", help="job posting URL to parse")
    parser.add_argument("--url", dest="opt_url", help="job posting URL to parse (flag alternative)")
    parser.add_argument(
        "--database", help="optional SQLAlchemy database URL to write the parsed job into"
    )
    parser.add_argument("--verbose", action="store_true", help="enable DEBUG logging")

    args = parser.parse_args()
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    target_url = args.opt_url or args.url
    if not target_url:
        parser.error("A job posting URL is required. Provide it as an argument or via --url.")

    try:
        job = parse_job_url(target_url)
    except Exception as exc:
        log.error("Failed to parse job URL: %s", exc)
        raise SystemExit(1) from exc

    job_data = job_to_dict(job)
    print(json.dumps(job_data, indent=2, ensure_ascii=False))

    if args.database:
        from scraper.db import write_jobs

        log.info("Writing parsed job %s to database %s...", job.id, args.database)
        write_jobs(args.database, [job], {job.id}, scope_companies={job.company})
        log.info("Successfully persisted job %s", job.id)


if __name__ == "__main__":
    main()
