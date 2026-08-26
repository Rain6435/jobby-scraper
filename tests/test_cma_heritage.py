import responses

from scraper.boards.cma_heritage import LIST_URL, CmaHeritageScraper

COMPANY = {"name": "CMA Jobs in Heritage", "board": "cma_heritage"}

_LIST_HTML = """
<div class="row p-2 careerList">
<div class="col-sm-3"><a href="https://museums.ca/company/roster/companyRosterDetails.html?companyId=81598&companyRosterId=87">Conservator</a></div>
<div class="col-sm-3"><a href="https://museums.ca/company/roster/companyRosterDetails.html?companyId=81598&companyRosterId=87">Ingenium, Canada&#39;s Museum</a></div>
<div class="col-sm-2"><a href="https://museums.ca/company/roster/companyRosterDetails.html?companyId=81598&companyRosterId=87">Ottawa ON</a></div>
<div class="col-sm-2"><a href="https://museums.ca/company/roster/companyRosterDetails.html?companyId=81598&companyRosterId=87">Permanent</a></div>
<div class="col-sm-1"><a href="https://museums.ca/company/roster/companyRosterDetails.html?companyId=81598&companyRosterId=87">09/11/2026</a></div>
</div>
<!--ola:rule ruleid="61110"-->
<div class="row p-2 careerList">
<div class="col-sm-3"><a href="https://museums.ca/company/roster/companyRosterDetails.html?companyId=81595&companyRosterId=87">Exhibits &amp; Collection Interpreter</a></div>
<div class="col-sm-3"><a href="https://museums.ca/company/roster/companyRosterDetails.html?companyId=81595&companyRosterId=87">London Children's Museum</a></div>
<div class="col-sm-2"><a href="https://museums.ca/company/roster/companyRosterDetails.html?companyId=81595&companyRosterId=87">100 Kellogg Lane</a></div>
<div class="col-sm-2"><a href="https://museums.ca/company/roster/companyRosterDetails.html?companyId=81595&companyRosterId=87">Contract Full-time</a></div>
<div class="col-sm-1"><a href="https://museums.ca/company/roster/companyRosterDetails.html?companyId=81595&companyRosterId=87">08/30/2026</a></div>
</div>
"""

_DETAIL_HTML = """
<h1>Conservator</h1>
<table style="width: 100%;">
<tbody>
<tr><td><p><strong>LOCATION :</strong></p></td><td><p>Ottawa ON</p></td></tr>
<tr><td><p><strong>SALARY :</strong></p></td><td><p>$60,000</p></td></tr>
</tbody>
</table>
<h1></h1>
"""


def _detail_url(company_id: str) -> str:
    return f"https://museums.ca/company/roster/companyRosterDetails.html?companyId={company_id}&companyRosterId=87"


@responses.activate
def test_extracts_and_maps_postings():
    responses.get(LIST_URL, body=_LIST_HTML)
    responses.get(_detail_url("81598"), body=_DETAIL_HTML)
    responses.get(_detail_url("81595"), body=_DETAIL_HTML)

    jobs = CmaHeritageScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 2
    job = jobs[0]
    assert job.id == "cma-jobs-in-heritage:81598"
    assert job.title == "Conservator"
    assert job.company == "Ingenium, Canada's Museum"
    assert job.location == "Ottawa ON"
    assert job.url == _detail_url("81598")
    assert job.source == "cma_heritage"
    assert job.posted_on == ""
    assert job.posted_days is None
    assert "LOCATION" in job.description
    assert "$60,000" in job.description


@responses.activate
def test_decodes_html_entities_in_title():
    responses.get(LIST_URL, body=_LIST_HTML)
    responses.get(_detail_url("81598"), body=_DETAIL_HTML)
    responses.get(_detail_url("81595"), body=_DETAIL_HTML)

    jobs = CmaHeritageScraper(COMPANY).fetch_jobs()

    assert jobs[1].title == "Exhibits & Collection Interpreter"


@responses.activate
def test_detail_fetch_failure_returns_empty_description_not_a_crash():
    responses.get(LIST_URL, body=_LIST_HTML)
    responses.get(_detail_url("81598"), status=500)
    responses.get(_detail_url("81595"), body=_DETAIL_HTML)

    jobs = CmaHeritageScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 2
    assert jobs[0].description == ""


def test_extract_postings_skips_rows_missing_a_company_id():
    html = """
    <div class="row p-2 careerList">
    <div class="col-sm-3"><a href="https://museums.ca/nope">Untitled</a></div>
    <div class="col-sm-3"><a href="https://museums.ca/nope">Some Org</a></div>
    <div class="col-sm-2"><a href="https://museums.ca/nope">Somewhere</a></div>
    </div>
    """
    postings = CmaHeritageScraper._extract_postings(html)
    assert postings == []
