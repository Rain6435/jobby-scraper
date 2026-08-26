from datetime import datetime, timedelta, timezone

import responses

from scraper.boards.teamtailor import TeamtailorScraper, posted_days_from_iso

COMPANY = {"name": "Sessions", "board": "teamtailor", "company": "sessions"}
API = "https://sessions.teamtailor.com/jobs.json"


def test_posted_days_from_iso():
    three_ago = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    assert posted_days_from_iso(three_ago) == 3
    assert posted_days_from_iso(None) is None
    assert posted_days_from_iso("") is None
    assert posted_days_from_iso("not-a-date") is None


@responses.activate
def test_maps_jobs_with_dates_and_locations():
    published = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    responses.get(API, json={
        "version": "https://jsonfeed.org/version/1.1",
        "title": "Sessions",
        "items": [
            {
                "id": "3ce2c88b-cbc6-4ae9-8ecb-000466c69037",
                "title": "  Group Financial Controller  ",
                "url": "https://sessions.teamtailor.com/jobs/8124573",
                "date_published": published,
                "content_html": "<p>Lead <b>finance</b>.</p>",
                "_jobposting": {
                    "jobLocation": [
                        {
                            "address": {
                                "addressLocality": "Stockholm",
                                "addressRegion": "Stockholm County",
                                "addressCountry": "SE",
                            }
                        },
                        {"address": {"addressLocality": "London", "addressCountry": "UK"}},
                    ]
                },
            },
        ],
    })

    jobs = TeamtailorScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "sessions:3ce2c88b-cbc6-4ae9-8ecb-000466c69037"
    assert job.title == "Group Financial Controller"
    assert job.locations == ["Stockholm, Stockholm County, SE", "London, UK"]
    assert job.location == "Stockholm, Stockholm County, SE"
    assert job.url == "https://sessions.teamtailor.com/jobs/8124573"
    assert job.posted_days == 2
    assert job.posted_on == "2 days ago"
    assert job.source == "teamtailor"
    assert job.description == "Lead finance."


@responses.activate
def test_missing_jobposting_falls_back_gracefully():
    responses.get(API, json={
        "items": [
            {"id": "x1", "title": "Dev", "url": "u"},
        ],
    })

    jobs = TeamtailorScraper(COMPANY).fetch_jobs()

    assert jobs[0].locations == []
    assert jobs[0].location == ""
    assert jobs[0].posted_days is None
    assert jobs[0].posted_on == ""
    assert jobs[0].description == ""


@responses.activate
def test_malformed_job_location_entries_skipped():
    responses.get(API, json={
        "items": [
            {
                "id": "x2",
                "title": "Dev",
                "url": "u",
                "_jobposting": {"jobLocation": [{"address": {}}, None]},
            },
        ],
    })

    jobs = TeamtailorScraper(COMPANY).fetch_jobs()

    assert jobs[0].locations == []
