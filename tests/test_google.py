import json
from datetime import UTC, datetime

import responses
from requests import PreparedRequest

from scraper.boards.google import (
    BASE_URL,
    GoogleScraper,
)
from scraper.config_types import GoogleConfig

COMPANY: GoogleConfig = {"name": "Google", "board": "google"}


def _build_html_page(jobs: list[list[object]], total: int = 20) -> str:
    payload = [jobs, None, total, 20]
    json_str = json.dumps(payload)
    return (
        "<!DOCTYPE html><html><head></head><body>"
        f"<script>AF_initDataCallback({{key: 'ds:1', hash: '1', data: {json_str}, sideChannel: {{}}}});</script>"
        "</body></html>"
    )


def _mock_raw_job(
    job_id: str = "1001",
    title: str = "Staff Software Engineer, Machine Learning",
    company: str = "Google",
    locations: list[str] | None = None,
    ts: int | None = None,
    overview: str = "<p>Join our core AI algorithms team.</p>",
    responsibilities: str = "<ul><li>Design ML systems</li></ul>",
    qualifications: str = "<ul><li>PhD in CS or equivalent</li></ul>",
) -> list[object]:
    if locations is None:
        locations = ["Mountain View, CA, USA", "New York, NY, USA"]
    if ts is None:
        ts = int(datetime.now(tz=UTC).timestamp())

    locs_structure = [
        [loc, [f"Address for {loc}"], loc.split(",")[0], "10001", "CA", "US"] for loc in locations
    ]

    item: list[object] = [None] * 21
    item[0] = job_id
    item[1] = title
    item[2] = f"https://www.google.com/about/careers/applications/signin?jobId={job_id}"
    item[3] = [None, responsibilities]
    item[4] = [None, qualifications]
    item[7] = company
    item[9] = locs_structure
    item[10] = [None, overview]
    item[12] = [ts, 0]
    return item


@responses.activate
def test_fetches_jobs_successfully():
    j1 = _mock_raw_job(job_id="101", title="Compiler Engineer", ts=1788952097)
    j2 = _mock_raw_job(
        job_id="102", title="Research Scientist", company="DeepMind", locations=["London, UK"]
    )

    html = _build_html_page([j1, j2], total=2)
    responses.add(responses.GET, BASE_URL, body=html, status=200)

    scraper = GoogleScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 2
    assert jobs[0].id == "google:101"
    assert jobs[0].title == "Compiler Engineer"
    assert jobs[0].company == "Google"
    assert jobs[0].source == "google"
    assert jobs[0].location == "Mountain View, CA, USA"
    assert jobs[0].locations == ["Mountain View, CA, USA", "New York, NY, USA"]
    assert jobs[0].url == "https://www.google.com/about/careers/applications/jobs/results/101"
    assert jobs[0].posted_date == "2026-09-09"
    assert "Join our core AI algorithms team." in jobs[0].description
    assert "Design ML systems" in jobs[0].description
    assert "PhD in CS or equivalent" in jobs[0].description

    assert jobs[1].id == "google:102"
    assert jobs[1].location == "London, UK"
    assert jobs[1].locations == ["London, UK"]


@responses.activate
def test_pagination():
    page1_jobs = [_mock_raw_job(job_id=f"p1_{i}") for i in range(20)]
    page2_jobs = [_mock_raw_job(job_id="p2_0")]

    empty_headers: dict[str, str] = {}

    def request_callback(request: PreparedRequest) -> tuple[int, dict[str, str], str]:
        url = str(request.url or "")
        if "page=1" in url:
            return (200, empty_headers, _build_html_page(page1_jobs, total=21))
        elif "page=2" in url:
            return (200, empty_headers, _build_html_page(page2_jobs, total=21))
        return (200, empty_headers, _build_html_page([], total=21))

    responses.add_callback(responses.GET, BASE_URL, callback=request_callback)

    scraper = GoogleScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 21
    assert jobs[0].id == "google:p1_0"
    assert jobs[20].id == "google:p2_0"


@responses.activate
def test_filters_and_company_name():
    responses.add(
        responses.GET, BASE_URL, body=_build_html_page([_mock_raw_job(job_id="1")]), status=200
    )

    cfg: GoogleConfig = {
        "name": "Google DeepMind",
        "board": "google",
        "company_name": "DeepMind",
        "query": "reinforcement learning",
        "location": "London",
    }
    scraper = GoogleScraper(cfg)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].company == "Google DeepMind"
    assert len(responses.calls) == 1
    called_url = str(responses.calls[0].request.url or "")
    assert "company=DeepMind" in called_url
    assert "q=reinforcement+learning" in called_url
    assert "location=London" in called_url


@responses.activate
def test_handles_missing_ds1_gracefully():
    html = "<html><body><h1>No scripts here</h1></body></html>"
    responses.add(responses.GET, BASE_URL, body=html, status=200)

    scraper = GoogleScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert jobs == []


@responses.activate
def test_handles_corrupt_json():
    html = "<script>AF_initDataCallback({key: 'ds:1', data: [bad json here], sideChannel: {}});</script>"
    responses.add(responses.GET, BASE_URL, body=html, status=200)

    scraper = GoogleScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert jobs == []
