from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import responses

from scraper.boards.jibe import JibeScraper
from scraper.config_types import JibeConfig

GITHUB_CONFIG: JibeConfig = {
    "name": "GitHub",
    "board": "jibe",
    "tenant": "githubinc",
}

URL_CONFIG: JibeConfig = {
    "name": "GitHub Careers",
    "board": "jibe",
    "url": "https://www.github.careers",
}


@responses.activate
def test_maps_jibe_jobs_with_iso_dates_and_locations() -> None:
    created = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S+0000")
    mock_payload = {
        "totalCount": 1,
        "jobs": [
            {
                "data": {
                    "slug": "5677",
                    "req_id": "5677",
                    "title": "Staff Software Engineer, Search",
                    "description": "<p>Build search systems for <strong>millions</strong> of devs.</p>",
                    "create_date": created,
                    "location_name": "Canada Remote",
                    "full_location": "Canada",
                    "city": "Vancouver",
                    "state": "BC",
                    "country": "Canada",
                    "multipleLocations": True,
                    "additional_locations": [
                        {
                            "location_name": "US Remote",
                            "country": "United States",
                        }
                    ],
                    "canonical_url": "https://githubinc.jibeapply.com/jobs/5677?lang=en-us",
                }
            }
        ],
    }

    responses.get(
        "https://githubinc.jibeapply.com/api/jobs",
        json=mock_payload,
        status=200,
    )

    scraper = JibeScraper(GITHUB_CONFIG)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "github:5677"
    assert job.company == "GitHub"
    assert job.title == "Staff Software Engineer, Search"
    assert job.location == "Canada Remote"
    assert job.locations == ["Canada Remote", "US Remote"]
    assert job.url == "https://githubinc.jibeapply.com/jobs/5677?lang=en-us"
    assert job.posted_days == 2
    assert job.posted_on == "2 days ago"
    assert job.source == "jibe"
    assert "Build search systems for millions of devs." in job.description


@responses.activate
def test_jibe_custom_url_and_fallback_fields() -> None:
    mock_payload = {
        "totalCount": 1,
        "jobs": [
            {
                "data": {
                    "req_id": "1001",
                    "title": "Product Designer",
                    "city": "New York",
                    "state": "NY",
                    "country": "United States",
                    "meta_data": {
                        "canonical_url": "https://www.github.careers/jobs/1001",
                    },
                }
            }
        ],
    }

    responses.get(
        "https://www.github.careers/api/jobs",
        json=mock_payload,
        status=200,
    )

    scraper = JibeScraper(URL_CONFIG)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "github-careers:1001"
    assert job.location == "New York, NY, United States"
    assert job.locations == ["New York, NY, United States"]
    assert job.url == "https://www.github.careers/jobs/1001"
    assert job.posted_days is None
    assert job.posted_on == ""


def test_jibe_requires_tenant_or_url() -> None:
    invalid_config: JibeConfig = {
        "name": "Invalid",
        "board": "jibe",
    }
    scraper = JibeScraper(invalid_config)
    with pytest.raises(ValueError, match="neither 'tenant' nor 'url'"):
        scraper.fetch_jobs()
