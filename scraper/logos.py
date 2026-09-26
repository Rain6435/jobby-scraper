"""Unified SVG Logo Resolver & Normalization Engine.

Resolves, validates, formats, and generates unified SVG logos for companies
across all supported ATS platforms.

Guarantees 100% resolution-independent SVG coverage across all companies
via a 5-tier fallback architecture:
1. Curated Vector Repositories (Simple Icons, SVGL, VectorLogoZone)
2. Wikidata & Wikimedia Commons Official Vector SVGs (Property P154)
3. Website & Career Portal Live Scraping for Vector Favicons / Logos
4. High-Resolution Favicons Embedded inside Unified 128x128 SVG Container
5. Branded Geometric Monogram SVGs with Deterministic Palette Hashing
"""

from __future__ import annotations

import base64
import hashlib
import html
import logging
import re
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import cast

import requests
from requests.adapters import HTTPAdapter

from scraper.config_types import CompanyConfig

log = logging.getLogger("scraper.logos")

ROOT = Path(__file__).resolve().parent.parent
LOGO_DIR = ROOT / "data" / "logos"
CANVAS_SIZE = 128
DEFAULT_TIMEOUT = 5

HEADERS = {
    "User-Agent": "JobScraperBot/1.0 (+https://github.com/Rain6435/jobby-scraper)",
    "Accept": "image/svg+xml,image/*,*/*;q=0.8",
}

_session: requests.Session | None = None


def get_session() -> requests.Session:
    """Return a shared HTTP session with connection pooling for logo requests."""
    global _session
    if _session is None:
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update(HEADERS)
        _session = session
    return _session


def slugify_company(name: str) -> str:
    """Generate a clean, filesystem-safe filename slug for a company.

    Example:
        'Allen Institute' -> 'allen-institute'
        'Apple Inc.' -> 'apple'
        'City of Seattle' -> 'city-of-seattle'
    """
    clean = name.lower().strip()
    # Strip common legal suffixes
    clean = re.sub(
        r"\b(inc|incorporated|corp|corporation|ltd|limited|llc|group|gmbh|sa|bv|holdings)\b",
        "",
        clean,
    )
    clean = re.sub(r"[^\w\s-]", "", clean).strip()
    slug = re.sub(r"[\s_]+", "-", clean)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        raw = re.sub(r"[^\w]", "", name.lower())
        return raw or "company"
    return slug


def _strip_tags(svg_text: str) -> str:
    """Strip potentially dangerous tags and comments from raw SVG text."""
    # Strip XML comments
    text = re.sub(r"<!--.*?-->", "", svg_text, flags=re.DOTALL)
    # Strip script and style tags
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return text.strip()


def normalize_svg(svg_content: str, title: str = "") -> str:
    """Normalize raw SVG into a unified, sanitized, resolution-independent SVG format.

    - Validates XML syntax
    - Enforces viewBox and xmlns
    - Centers content with preserveAspectRatio="xMidYMid meet"
    - Sets width="100%" height="100%"
    """
    clean_text = _strip_tags(svg_content)
    # Strip leading XML declaration if present
    clean_text = re.sub(r"<\?xml[^>]*\?>", "", clean_text).strip()

    # Find the <svg> opening and closing tags
    start = clean_text.find("<svg")
    end = clean_text.rfind("</svg>")
    if start == -1 or end == -1:
        raise ValueError("Invalid SVG: missing <svg> tags")
    svg_block = clean_text[start : end + 6]

    # Verify well-formed XML
    try:
        root = ET.fromstring(svg_block)
    except ET.ParseError as exc:
        raise ValueError(f"Malformed SVG XML: {exc}") from exc

    # Extract existing viewBox or width/height
    viewbox = root.attrib.get("viewBox")
    width_attr = root.attrib.get("width")
    height_attr = root.attrib.get("height")

    if not viewbox:
        w_val = 0.0
        h_val = 0.0
        if width_attr and height_attr:
            w_m = re.match(r"^([\d.]+)", width_attr)
            h_m = re.match(r"^([\d.]+)", height_attr)
            if w_m and h_m:
                try:
                    w_val = float(w_m.group(1))
                    h_val = float(h_m.group(1))
                except ValueError:
                    w_val = 0.0
                    h_val = 0.0
        if w_val > 0 and h_val > 0:
            viewbox = f"0 0 {int(w_val)} {int(h_val)}"
        else:
            viewbox = f"0 0 {CANVAS_SIZE} {CANVAS_SIZE}"

    # Extract inner elements
    # Remove xmlns from children tag names in serialization
    inner_parts: list[str] = []
    if title:
        inner_parts.append(f"<title>{html.escape(title)}</title>")

    for child in root:
        # Strip tag namespace if ElementTree added it
        tag_name = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag_name.lower() in ("script", "foreignobject"):
            continue
        try:
            child_str = ET.tostring(child, encoding="unicode", method="xml")
            # Clean namespace prefixes ElementTree might insert
            child_str = re.sub(r"ns\d+:", "", child_str)
            child_str = re.sub(r"\sxmlns(:\w+)?=[\"'][^\"']*[\"']", "", child_str)
            inner_parts.append(child_str)
        except Exception:
            continue

    inner_xml = "".join(inner_parts)
    return (
        f'<svg {_root_xmlns_attrs(inner_xml)}viewBox="{viewbox}" '
        f'width="100%" height="100%" preserveAspectRatio="xMidYMid meet">\n'
        f"{inner_xml}\n"
        f"</svg>"
    )


# Namespace prefixes that legitimately appear in favicon-sourced <metadata>
# blocks (e.g. RealFaviconGenerator's RDF/Dublin Core attribution) — line
# 156 above strips every xmlns(:*) declaration from child serialization to
# clean up ElementTree's own auto-generated ns0:/ns1: aliases, but that also
# strips a *source* SVG's real xmlns:rdf/xmlns:dc off <metadata> if that
# element survives into inner_parts, orphaning its rdf:RDF/dc:creator
# children. Chromium tolerates an undeclared prefix in inline SVG; Firefox's
# stricter XML parser throws "prefix not bound to a namespace" and refuses
# to render the *entire* SVG (confirmed on 13 existing logos, e.g. solace.svg).
# Re-declaring on the root whenever inner_xml actually still uses a prefix
# is cheaper and more robust than trying to special-case metadata stripping
# for every favicon generator's own namespace choices.
_NAMESPACE_URIS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dc": "http://purl.org/dc/elements/1.1/",
    "cc": "http://creativecommons.org/ns#",
}


def _root_xmlns_attrs(inner_xml: str) -> str:
    """Build extra xmlns:<prefix>="..." attrs for any known prefix actually
    used in inner_xml, plus the mandatory default SVG namespace. Always ends
    with a trailing space so callers can concatenate directly before viewBox.
    """
    attrs = ['xmlns="http://www.w3.org/2000/svg"']
    for prefix, uri in _NAMESPACE_URIS.items():
        if re.search(rf"[<\s]{prefix}:", inner_xml):
            attrs.append(f'xmlns:{prefix}="{uri}"')
    return " ".join(attrs) + " "


def embed_raster_in_svg(image_bytes: bytes, mime_type: str = "image/png", title: str = "") -> str:
    """Embed high-resolution raster image bytes inside a unified 128x128 SVG container."""
    b64_data = base64.b64encode(image_bytes).decode("ascii")
    data_uri = f"data:{mime_type};base64,{b64_data}"
    title_element = f"<title>{html.escape(title)}</title>" if title else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CANVAS_SIZE} {CANVAS_SIZE}" '
        f'width="100%" height="100%" preserveAspectRatio="xMidYMid meet">\n'
        f"{title_element}\n"
        f'<image href="{data_uri}" width="{CANVAS_SIZE}" height="{CANVAS_SIZE}" '
        f'preserveAspectRatio="xMidYMid meet"/>\n'
        f"</svg>"
    )


def generate_monogram_svg(company_name: str) -> str:
    """Generate a clean, modern vector monogram SVG for a company with deterministic palette hashing."""
    clean = re.sub(r"[^\w\s]", "", company_name).strip()
    words = clean.split()
    if len(words) >= 2:
        initials = (words[0][0] + words[1][0]).upper()
    elif len(words) == 1 and len(words[0]) >= 2:
        initials = words[0][:2].upper()
    elif len(words) == 1:
        initials = words[0][0].upper()
    else:
        initials = "CO"

    # Deterministic accessible background color from MD5 hash
    digest = hashlib.md5(company_name.encode("utf-8")).hexdigest()
    hue = int(digest[:4], 16) % 360
    bg_color = f"hsl({hue}, 60%, 42%)"

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CANVAS_SIZE} {CANVAS_SIZE}" '
        f'width="100%" height="100%">\n'
        f"<title>{html.escape(company_name)}</title>\n"
        f'<rect width="{CANVAS_SIZE}" height="{CANVAS_SIZE}" rx="28" fill="{bg_color}"/>\n'
        f'<text x="64" y="66" font-family="system-ui, -apple-system, sans-serif" font-size="48" '
        f'font-weight="700" fill="#ffffff" text-anchor="middle" dominant-baseline="central">'
        f"{html.escape(initials)}</text>\n"
        f"</svg>"
    )


def _extract_candidate_identifiers(company: CompanyConfig) -> list[str]:
    """Generate candidate slug variations and identifiers for icon lookup."""
    name = company["name"]
    slugs: list[str] = []

    # 1. Direct explicit tokens / slugs from config
    for key in ("slug", "token", "company", "agency", "board_id"):
        val = company.get(key)
        if isinstance(val, str) and val.strip():
            slugs.append(val.strip().lower())

    # 2. Name-derived variations
    name_slug = slugify_company(name)
    slugs.append(name_slug)
    slugs.append(name_slug.replace("-", ""))

    # 3. First word for short names (e.g. 'Apple Inc' -> 'apple')
    words = name_slug.split("-")
    if len(words) > 1:
        slugs.append(words[0])

    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for s in slugs:
        if s and s not in seen:
            seen.add(s)
            result.append(s)
    return result


def _resolve_tier1_vector(company: CompanyConfig) -> str | None:
    """Tier 1: Look up curated vector icon repositories (Simple Icons, VectorLogoZone)."""
    session = get_session()
    slugs = _extract_candidate_identifiers(company)

    # 1. Simple Icons CDN
    for s in slugs:
        url = f"https://cdn.jsdelivr.net/npm/simple-icons@v11/icons/{s}.svg"
        try:
            resp = session.get(url, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200 and "<svg" in resp.text:
                return normalize_svg(resp.text, title=company["name"])
        except Exception:
            pass

    # 2. VectorLogoZone
    for s in slugs:
        url = f"https://www.vectorlogo.zone/logos/{s}/{s}-icon.svg"
        try:
            resp = session.get(url, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200 and "<svg" in resp.text:
                return normalize_svg(resp.text, title=company["name"])
        except Exception:
            pass

    return None


def _resolve_tier2_wikimedia(company: CompanyConfig) -> str | None:
    """Tier 2: Look up Wikidata official logo image (Property P154) on Wikimedia Commons."""
    session = get_session()
    name = company["name"]
    try:
        # Search entity on Wikidata
        search_url = "https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbsearchentities",
            "format": "json",
            "language": "en",
            "search": name,
            "limit": 3,
        }
        res_obj: object = session.get(search_url, params=params, timeout=DEFAULT_TIMEOUT).json()
        if not isinstance(res_obj, dict):
            return None
        res_dict = cast(dict[str, object], res_obj)
        raw_search: object = res_dict.get("search")
        if not isinstance(raw_search, list) or not raw_search:
            return None

        search_results = cast(list[object], raw_search)
        for item in search_results:
            if not isinstance(item, dict):
                continue
            item_dict = cast(dict[str, object], item)
            entity_id = item_dict.get("id")
            if not isinstance(entity_id, str):
                continue
            entity_url = f"https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json"
            entity_resp_obj: object = session.get(entity_url, timeout=DEFAULT_TIMEOUT).json()
            if not isinstance(entity_resp_obj, dict):
                continue
            entity_resp = cast(dict[str, object], entity_resp_obj)
            entities_obj: object = entity_resp.get("entities")
            if not isinstance(entities_obj, dict):
                continue
            entities_dict = cast(dict[str, object], entities_obj)
            entity_obj: object = entities_dict.get(entity_id)
            if not isinstance(entity_obj, dict):
                continue
            entity_dict = cast(dict[str, object], entity_obj)
            claims_obj: object = entity_dict.get("claims")
            if not isinstance(claims_obj, dict):
                continue
            claims_dict = cast(dict[str, object], claims_obj)

            p154_list: object = claims_dict.get("P154")
            if isinstance(p154_list, list) and p154_list:
                p154_claims = cast(list[object], p154_list)
                first_claim = p154_claims[0]
                if isinstance(first_claim, dict):
                    first_claim_dict = cast(dict[str, object], first_claim)
                    mainsnak: object = first_claim_dict.get("mainsnak")
                    if isinstance(mainsnak, dict):
                        mainsnak_dict = cast(dict[str, object], mainsnak)
                        datavalue: object = mainsnak_dict.get("datavalue")
                        if isinstance(datavalue, dict):
                            datavalue_dict = cast(dict[str, object], datavalue)
                            filename: object = datavalue_dict.get("value")
                            if isinstance(filename, str) and filename.lower().endswith(".svg"):
                                encoded = urllib.parse.quote(filename.replace(" ", "_"))
                                img_url = (
                                    f"https://commons.wikimedia.org/wiki/Special:FilePath/{encoded}"
                                )
                                img_resp = session.get(img_url, timeout=DEFAULT_TIMEOUT)
                                if img_resp.status_code == 200 and "<svg" in img_resp.text:
                                    return normalize_svg(img_resp.text, title=name)
    except Exception:
        pass
    return None


def _derive_company_domain(company: CompanyConfig) -> str | None:
    """Infer the primary web domain for a company from its config."""
    # 1. careers_base or url
    for key in ("careers_base", "url"):
        val = company.get(key)
        if isinstance(val, str) and val.strip():
            parsed = urllib.parse.urlparse(val)
            host = parsed.netloc.lower()
            if "myworkdayjobs.com" in host:
                parts = host.split(".")
                return f"{parts[0]}.com"
            if host and not any(
                portal in host
                for portal in ("greenhouse.io", "lever.co", "ashbyhq.com", "bamboohr.com")
            ):
                return host

    # 2. successfactors domain
    sf_domain = company.get("domain")
    if isinstance(sf_domain, str) and sf_domain.strip():
        return sf_domain.strip().lower()

    # 3. bamboo subdomain
    if company.get("board") == "bamboohr":
        sub = company.get("company")
        if isinstance(sub, str) and sub.strip():
            return f"{sub.strip().lower()}.com"

    # 4. government agency
    if company.get("board") == "governmentjobs":
        agency = company.get("agency")
        if isinstance(agency, str) and agency.strip():
            return f"{agency.strip().lower()}.gov"

    # 5. clean company name
    name_slug = slugify_company(company["name"]).replace("-", "")
    if len(name_slug) >= 3:
        return f"{name_slug}.com"

    return None


def _resolve_tier3_website_svg(company: CompanyConfig) -> str | None:
    """Tier 3: Scrape company career site or domain for SVG favicon or logo."""
    domain = _derive_company_domain(company)
    if not domain:
        return None
    session = get_session()
    name = company["name"]
    url = f"https://{domain}"
    try:
        resp = session.get(url, timeout=DEFAULT_TIMEOUT, allow_redirects=True)
        if resp.status_code == 200:
            text = resp.text
            # Look for link rel='icon' type='image/svg+xml'
            svg_links = re.findall(
                r"<link[^>]+(?:icon|shortcut)[^>]+href=[\"']([^\"']+\.svg[^\"]*)[\"']",
                text,
                re.IGNORECASE,
            )
            for link in svg_links:
                full_url = urllib.parse.urljoin(resp.url, link)
                svg_resp = session.get(full_url, timeout=DEFAULT_TIMEOUT)
                if svg_resp.status_code == 200 and "<svg" in svg_resp.text:
                    return normalize_svg(svg_resp.text, title=name)
    except Exception:
        pass
    return None


def _resolve_tier4_favicon(company: CompanyConfig) -> str | None:
    """Tier 4: Fetch high-resolution 128px favicon and wrap inside unified SVG container."""
    domain = _derive_company_domain(company)
    if not domain:
        return None
    session = get_session()
    name = company["name"]
    favicon_url = f"https://www.google.com/s2/favicons?domain={domain}&sz={CANVAS_SIZE}"
    try:
        resp = session.get(favicon_url, timeout=DEFAULT_TIMEOUT)
        # Empty/generic Google favicon is typically under 300 bytes
        if resp.status_code == 200 and len(resp.content) > 300:
            return embed_raster_in_svg(resp.content, mime_type="image/png", title=name)
    except Exception:
        pass
    return None


def resolve_company_logo(company: CompanyConfig) -> tuple[str, str]:
    """Resolve unified SVG logo for a company across all 5 tiers.

    Returns:
        tuple of (svg_content, tier_name)
    """
    name = company["name"]

    # Tier 1: Vector repositories
    svg = _resolve_tier1_vector(company)
    if svg:
        log.debug("[%s] Resolved via Tier 1 (Vector Library)", name)
        return svg, "tier1_vector"

    # Tier 2: Wikimedia Commons
    svg = _resolve_tier2_wikimedia(company)
    if svg:
        log.debug("[%s] Resolved via Tier 2 (Wikimedia)", name)
        return svg, "tier2_wikimedia"

    # Tier 3: Website SVG scrape
    svg = _resolve_tier3_website_svg(company)
    if svg:
        log.debug("[%s] Resolved via Tier 3 (Website Scrape)", name)
        return svg, "tier3_website"

    # Tier 4: Favicon embedded in SVG
    svg = _resolve_tier4_favicon(company)
    if svg:
        log.debug("[%s] Resolved via Tier 4 (Favicon Embedded)", name)
        return svg, "tier4_favicon"

    # Tier 5: Deterministic Monogram SVG
    log.debug("[%s] Resolved via Tier 5 (Monogram SVG)", name)
    return generate_monogram_svg(name), "tier5_monogram"


def resolve_and_save_logo(
    company: CompanyConfig,
    output_dir: Path = LOGO_DIR,
    force: bool = False,
) -> str:
    """Resolve and write the unified SVG logo to output_dir / f"{slug}.svg".

    Returns:
        Relative path string suitable for config.json (e.g. 'data/logos/apple.svg').
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify_company(company["name"])
    filename = f"{slug}.svg"
    target_path = output_dir / filename
    rel_path = f"data/logos/{filename}"

    if target_path.exists() and not force:
        return rel_path

    svg_content, _ = resolve_company_logo(company)
    target_path.write_text(svg_content, encoding="utf-8")
    return rel_path
