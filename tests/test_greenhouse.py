from datetime import datetime, timedelta, timezone

import responses

from scraper.boards.greenhouse import GreenhouseScraper, posted_days_from_iso

COMPANY = {"name": "Asana", "board": "greenhouse", "token": "asana"}
API = "https://boards-api.greenhouse.io/v1/boards/asana/jobs"


def test_posted_days_from_iso():
    three_ago = (datetime.now(timezone.utc) - timedelta(days=3, hours=2)).isoformat()
    assert posted_days_from_iso(three_ago) == 3
    assert posted_days_from_iso("") is None
    assert posted_days_from_iso("not-a-date") is None


@responses.activate
def test_maps_jobs_with_dates_and_offices():
    published = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    responses.get(API, json={"jobs": [
        {
            "id": 7740145,
            "title": "  AI Engineer  ",
            "location": {"name": "Toronto"},
            "offices": [{"name": "Toronto", "location": "Toronto, Canada"}],
            "absolute_url": "https://www.asana.com/jobs/apply/7740145",
            "first_published": published,
            "content": "<p>Build cool stuff.</p>",
        },
    ]})

    jobs = GreenhouseScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "asana:7740145"
    assert job.title == "AI Engineer"
    assert job.locations == ["Toronto, Canada"]   # offices.location preferred
    assert job.location == "Toronto, Canada"
    assert job.url == "https://www.asana.com/jobs/apply/7740145"
    assert job.posted_days == 2
    assert job.posted_on == "2 days ago"
    assert job.source == "greenhouse"
    assert job.description == "Build cool stuff."
    request_url = responses.calls[0].request.url
    assert request_url is not None
    assert request_url.endswith("?content=true")


@responses.activate
def test_falls_back_to_location_name_without_offices():
    responses.get(API, json={"jobs": [
        {"id": 1, "title": "Dev", "location": {"name": "Warsaw"},
         "absolute_url": "u", "first_published": ""},
    ]})

    jobs = GreenhouseScraper(COMPANY).fetch_jobs()

    assert jobs[0].locations == ["Warsaw"]
    assert jobs[0].posted_days is None
    assert jobs[0].posted_on == ""
    assert jobs[0].description == ""
