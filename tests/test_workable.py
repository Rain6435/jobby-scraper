from datetime import UTC, datetime, timedelta

import responses

from scraper.boards.workable import WorkableScraper, posted_days_from_date_str
from scraper.config_types import WorkableConfig

COMPANY: WorkableConfig = {
    "name": "Hugging Face",
    "board": "workable",
    "company": "huggingface",
}
API = "https://apply.workable.com/api/v1/widget/accounts/huggingface"


def test_posted_days_from_date_str() -> None:
    three_ago = (datetime.now(UTC) - timedelta(days=3)).strftime("%Y-%m-%d")
    assert posted_days_from_date_str(three_ago) == 3
    assert posted_days_from_date_str(None) is None
    assert posted_days_from_date_str("") is None
    assert posted_days_from_date_str("not-a-date") is None


@responses.activate
def test_maps_jobs_with_dates_and_locations() -> None:
    published = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%d")
    responses.get(
        API,
        json={
            "name": "Hugging Face",
            "description": "AI company",
            "jobs": [
                {
                    "title": "  Senior Software Engineer  ",
                    "shortcode": "F4C096B22E",
                    "url": "https://apply.workable.com/j/F4C096B22E",
                    "published_on": published,
                    "description": "<p>Build <b>great</b> models.</p>",
                    "locations": [
                        {
                            "city": "Paris",
                            "region": "Île-de-France",
                            "country": "France",
                        },
                        {"city": "Remote", "region": "", "country": ""},
                    ],
                },
            ],
        },
    )

    jobs = WorkableScraper(COMPANY).fetch_jobs()

    assert len(responses.calls) == 1
    request_url = responses.calls[0].request.url
    assert request_url is not None and "details=true" in request_url

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "hugging-face:F4C096B22E"
    assert job.title == "Senior Software Engineer"
    assert job.locations == ["Paris, Île-de-France, France", "Remote"]
    assert job.location == "Paris, Île-de-France, France"
    assert job.url == "https://apply.workable.com/j/F4C096B22E"
    assert job.posted_days == 2
    assert job.posted_on == "2 days ago"
    assert job.source == "workable"
    assert job.description == "Build great models."


@responses.activate
def test_falls_back_to_top_level_location_fields() -> None:
    responses.get(
        API,
        json={
            "jobs": [
                {
                    "title": "Dev",
                    "shortcode": "x1",
                    "url": "u",
                    "city": "Berlin",
                    "state": "",
                    "country": "Germany",
                },
            ],
        },
    )

    jobs = WorkableScraper(COMPANY).fetch_jobs()

    assert jobs[0].locations == ["Berlin, Germany"]
    assert jobs[0].posted_days is None
    assert jobs[0].posted_on == ""
    assert jobs[0].description == ""


@responses.activate
def test_no_locations_at_all() -> None:
    responses.get(
        API,
        json={
            "jobs": [
                {"title": "Dev", "shortcode": "x2", "url": "u"},
            ],
        },
    )

    jobs = WorkableScraper(COMPANY).fetch_jobs()

    assert jobs[0].locations == []
    assert jobs[0].location == ""
