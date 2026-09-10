import json
from datetime import UTC, datetime

import responses
from requests import PreparedRequest

from scraper.boards.netflix import (
    DETAIL_URL,
    SEARCH_URL,
    NetflixPosition,
    NetflixScraper,
    NetflixSearchResponse,
)
from scraper.config_types import NetflixConfig

COMPANY: NetflixConfig = {"name": "Netflix", "board": "netflix"}


def _mock_position(
    pos_id: int = 790318358916,
    name: str = "Front-End Developer",
    location: str = "Vancouver,Canada",
    t_create: int | None = None,
) -> NetflixPosition:
    if t_create is None:
        t_create = int(datetime.now(tz=UTC).timestamp())
    return NetflixPosition(
        id=pos_id,
        name=name,
        posting_name=name,
        location=location,
        locations=[location],
        department="Feature Animation",
        t_create=t_create,
        canonicalPositionUrl=f"https://explore.jobs.netflix.net/careers/job/{pos_id}",
    )


@responses.activate
def test_fetches_jobs_successfully():
    pos1 = _mock_position(pos_id=101, name="Backend Engineer", t_create=1788480000)
    pos2 = _mock_position(pos_id=102, name="Data Engineer", location="Los Gatos,California,USA")

    search_resp = NetflixSearchResponse(count=2, positions=[pos1, pos2])
    responses.add(responses.GET, SEARCH_URL, json=search_resp, status=200)

    # Detail endpoints
    responses.add(
        responses.GET,
        DETAIL_URL.format(id="101"),
        json={"id": 101, "job_description": "<p>Work on scalable video streaming systems.</p>"},
        status=200,
    )
    responses.add(
        responses.GET,
        DETAIL_URL.format(id="102"),
        json={"id": 102, "job_description": "<p>Big data pipelines with Spark.</p>"},
        status=200,
    )

    scraper = NetflixScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 2
    assert jobs[0].id == "netflix:101"
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].company == "Netflix"
    assert jobs[0].source == "netflix"
    assert jobs[0].location == "Vancouver,Canada"
    assert jobs[0].locations == ["Vancouver,Canada"]
    assert jobs[0].url == "https://explore.jobs.netflix.net/careers/job/101"
    assert jobs[0].posted_date == "2026-09-04"
    assert jobs[0].posted_on != ""
    assert jobs[0].description == "Work on scalable video streaming systems."

    assert jobs[1].id == "netflix:102"
    assert jobs[1].description == "Big data pipelines with Spark."


@responses.activate
def test_pagination():
    page1_positions = [_mock_position(pos_id=100 + i) for i in range(10)]
    page2_positions = [_mock_position(pos_id=200)]

    empty_headers: dict[str, str] = {}

    def search_callback(request: PreparedRequest) -> tuple[int, dict[str, str], str]:
        url = str(request.url or "")
        if "start=0" in url:
            return (200, empty_headers, json.dumps({"count": 11, "positions": page1_positions}))
        elif "start=10" in url:
            return (200, empty_headers, json.dumps({"count": 11, "positions": page2_positions}))
        return (200, empty_headers, json.dumps({"count": 11, "positions": []}))

    responses.add_callback(
        responses.GET, SEARCH_URL, callback=search_callback, content_type="application/json"
    )

    for pid in [100 + i for i in range(10)] + [200]:
        responses.add(
            responses.GET,
            DETAIL_URL.format(id=str(pid)),
            json={"id": pid, "job_description": "Job details"},
            status=200,
        )

    scraper = NetflixScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 11
    assert jobs[0].id == "netflix:100"
    assert jobs[10].id == "netflix:200"


@responses.activate
def test_fetch_details_disabled():
    pos = _mock_position(pos_id=505, name="Designer")
    responses.add(responses.GET, SEARCH_URL, json={"count": 1, "positions": [pos]}, status=200)

    cfg: NetflixConfig = {"name": "Netflix", "board": "netflix", "fetch_details": False}
    scraper = NetflixScraper(cfg)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].description == ""
    # Verify no detail requests were made
    assert len(responses.calls) == 1


@responses.activate
def test_handles_empty_search():
    responses.add(responses.GET, SEARCH_URL, json={"count": 0, "positions": []}, status=200)

    scraper = NetflixScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert jobs == []


@responses.activate
def test_detail_failure_fallback():
    pos = _mock_position(pos_id=777, name="Site Reliability Engineer")
    responses.add(responses.GET, SEARCH_URL, json={"count": 1, "positions": [pos]}, status=200)
    responses.add(responses.GET, DETAIL_URL.format(id="777"), status=500)

    scraper = NetflixScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].id == "netflix:777"
    assert jobs[0].description == ""
