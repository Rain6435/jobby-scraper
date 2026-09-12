from __future__ import annotations

import json

import responses

from scraper.boards import SCRAPERS
from scraper.boards.quebec_emploi import (
    DETAIL_URL,
    SEARCH_URL,
    QuebecEmploiScraper,
    _resolve_admin_regions,
)
from scraper.config_types import QuebecEmploiConfig

COMPANY: QuebecEmploiConfig = {"name": "Québec emploi", "board": "quebec_emploi"}

SAMPLE_SEARCH_RESPONSE = {
    "meta": {"total_hits": 2},
    "items": [
        {
            "nom_ville": "Montréal",
            "titre": "Développeur Full Stack",
            "latitude": 45.5017,
            "expiration_date": "2026-10-15",
            "employeur": "Tech Solutions Inc.",
            "ide_affch": 548320,
            "longitude": -73.5673,
        },
        {
            "nom_ville": "Québec",
            "titre": "Analyste en informatique",
            "latitude": 46.8139,
            "expiration_date": "2026-10-20",
            "employeur": "Gouvernement du Québec",
            "ide_affch": 548321,
            "longitude": -71.2080,
        },
    ],
}

SAMPLE_DETAIL_RESPONSE = {
    "title": "Développeur Full Stack",
    "googleForJob": {
        "key": (
            '<script type="application/ld+json">{\n'
            '"@context":"https://schema.org/",\n'
            '"@type":"JobPosting",\n'
            '"title":"Développeur Full Stack",\n'
            '"description":"<p>Nous recherchons un développeur Full Stack expérimenté.</p>",\n'
            '"datePosted":"2026-09-10",\n'
            '"validThrough":"2026-10-15",\n'
            '"hiringOrganization":{"name":"Tech Solutions Inc."}\n'
            "}</script>"
        )
    },
    "body": [
        {"id": 46, "label": "Description du poste", "content": "<p>Description détaillée</p>"}
    ],
}


def test_registry_resolution() -> None:
    assert SCRAPERS["quebec_emploi"] is QuebecEmploiScraper
    assert SCRAPERS["emploi_quebec"] is QuebecEmploiScraper


def test_resolve_admin_regions() -> None:
    assert _resolve_admin_regions("06", None, None) == ["06"]
    assert _resolve_admin_regions("Montréal", None, None) == ["06"]
    assert _resolve_admin_regions("montreal", None, None) == ["06"]
    assert _resolve_admin_regions(None, ["Capitale-Nationale", "13"], None) == ["03", "13"]
    assert _resolve_admin_regions(None, None, "Gatineau") == ["07"]
    assert _resolve_admin_regions("Unknown City", None, None) == []


@responses.activate
def test_fetch_jobs_default() -> None:
    responses.add(
        responses.POST,
        SEARCH_URL,
        json=SAMPLE_SEARCH_RESPONSE,
        status=200,
    )
    # Page 2 returns empty to end pagination
    responses.add(
        responses.POST,
        SEARCH_URL,
        json={"meta": {"total_hits": 2}, "items": []},
        status=200,
    )

    scraper = QuebecEmploiScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 2
    j1 = jobs[0]
    assert j1.id == "quebec-emploi:548320"
    assert j1.company == "Tech Solutions Inc."
    assert j1.title == "Développeur Full Stack"
    assert j1.location == "Montréal, QC"
    assert j1.locations == ["Montréal, QC"]
    assert j1.url == "https://www.quebecemploi.gouv.qc.ca/plateforme-emploi/poste/548320"
    assert j1.posted_on == "Expires: 2026-10-15"
    assert j1.source == "quebec_emploi"
    assert "Tech Solutions Inc." in j1.description

    j2 = jobs[1]
    assert j2.id == "quebec-emploi:548321"
    assert j2.company == "Gouvernement du Québec"
    assert j2.location == "Québec, QC"


@responses.activate
def test_fetch_jobs_pagination() -> None:
    page1 = {
        "meta": {"total_hits": 3},
        "items": [
            {
                "nom_ville": "Laval",
                "titre": "Role 1",
                "employeur": "Company A",
                "ide_affch": 101,
                "expiration_date": "2026-11-01",
            }
        ],
    }
    page2 = {
        "meta": {"total_hits": 3},
        "items": [
            {
                "nom_ville": "Sherbrooke",
                "titre": "Role 2",
                "employeur": "Company B",
                "ide_affch": 102,
                "expiration_date": "2026-11-02",
            }
        ],
    }
    page3: dict[str, object] = {"meta": {"total_hits": 3}, "items": []}

    responses.add(responses.POST, SEARCH_URL, json=page1, status=200)
    responses.add(responses.POST, SEARCH_URL, json=page2, status=200)
    responses.add(responses.POST, SEARCH_URL, json=page3, status=200)

    scraper = QuebecEmploiScraper(
        {"name": "Québec emploi", "board": "quebec_emploi", "max_pages": 5}
    )
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 2
    assert jobs[0].id == "quebec-emploi:101"
    assert jobs[1].id == "quebec-emploi:102"
    assert len(responses.calls) == 3


@responses.activate
def test_fetch_jobs_with_query_and_region() -> None:
    responses.add(
        responses.POST,
        SEARCH_URL,
        json=SAMPLE_SEARCH_RESPONSE,
        status=200,
    )
    responses.add(
        responses.POST,
        SEARCH_URL,
        json={"meta": {"total_hits": 2}, "items": []},
        status=200,
    )

    cfg: QuebecEmploiConfig = {
        "name": "Québec emploi Montréal",
        "board": "quebec_emploi",
        "query": "développeur",
        "region": "Montréal",
    }
    scraper = QuebecEmploiScraper(cfg)
    jobs = scraper.fetch_jobs()
    assert len(jobs) == 2

    req_body = responses.calls[0].request.body
    assert isinstance(req_body, (str, bytes))
    body = json.loads(req_body)
    assert isinstance(body, dict)
    assert body["filter"]["inputSearch"] == "développeur"
    assert body["filter"]["adminRegion"] == ["06"]


@responses.activate
def test_fetch_jobs_client_side_filters() -> None:
    responses.add(
        responses.POST,
        SEARCH_URL,
        json=SAMPLE_SEARCH_RESPONSE,
        status=200,
    )
    responses.add(
        responses.POST,
        SEARCH_URL,
        json={"meta": {"total_hits": 2}, "items": []},
        status=200,
    )

    # Filter only Full Stack in title and Montréal in location
    cfg: QuebecEmploiConfig = {
        "name": "Québec emploi",
        "board": "quebec_emploi",
        "title": "Full Stack",
        "location": "Montréal",
    }
    scraper = QuebecEmploiScraper(cfg)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].title == "Développeur Full Stack"


@responses.activate
def test_fetch_jobs_with_details() -> None:
    responses.add(
        responses.POST,
        SEARCH_URL,
        json=SAMPLE_SEARCH_RESPONSE,
        status=200,
    )
    responses.add(
        responses.POST,
        SEARCH_URL,
        json={"meta": {"total_hits": 2}, "items": []},
        status=200,
    )

    detail_548320 = DETAIL_URL.format(job_id="548320", lang="fr")
    detail_548321 = DETAIL_URL.format(job_id="548321", lang="fr")

    responses.add(responses.GET, detail_548320, json=SAMPLE_DETAIL_RESPONSE, status=200)
    responses.add(
        responses.GET,
        detail_548321,
        json={
            "title": "Analyste en informatique",
            "body": [
                {
                    "id": 46,
                    "label": "Description du poste",
                    "content": "<p>Description Analyste</p>",
                }
            ],
        },
        status=200,
    )

    cfg: QuebecEmploiConfig = {
        "name": "Québec emploi",
        "board": "quebec_emploi",
        "fetch_details": True,
    }
    scraper = QuebecEmploiScraper(cfg)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 2
    assert "Nous recherchons un développeur Full Stack expérimenté." in jobs[0].description
    assert jobs[0].posted_on == "2026-09-10"
    assert "Description Analyste" in jobs[1].description


@responses.activate
def test_fetch_jobs_handles_errors() -> None:
    responses.add(responses.POST, SEARCH_URL, status=500)

    scraper = QuebecEmploiScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert jobs == []
