"""Unit tests for unified SVG logo engine (scraper/logos.py)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scraper.config_types import CompanyConfig
from scraper.logos import (
    embed_raster_in_svg,
    generate_monogram_svg,
    normalize_svg,
    resolve_and_save_logo,
    resolve_company_logo,
    slugify_company,
)


def test_slugify_company() -> None:
    assert slugify_company("Apple Inc.") == "apple"
    assert slugify_company("Microsoft Corporation") == "microsoft"
    assert slugify_company("Allen Institute") == "allen-institute"
    assert slugify_company("City of Seattle") == "city-of-seattle"
    assert slugify_company("GLY Construction, LLC") == "gly-construction"
    assert slugify_company("AstraZeneca Canada") == "astrazeneca-canada"
    assert slugify_company("   ") == "company"


def test_normalize_svg_valid() -> None:
    raw = '<svg viewBox="0 0 24 24"><path d="M0 0h24v24H0z"/></svg>'
    normalized = normalize_svg(raw, title="Test Company")
    assert 'viewBox="0 0 24 24"' in normalized
    assert 'width="100%"' in normalized
    assert 'height="100%"' in normalized
    assert 'preserveAspectRatio="xMidYMid meet"' in normalized
    assert "<title>Test Company</title>" in normalized
    # Valid XML
    root = ET.fromstring(normalized)
    assert root.tag.endswith("svg")


def test_normalize_svg_synthesizes_viewbox() -> None:
    raw = '<svg width="200" height="100"><circle cx="50" cy="50" r="40"/></svg>'
    normalized = normalize_svg(raw)
    assert 'viewBox="0 0 200 100"' in normalized
    root = ET.fromstring(normalized)
    assert root.tag.endswith("svg")


def test_normalize_svg_sanitizes_scripts() -> None:
    raw = (
        '<svg viewBox="0 0 50 50"><script>alert("xss")</script><rect width="50" height="50"/></svg>'
    )
    normalized = normalize_svg(raw)
    assert "alert" not in normalized
    assert "<script" not in normalized
    root = ET.fromstring(normalized)
    assert root.tag.endswith("svg")


def test_normalize_svg_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid SVG"):
        normalize_svg("<div>not svg</div>")


def test_normalize_svg_declares_namespaces_for_metadata_prefixes() -> None:
    """RealFaviconGenerator-style source SVGs declare xmlns:rdf/xmlns:dc on
    their own root for their <metadata> block's rdf:RDF/dc:creator children
    (confirmed on the real solace.svg before normalization). The per-child
    xmlns-stripping regex above (removing ElementTree's own auto-generated
    ns0:/ns1: aliases from other children) also strips those two real
    declarations off <metadata>'s re-serialized string, orphaning its
    rdf:/dc: prefixed children in the final output. Chromium tolerates an
    unbound prefix in inline SVG; Firefox's stricter XML parser throws
    "prefix not bound to a namespace" and refuses to render the entire SVG
    (this exact bug shipped in 13 real logos, e.g. solace.svg, before this
    fix). normalize_svg must re-declare xmlns:rdf/xmlns:dc on its own output
    root whenever a kept child still uses those prefixes.
    """
    raw = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'viewBox="0 0 250 250">'
        "<title>Solace</title>"
        "<metadata><rdf:RDF><rdf:Description>"
        "<dc:creator>RealFaviconGenerator</dc:creator>"
        "</rdf:Description></rdf:RDF></metadata>"
        '<path d="M0 0h250v250H0z"/>'
        "</svg>"
    )
    normalized = normalize_svg(raw)
    assert 'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"' in normalized
    assert 'xmlns:dc="http://purl.org/dc/elements/1.1/"' in normalized
    # The real assertion: this must be well-formed, strictly-parseable XML
    # with every prefix bound — a lenient parser accepting it isn't enough,
    # since the bug is specifically about parsers that reject unbound
    # prefixes (confirmed against Firefox on the real solace.svg).
    root = ET.fromstring(normalized)
    assert root.tag.endswith("svg")


def test_normalize_svg_omits_unused_namespace_declarations() -> None:
    """A plain SVG with no rdf:/dc:/cc: content shouldn't grow unnecessary
    xmlns:* declarations on its root.
    """
    raw = '<svg viewBox="0 0 24 24"><path d="M0 0h24v24H0z"/></svg>'
    normalized = normalize_svg(raw)
    assert "xmlns:rdf" not in normalized
    assert "xmlns:dc" not in normalized


def test_embed_raster_in_svg() -> None:
    fake_png = b"\x89PNG\r\n\x1a\nfakeimagebytes"
    svg = embed_raster_in_svg(fake_png, mime_type="image/png", title="Acme")
    assert 'viewBox="0 0 128 128"' in svg
    assert "data:image/png;base64," in svg
    assert "<title>Acme</title>" in svg
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")


def test_generate_monogram_svg() -> None:
    svg = generate_monogram_svg("Alpha Beta Corp")
    assert 'viewBox="0 0 128 128"' in svg
    assert ">AB<" in svg
    assert "hsl(" in svg
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")

    # Single-word name takes first two letters
    svg_single = generate_monogram_svg("Linear")
    assert ">LI<" in svg_single

    # Determinism: same name yields exact same color
    assert generate_monogram_svg("Acme") == generate_monogram_svg("Acme")


def test_resolve_company_logo_fallback_to_monogram() -> None:
    cfg: CompanyConfig = {"name": "Nonexistent Fake Org 999", "board": "greenhouse"}
    with patch("scraper.logos.get_session") as mock_get_sess:
        mock_sess = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {}
        mock_sess.get.return_value = mock_resp
        mock_get_sess.return_value = mock_sess

        svg, tier = resolve_company_logo(cfg)
        assert tier == "tier5_monogram"
        assert ">NF<" in svg


def test_resolve_and_save_logo(tmp_path: Path) -> None:
    cfg: CompanyConfig = {"name": "Test Acme", "board": "greenhouse"}
    with patch("scraper.logos.resolve_company_logo") as mock_resolve:
        mock_resolve.return_value = ("<svg><circle/></svg>", "tier1_vector")
        rel_path = resolve_and_save_logo(cfg, output_dir=tmp_path)
        assert rel_path == "data/logos/test-acme.svg"
        saved_file = tmp_path / "test-acme.svg"
        assert saved_file.exists()
        assert saved_file.read_text(encoding="utf-8") == "<svg><circle/></svg>"


def test_discover_companies_append_with_logo(tmp_path: Path) -> None:
    import json

    from scripts.discover_companies import ProbeResult, append_to_config

    mock_cfg = tmp_path / "mock_config.json"
    mock_cfg.write_text(json.dumps({"companies": []}), encoding="utf-8")

    probe: ProbeResult = {
        "name": "New Discover Co",
        "board": "greenhouse",
        "token": "newdiscoverco",
    }

    with (
        patch("scripts.discover_companies.CONFIG_PATH", mock_cfg),
        patch("scraper.logos.resolve_and_save_logo") as mock_save,
    ):
        mock_save.return_value = "data/logos/new-discover-co.svg"
        added = append_to_config([probe])
        assert added == 1

        data = json.loads(mock_cfg.read_text(encoding="utf-8"))
        saved_companies = data["companies"]
        assert len(saved_companies) == 1
        assert saved_companies[0]["name"] == "New Discover Co"
        assert saved_companies[0]["logo"] == "data/logos/new-discover-co.svg"
