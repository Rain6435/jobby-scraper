from datetime import datetime, timedelta, timezone

import responses

from scraper.boards.recruitee import RecruiteeScraper, posted_days_from_recruitee_ts

from scraper.config_types import RecruiteeConfig

COMPANY: RecruiteeConfig = {"name": "Sendcloud", "board": "recruitee", "company": "sendcloud"}
API = "https://sendcloud.recruitee.com/api/offers/"


def test_posted_days_from_recruitee_ts() -> None:
    three_ago = (datetime.now(timezone.utc) - timedelta(days=3, hours=2)).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )
    assert posted_days_from_recruitee_ts(three_ago) == 3
    assert posted_days_from_recruitee_ts("") is None
    assert posted_days_from_recruitee_ts("not-a-date") is None


@responses.activate
def test_maps_jobs_with_dates_and_structured_locations() -> None:
    published = (datetime.now(timezone.utc) - timedelta(days=2)).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )
    responses.get(API, json={"offers": [
        {
            "id": 2429738,
            "title": "  Senior Marketer  ",
            "careers_url": "https://sendcloud.recruitee.com/o/senior-marketer",
            "published_at": published,
            "description": "<p>Grow the <b>brand</b>.</p>",
            "city": "Amsterdam",
            "state_name": "Noord-Holland",
            "country": "Netherlands",
            "locations": [
                {"city": "Amsterdam", "state": "Noord-Holland", "country": "Netherlands"},
            ],
        },
    ]})

    jobs = RecruiteeScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "sendcloud:2429738"
    assert job.title == "Senior Marketer"
    assert job.locations == ["Amsterdam, Noord-Holland, Netherlands"]
    assert job.location == "Amsterdam, Noord-Holland, Netherlands"
    assert job.url == "https://sendcloud.recruitee.com/o/senior-marketer"
    assert job.posted_days == 2
    assert job.posted_on == "2 days ago"
    assert job.source == "recruitee"
    assert job.description == "Grow the brand."


@responses.activate
def test_falls_back_to_flat_fields_without_structured_locations() -> None:
    responses.get(API, json={"offers": [
        {"id": 1, "title": "Dev", "careers_url": "u", "published_at": "",
         "city": "Berlin", "country": "Germany"},
    ]})

    jobs = RecruiteeScraper(COMPANY).fetch_jobs()

    assert jobs[0].locations == ["Berlin, Germany"]
    assert jobs[0].posted_days is None
    assert jobs[0].posted_on == ""
    assert jobs[0].description == ""


@responses.activate
def test_falls_back_when_no_location_at_all() -> None:
    responses.get(API, json={"offers": [
        {"id": 1, "title": "Dev", "careers_url": "u", "published_at": ""},
    ]})

    jobs = RecruiteeScraper(COMPANY).fetch_jobs()

    assert jobs[0].locations == []
    assert jobs[0].location == ""
