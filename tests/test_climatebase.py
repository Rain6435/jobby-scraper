from datetime import UTC, datetime, timedelta
from typing import Unpack, cast

import responses

from scraper.boards.climatebase import API, ClimatebaseHit, ClimatebaseScraper
from scraper.config_types import ClimatebaseConfig

COMPANY: ClimatebaseConfig = {
    "name": "Climatebase",
    "board": "climatebase",
    "keywords": ["environmental analyst"],
}


def _hit(job_id: str = "12345", **overrides: Unpack[ClimatebaseHit]) -> ClimatebaseHit:
    hit: ClimatebaseHit = {
        "id": job_id,
        "title": "  Environmental Analyst  ",
        "name_of_employer": "GFL Environmental",
        "locations": ["Toronto, ON, CA", "Ottawa, ON, CA"],
        "countries": ["Canada"],
        "how_to_apply": "https://jobs.example.com/12345",
        "activation_date": (datetime.now(UTC) - timedelta(days=3)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        ),
        "description": "<p>Monitor <b>environmental</b> compliance.</p>",
    }
    hit.update(overrides)
    return hit


def _page(hits: list[ClimatebaseHit], page: int = 0, nb_pages: int = 1) -> dict[str, object]:
    return {"hits": hits, "page": page, "nbPages": nb_pages, "nbHits": len(hits)}


@responses.activate
def test_maps_a_hit() -> None:
    responses.post(API, json=_page([_hit()]))

    jobs = ClimatebaseScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "climatebase:12345"
    assert job.company == "GFL Environmental"
    assert job.title == "Environmental Analyst"
    assert job.locations == ["Toronto, ON, CA", "Ottawa, ON, CA"]
    assert job.location == "Toronto, ON, CA"
    assert job.url == "https://jobs.example.com/12345"
    assert job.posted_days == 3
    assert job.posted_on == "3 days ago"
    assert job.source == "climatebase"
    assert job.description == "Monitor environmental compliance."


@responses.activate
def test_falls_back_to_board_name_when_employer_missing() -> None:
    responses.post(API, json=_page([_hit(name_of_employer="")]))

    jobs = ClimatebaseScraper(COMPANY).fetch_jobs()

    assert jobs[0].company == "Climatebase"


@responses.activate
def test_dedupes_jobs_matched_by_more_than_one_keyword() -> None:
    company: ClimatebaseConfig = {
        "name": "Climatebase",
        "board": "climatebase",
        "keywords": ["environmental analyst", "sustainability"],
    }
    responses.post(API, json=_page([_hit()]))
    responses.post(API, json=_page([_hit()]))

    jobs = ClimatebaseScraper(company).fetch_jobs()

    assert len(jobs) == 1
    assert len(responses.calls) == 2


@responses.activate
def test_paginates_until_last_page() -> None:
    company: ClimatebaseConfig = {
        "name": "Climatebase",
        "board": "climatebase",
        "keywords": ["environmental"],
    }
    responses.post(API, json=_page([_hit("1"), _hit("2")], page=0, nb_pages=2))
    responses.post(API, json=_page([_hit("3")], page=1, nb_pages=2))

    jobs = ClimatebaseScraper(company).fetch_jobs()

    assert {j.id for j in jobs} == {"climatebase:1", "climatebase:2", "climatebase:3"}
    assert len(responses.calls) == 2


@responses.activate
def test_defaults_to_empty_query_when_no_keywords_configured() -> None:
    company: ClimatebaseConfig = {"name": "Climatebase", "board": "climatebase"}
    responses.post(API, json=_page([_hit()]))

    jobs = ClimatebaseScraper(company).fetch_jobs()

    assert len(jobs) == 1
    import json as json_module

    sent = json_module.loads(cast(bytes, responses.calls[0].request.body))
    assert sent["query"] == ""
