import responses

from scraper.boards.janestreet import (
    JOBS_URL,
    JaneStreetScraper,
)
from scraper.config_types import JaneStreetConfig

COMPANY: JaneStreetConfig = {"name": "Jane Street", "board": "janestreet"}

SAMPLE_JOBS = [
    {
        "id": 8631912002,
        "position": "Software Engineer",
        "category": "Technology",
        "availability": "Full-Time: Experienced",
        "city": "NYC",
        "overview": "<p>Build high-performance distributed trading systems in OCaml.</p>",
        "team": "Trading Systems",
        "min_salary": "250,000",
        "max_salary": "300,000",
    },
    {
        "id": 8631912003,
        "position": "Quantitative Researcher",
        "category": "Trading, Research, and Machine Learning",
        "availability": "Full-Time: New Grad",
        "city": "LDN",
        "overview": "<p>Develop statistical models and machine learning strategies.</p>",
        "team": "Research",
        "min_salary": "150,000",
        "max_salary": "200,000",
    },
    {
        "id": 8631912004,
        "position": "Trader",
        "category": "Trading",
        "city": "HKG",
        "overview": "<p>Trade diverse asset classes globally.</p>",
    },
    {
        "id": "",
        "position": "Invalid",
    },
]


@responses.activate
def test_fetch_jobs_success() -> None:
    responses.get(JOBS_URL, json=SAMPLE_JOBS)

    scraper = JaneStreetScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 3

    j1 = jobs[0]
    assert j1.id == "jane-street:8631912002"
    assert j1.company == "Jane Street"
    assert j1.title == "Software Engineer"
    assert j1.location == "New York, NY"
    assert j1.locations == ["New York, NY"]
    assert j1.url == "https://www.janestreet.com/join-jane-street/position/8631912002/"
    assert j1.source == "janestreet"
    assert "Salary: $250,000 - $300,000" in j1.description
    assert "Department: Technology" in j1.description
    assert "Team: Trading Systems" in j1.description
    assert "Type: Full-Time: Experienced" in j1.description
    assert "Build high-performance distributed trading systems in OCaml." in j1.description

    j2 = jobs[1]
    assert j2.id == "jane-street:8631912003"
    assert j2.company == "Jane Street"
    assert j2.title == "Quantitative Researcher"
    assert j2.location == "London, UK"
    assert j2.locations == ["London, UK"]
    assert j2.url == "https://www.janestreet.com/join-jane-street/position/8631912003/"

    j3 = jobs[2]
    assert j3.id == "jane-street:8631912004"
    assert j3.company == "Jane Street"
    assert j3.title == "Trader"
    assert j3.location == "Hong Kong"
    assert j3.locations == ["Hong Kong"]


@responses.activate
def test_fetch_jobs_location_filter() -> None:
    responses.get(JOBS_URL, json=SAMPLE_JOBS)

    scraper = JaneStreetScraper(
        {"name": "Jane Street", "board": "janestreet", "location": "London"}
    )
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].title == "Quantitative Researcher"


@responses.activate
def test_fetch_jobs_network_error() -> None:
    responses.get(JOBS_URL, status=500)

    scraper = JaneStreetScraper(COMPANY)
    jobs = scraper.fetch_jobs()
    assert jobs == []
