import responses

from scraper.boards.gc_jobs import (
    BASE_URL,
    POSTER_URL,
    GCJobsScraper,
)
from scraper.config_types import GCJobsConfig

COMPANY: GCJobsConfig = {"name": "Government of Canada", "board": "gc_jobs"}

SAMPLE_PAGE_1 = """
<ul class="searchResultTab">
    <li class="searchResultTabSelected">
        <a class="searchJobTabAnchor" href="page2440?tab=1&amp;tabKeepCriteria=1">Jobs open to the public (2)</a>
    </li>
</ul>
<div id="results">
    <li class="searchResult">
        <div>
            <strong>
                <a href="/psrs-srfp/applicant/page1800?poster=2459537">Administrative and Operational Support</a>
            </strong>
        </div>
        <div class="tableTable">
            <div class="tableRow">
                <div class="tableCell">
                    Closing date: 2026-09-11
                    <br />
                    Royal Canadian Mounted Police
                    <br />
                    Calgary (Alberta), Edmonton (Alberta)
                </div>
                <div class="tableCell">
                    English essential
                    <br />
                    $57,217 to $61,761
                </div>
            </div>
        </div>
        <hr class="searchJobHrLine" />
    </li>
    <li class="searchResult">
        <div>
            <strong>
                <a href="/psrs-srfp/applicant/page1800?poster=2458193">Head Lifeguard</a>
            </strong>
        </div>
        <div class="tableTable">
            <div class="tableRow">
                <div class="tableCell">
                    Closing date: 2026-09-15
                    <br />
                    Parks Canada
                    <br />
                    - Lake Louise, Yoho &amp; Kootenay Field Unit – Visitor Experience
                    <br />
                    Radium Hot Springs (British Columbia)
                </div>
                <div class="tableCell">
                    Bilingual - imperative
                    <br />
                    $30.66 to $33.28 per hour
                </div>
            </div>
        </div>
        <hr class="searchJobHrLine" />
    </li>
</div>
"""

SAMPLE_PAGE_2 = """
<div id="results">
    <li class="searchResult">
        <div>
            <strong>
                <a href="/psrs-srfp/applicant/page1800?poster=2457408">Business Development Officer</a>
            </strong>
        </div>
        <div class="tableTable">
            <div class="tableRow">
                <div class="tableCell">
                    Closing date: 2026-09-20
                    <br />
                    National Research Council Canada
                    <br />
                    Montréal Island (Québec)
                </div>
                <div class="tableCell">
                    Bilingual - imperative
                    <br />
                    $83,985 to $168,192
                </div>
            </div>
        </div>
        <hr class="searchJobHrLine" />
    </li>
</div>
"""

SAMPLE_DETAIL = """
<!DOCTYPE html>
<html>
<body>
<main>
    <h1>Administrative and Operational Support</h1>
    <h2>Royal Canadian Mounted Police</h2>
    <p>Perform administrative and clerical duties supporting RCMP detachment operations in Alberta.</p>
</main>
</body>
</html>
"""


def _mock_session_handshake(page1_body: str = SAMPLE_PAGE_1) -> None:
    responses.get(f"{BASE_URL}?toggleLanguage=en", body="<html>session init</html>", status=200)
    responses.get(
        f"{BASE_URL}?toggleLanguage=en&ajaxSetInternalAccess=1",
        json={"hasAccess": [False]},
        status=200,
    )
    responses.get(
        f"{BASE_URL}?toggleLanguage=en&isSecondPartOfPage=1&isInitialNetworkCheck=1",
        body=page1_body,
        status=200,
    )


def test_init_accepts_settings_and_previous() -> None:
    """Regression test: scrape_one (scraper/main.py) always calls
    scraper_cls(company_cfg, settings, previous=scraper_previous) — a
    subclass __init__ that only accepts `company` raises TypeError here,
    caught by scrape_one's broad except and silently logged as an ordinary
    scrape failure (zero jobs, every run). Confirms this scraper's __init__
    matches BaseScraper's real signature."""
    scraper = GCJobsScraper(COMPANY, {}, previous={})
    assert scraper.settings == {}
    assert scraper.previous == {}


@responses.activate
def test_fetch_jobs_success() -> None:
    _mock_session_handshake()

    scraper = GCJobsScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 2

    j1 = jobs[0]
    assert j1.id == "government-of-canada:2459537"
    assert j1.company == "Royal Canadian Mounted Police"
    assert j1.company_group == "Government of Canada"
    assert j1.title == "Administrative and Operational Support"
    assert j1.location == "Calgary (Alberta)"
    assert j1.locations == ["Calgary (Alberta)", "Edmonton (Alberta)"]
    assert j1.url == f"{POSTER_URL}?poster=2459537&toggleLanguage=en"
    assert j1.posted_on == "Closing: 2026-09-11"
    assert j1.source == "gc_jobs"
    assert "Department: Royal Canadian Mounted Police" in j1.description
    assert "Salary: $57,217 to $61,761" in j1.description
    assert "Language: English essential" in j1.description

    j2 = jobs[1]
    assert j2.id == "government-of-canada:2458193"
    assert (
        j2.company == "Parks Canada - Lake Louise, Yoho & Kootenay Field Unit – Visitor Experience"
    )
    assert j2.company_group == "Government of Canada"
    assert j2.title == "Head Lifeguard"
    assert j2.location == "Radium Hot Springs (British Columbia)"
    assert j2.locations == ["Radium Hot Springs (British Columbia)"]
    assert j2.posted_on == "Closing: 2026-09-15"
    assert "Salary: $30.66 to $33.28 per hour" in j2.description


@responses.activate
def test_fetch_jobs_pagination() -> None:
    page1_with_more = """
    <ul class="searchResultTab">
        <li class="searchResultTabSelected">
            <a class="searchJobTabAnchor">Jobs open to the public (25)</a>
        </li>
    </ul>
    <li class="searchResult">
        <div><strong><a href="/psrs-srfp/applicant/page1800?poster=2459537">Job 1</a></strong></div>
        <div class="tableTable"><div class="tableRow">
            <div class="tableCell">RCMP<br />Ottawa (Ontario)</div>
            <div class="tableCell">$50,000</div>
        </div></div>
    </li>
    """
    _mock_session_handshake(page1_body=page1_with_more)
    responses.get(
        f"{BASE_URL}?requestedPage=2&tab=1&log=false&isSecondPartOfPage=1",
        body=SAMPLE_PAGE_2,
        status=200,
    )

    scraper = GCJobsScraper({"name": "Government of Canada", "board": "gc_jobs", "max_pages": 2})
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 2
    assert jobs[0].title == "Job 1"
    assert jobs[1].title == "Business Development Officer"
    assert jobs[1].company == "National Research Council Canada"


@responses.activate
def test_fetch_jobs_filters() -> None:
    _mock_session_handshake()

    # Test department filter
    scraper_dept = GCJobsScraper(
        {"name": "Government of Canada", "board": "gc_jobs", "department": "Parks Canada"}
    )
    jobs_dept = scraper_dept.fetch_jobs()
    assert len(jobs_dept) == 1
    assert jobs_dept[0].title == "Head Lifeguard"

    # Test location filter
    scraper_loc = GCJobsScraper(
        {"name": "Government of Canada", "board": "gc_jobs", "location": "Calgary"}
    )
    jobs_loc = scraper_loc.fetch_jobs()
    assert len(jobs_loc) == 1
    assert jobs_loc[0].title == "Administrative and Operational Support"

    # Test title filter
    scraper_title = GCJobsScraper(
        {"name": "Government of Canada", "board": "gc_jobs", "title": "lifeguard"}
    )
    jobs_title = scraper_title.fetch_jobs()
    assert len(jobs_title) == 1
    assert jobs_title[0].title == "Head Lifeguard"


@responses.activate
def test_fetch_jobs_with_details() -> None:
    _mock_session_handshake()
    responses.get(
        f"{POSTER_URL}?poster=2459537&toggleLanguage=en",
        body=SAMPLE_DETAIL,
        status=200,
    )
    responses.get(
        f"{POSTER_URL}?poster=2458193&toggleLanguage=en",
        body="<main><p>Parks Canada detail body</p></main>",
        status=200,
    )

    scraper = GCJobsScraper(
        {"name": "Government of Canada", "board": "gc_jobs", "fetch_details": True}
    )
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 2
    assert "Perform administrative and clerical duties" in jobs[0].description
    assert "Parks Canada detail body" in jobs[1].description


@responses.activate
def test_fetch_jobs_network_error() -> None:
    responses.get(f"{BASE_URL}?toggleLanguage=en", status=500)

    scraper = GCJobsScraper(COMPANY)
    jobs = scraper.fetch_jobs()
    assert jobs == []
