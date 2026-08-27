from datetime import datetime, timedelta, timezone
from typing import Unpack

import pytest
import responses

from scraper.boards.usajobs import (
    UsajobsMatchedObjectDescriptor,
    UsajobsScraper,
    UsajobsSearchResultItem,
)
from scraper.config_types import UsajobsConfig

COMPANY: UsajobsConfig = {"name": "US Federal Government", "board": "usajobs"}
API = "https://data.usajobs.gov/api/search"


def _item(
    matched_object_id: str = "833196500", **overrides: Unpack[UsajobsMatchedObjectDescriptor],
) -> UsajobsSearchResultItem:
    descriptor: UsajobsMatchedObjectDescriptor = {
        "PositionTitle": "  IT Specialist  ",
        "OrganizationName": "Department of Veterans Affairs",
        "DepartmentName": "Department of Veterans Affairs",
        "PositionURI": "https://www.usajobs.gov/job/833196500",
        "PositionLocation": [
            {"LocationName": "Washington, District of Columbia"},
            {"LocationName": "Remote"},
        ],
        "PublicationStartDate": (datetime.now(timezone.utc) - timedelta(days=2)).strftime(
            "%Y-%m-%dT%H:%M:%S.0000"
        ),
        "QualificationSummary": "<p>Must have <b>experience</b>.</p>",
        "UserArea": {"Details": {"JobSummary": "<p>Support IT systems.</p>"}},
    }
    descriptor.update(overrides)
    return {"MatchedObjectId": matched_object_id, "MatchedObjectDescriptor": descriptor}


@responses.activate
def test_maps_jobs_with_per_result_company_and_locations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USAJOBS_API_KEY", "key")
    monkeypatch.setenv("USAJOBS_USER_AGENT", "test@example.com")
    responses.get(API, json={"SearchResult": {"SearchResultItems": [_item()]}})

    jobs = UsajobsScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "us-federal-government:833196500"
    assert job.company == "Department of Veterans Affairs"
    assert job.title == "IT Specialist"
    assert job.locations == ["Washington, District of Columbia", "Remote"]
    assert job.location == "Washington, District of Columbia"
    assert job.url == "https://www.usajobs.gov/job/833196500"
    assert job.posted_days == 2
    assert job.posted_on == "2 days ago"
    assert job.source == "usajobs"
    assert job.description == "Support IT systems."  # JobSummary preferred


@responses.activate
def test_falls_back_to_qualification_summary_and_display_location(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USAJOBS_API_KEY", "key")
    monkeypatch.setenv("USAJOBS_USER_AGENT", "test@example.com")
    item = _item(
        PositionLocation=[],
        PositionLocationDisplay="Multiple Locations",
        UserArea={},
    )
    responses.get(API, json={"SearchResult": {"SearchResultItems": [item]}})

    jobs = UsajobsScraper(COMPANY).fetch_jobs()

    assert jobs[0].locations == ["Multiple Locations"]
    assert jobs[0].location == "Multiple Locations"
    assert jobs[0].description == "Must have experience."


@responses.activate
def test_falls_back_to_department_name_when_organization_name_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USAJOBS_API_KEY", "key")
    monkeypatch.setenv("USAJOBS_USER_AGENT", "test@example.com")
    item = _item(OrganizationName="")
    responses.get(API, json={"SearchResult": {"SearchResultItems": [item]}})

    jobs = UsajobsScraper(COMPANY).fetch_jobs()

    assert jobs[0].company == "Department of Veterans Affairs"


def test_returns_empty_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("USAJOBS_API_KEY", raising=False)
    monkeypatch.delenv("USAJOBS_USER_AGENT", raising=False)

    # No responses.activate/registered mock — a real HTTP call would raise
    # ConnectionError, proving fetch_jobs() returns before ever attempting one.
    assert UsajobsScraper(COMPANY).fetch_jobs() == []


@responses.activate
def test_paginates_until_a_short_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USAJOBS_API_KEY", "key")
    monkeypatch.setenv("USAJOBS_USER_AGENT", "test@example.com")
    full_page = [_item(str(i)) for i in range(500)]
    # responses matches registered URLs in order for repeated calls to the same URL.
    responses.get(API, json={"SearchResult": {"SearchResultItems": full_page}})
    responses.get(API, json={"SearchResult": {"SearchResultItems": full_page}})
    responses.get(API, json={"SearchResult": {"SearchResultItems": [_item("last")]}})

    jobs = UsajobsScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1001
    assert len(responses.calls) == 3
