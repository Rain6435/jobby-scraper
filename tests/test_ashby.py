from datetime import datetime, timedelta, timezone

import responses

from scraper.boards.ashby import AshbyScraper

COMPANY = {"name": "Loopio", "board": "ashby", "slug": "loopio"}
API = "https://api.ashbyhq.com/posting-api/job-board/loopio"


@responses.activate
def test_maps_jobs_with_dates_and_secondary_locations():
    published = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    responses.get(API, json={"jobs": [
        {
            "id": "31680a79-b812-493b-951f-951212770167",
            "title": "  Software Engineer  ",
            "location": "Toronto, ON Hub",
            "secondaryLocations": [{"location": "Remote Canada"}],
            "jobUrl": "https://jobs.ashbyhq.com/loopio/31680a79",
            "publishedAt": published,
            "descriptionPlain": "  Build great software.  ",
            "descriptionHtml": "<p>Build <b>great</b> software.</p>",
        },
    ]})

    jobs = AshbyScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "loopio:31680a79-b812-493b-951f-951212770167"
    assert job.title == "Software Engineer"
    assert job.locations == ["Toronto, ON Hub", "Remote Canada"]
    assert job.location == "Toronto, ON Hub"
    assert job.url == "https://jobs.ashbyhq.com/loopio/31680a79"
    assert job.posted_days == 2
    assert job.posted_on == "2 days ago"
    assert job.source == "ashby"
    assert job.description == "Build great software."  # descriptionPlain preferred


@responses.activate
def test_falls_back_to_stripped_html_without_plain_description():
    responses.get(API, json={"jobs": [
        {"id": "x2", "title": "Dev", "location": "Remote", "jobUrl": "u",
         "publishedAt": "", "descriptionHtml": "<p>HTML only</p>"},
    ]})

    jobs = AshbyScraper(COMPANY).fetch_jobs()

    assert jobs[0].description == "HTML only"


@responses.activate
def test_falls_back_when_no_secondary_locations_or_date():
    responses.get(API, json={"jobs": [
        {"id": "x1", "title": "Dev", "location": "Remote",
         "jobUrl": "u", "publishedAt": ""},
    ]})

    jobs = AshbyScraper(COMPANY).fetch_jobs()

    assert jobs[0].locations == ["Remote"]
    assert jobs[0].posted_days is None
    assert jobs[0].posted_on == ""
    assert jobs[0].description == ""


@responses.activate
def test_does_not_truncate_long_plain_description():
    """descriptionPlain used to be sliced at [:1500] here, independently of
    html_to_text's cap — so removing that cap alone left Ashby truncated."""
    body = "Build great software. " * 500
    responses.get(API, json={"jobs": [
        {
            "id": "abc",
            "title": "Engineer",
            "location": "Remote",
            "jobUrl": "https://jobs.ashbyhq.com/loopio/abc",
            "descriptionPlain": body,
        },
    ]})

    jobs = AshbyScraper(COMPANY).fetch_jobs()

    assert len(jobs[0].description) > 1500
    assert jobs[0].description == body.strip()
