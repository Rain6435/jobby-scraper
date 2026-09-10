import responses

from scraper.boards.valve import (
    DETAIL_URL,
    LIST_URL,
    ValveScraper,
)
from scraper.config_types import ValveConfig

COMPANY: ValveConfig = {"name": "Valve", "board": "valve"}

SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<body>
<div class="jobs_list">
    <a href="https://www.valvesoftware.com/en/jobs?job_id=2">
        <span>3D Character Artist</span>
    </a>
    <a href="https://www.valvesoftware.com/en/jobs?job_id=85">
        Audio Software Engineer
    </a>
</div>
</body>
</html>
"""

SAMPLE_DETAIL = """
<!DOCTYPE html>
<html>
<body>
<div class="job_description_intro">
    <p>At Valve, audio software engineers push the boundaries of audio tools.</p>
</div>
</body>
</html>
"""


@responses.activate
def test_maps_valve_jobs_with_details() -> None:
    responses.get(LIST_URL, body=SAMPLE_HTML)
    responses.get(DETAIL_URL.format(job_id="2"), body=SAMPLE_DETAIL)
    responses.get(DETAIL_URL.format(job_id="85"), body=SAMPLE_DETAIL)

    jobs = ValveScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 2
    j1 = jobs[0]
    assert j1.id == "valve:2"
    assert j1.company == "Valve"
    assert j1.title == "3D Character Artist"
    assert j1.location == "Bellevue, WA"
    assert j1.locations == ["Bellevue, WA"]
    assert j1.url == "https://www.valvesoftware.com/en/jobs?job_id=2"
    assert j1.source == "valve"
    assert "At Valve, audio software engineers" in j1.description
    assert j1.posted_days is None


@responses.activate
def test_skips_detail_fetch_when_configured() -> None:
    cfg: ValveConfig = {"name": "Valve", "board": "valve", "fetch_details": False}
    responses.get(LIST_URL, body=SAMPLE_HTML)

    jobs = ValveScraper(cfg).fetch_jobs()

    assert len(jobs) == 2
    assert jobs[0].description == ""
    assert len(responses.calls) == 1
