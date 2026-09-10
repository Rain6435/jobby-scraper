import json
from datetime import UTC, datetime

import responses

from scraper.boards.amazon import (
    API,
    AmazonResponse,
    AmazonScraper,
    RawAmazonJob,
    parse_amazon_date,
)
from scraper.config_types import AmazonConfig

COMPANY: AmazonConfig = {"name": "Amazon", "board": "amazon"}


def _job(
    job_id: str = "10535552",
    title: str = "Software Development Engineer",
    job_path: str = "/en/jobs/10535552/software-development-engineer",
    location: str = "Seattle, Washington, USA",
    locations: list[str] | None = None,
    posted_date: str = "September  9, 2026",
    description: str = "<p>Build the future at Amazon.</p>",
    basic_qualifications: str = "- 2+ years experience",
    preferred_qualifications: str = "- Master degree in CS",
) -> RawAmazonJob:
    if locations is None:
        loc_json = json.dumps(
            {
                "normalizedLocation": location,
                "city": "Seattle",
                "type": "ONSITE",
            }
        )
        locations = [loc_json]

    return RawAmazonJob(
        id_icims=job_id,
        id=job_id,
        title=f"  {title}  ",
        job_path=job_path,
        normalized_location=location,
        location=location,
        locations=locations,
        posted_date=posted_date,
        description=description,
        basic_qualifications=basic_qualifications,
        preferred_qualifications=preferred_qualifications,
        company_name="Amazon.com Services LLC",
    )


def _page(
    jobs: list[RawAmazonJob], hits: int | None = None, error: str | None = None
) -> AmazonResponse:
    return AmazonResponse(
        hits=hits if hits is not None else len(jobs),
        jobs=jobs,
        error=error,
    )


@responses.activate
def test_maps_a_job() -> None:
    responses.get(API, json=_page([_job()]))

    jobs = AmazonScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    j = jobs[0]
    assert j.id == "amazon:10535552"
    assert j.company == "Amazon"
    assert j.title == "Software Development Engineer"
    assert j.location == "Seattle, Washington, USA"
    assert j.locations == ["Seattle, Washington, USA"]
    assert j.url == "https://www.amazon.jobs/en/jobs/10535552/software-development-engineer"
    assert j.source == "amazon"
    assert "Build the future at Amazon." in j.description
    assert "Basic Qualifications:\n- 2+ years experience" in j.description
    assert "Preferred Qualifications:\n- Master degree in CS" in j.description


@responses.activate
def test_multi_location_parsing() -> None:
    loc1 = json.dumps({"normalizedLocation": "Seattle, Washington, USA"})
    loc2 = json.dumps({"normalizedLocation": "Austin, Texas, USA"})
    raw = _job(locations=[loc1, loc2])
    responses.get(API, json=_page([raw]))

    jobs = AmazonScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].locations == ["Seattle, Washington, USA", "Austin, Texas, USA"]


def test_parse_amazon_date() -> None:
    now = datetime.now(UTC)
    current_date_str = now.strftime("%B %d, %Y")
    assert parse_amazon_date(current_date_str) == 0
    assert parse_amazon_date("") is None
    assert parse_amazon_date("invalid-date-format") is None


@responses.activate
def test_paginates_until_all_jobs_fetched() -> None:
    responses.get(API, json=_page([_job(job_id="1"), _job(job_id="2")], hits=3))
    responses.get(API, json=_page([_job(job_id="3")], hits=3))

    jobs = AmazonScraper(COMPANY).fetch_jobs()

    assert {j.id for j in jobs} == {"amazon:1", "amazon:2", "amazon:3"}
    assert len(responses.calls) == 2


@responses.activate
def test_stops_on_api_error() -> None:
    responses.get(API, json=_page([], error="Cannot return more than 10000 results at once"))

    jobs = AmazonScraper(COMPANY).fetch_jobs()

    assert jobs == []
    assert len(responses.calls) == 1


@responses.activate
def test_passes_filter_parameters() -> None:
    cfg: AmazonConfig = {
        "name": "AWS",
        "board": "amazon",
        "category": "software-development",
        "country": "USA",
        "business_category": "amazon-web-services",
    }
    responses.get(API, json=_page([_job()]))

    AmazonScraper(cfg).fetch_jobs()

    url = responses.calls[0].request.url or ""
    assert "category%5B%5D=software-development" in url or "category[]=software-development" in url
    assert "country%5B%5D=USA" in url or "country[]=USA" in url
    assert (
        "business_category%5B%5D=amazon-web-services" in url
        or "business_category[]=amazon-web-services" in url
    )
