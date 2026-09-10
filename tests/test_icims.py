import responses

from scraper.boards.icims import IcimsScraper
from scraper.config_types import IcimsConfig

COMPANY: IcimsConfig = {
    "name": "Pacific Transit",
    "board": "icims",
    "tenant": "careers-pacifictransit",
}
PAGE0_URL = "https://careers-pacifictransit.icims.com/jobs/search?pr=0&in_iframe=1"
PAGE1_URL = "https://careers-pacifictransit.icims.com/jobs/search?pr=1&in_iframe=1"

HTML_PAGE0 = """
<div class="container-fluid iCIMS_JobsTable">
  <div class="row">
    <div class="col-xs-12 title">
      <a class="iCIMS_Anchor" href="https://careers-pacifictransit.icims.com/jobs/5501/fleet-systems-architect/job">
        <h2>Fleet Systems Architect</h2>
      </a>
    </div>
    <div class="col-xs-12 header">
      <div class="iCIMS_JobHeaderGroup">
        <div class="iCIMS_JobHeaderTag">Location</div>
        <div class="iCIMS_JobHeaderSubTag"><span>Seattle, WA</span></div>
      </div>
      <div class="iCIMS_JobHeaderGroup">
        <div class="iCIMS_JobHeaderTag">Posted Date</div>
        <div class="iCIMS_JobHeaderSubTag"><span>2026-03-01</span></div>
      </div>
    </div>
  </div>
</div>
"""

HTML_PAGE1 = """
<div class="container-fluid iCIMS_JobsTable">
  <div class="row">
    <div class="col-xs-12 empty">No open jobs found.</div>
  </div>
</div>
"""


@responses.activate
def test_maps_icims_html_jobs() -> None:
    responses.get(PAGE0_URL, body=HTML_PAGE0, content_type="text/html")
    responses.get(PAGE1_URL, body=HTML_PAGE1, content_type="text/html")

    jobs = IcimsScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    j = jobs[0]
    assert j.id == "pacific-transit:5501"
    assert j.company == "Pacific Transit"
    assert j.title == "Fleet Systems Architect"
    assert j.location == "Seattle, WA"
    assert j.locations == ["Seattle, WA"]
    assert j.url == "https://careers-pacifictransit.icims.com/jobs/5501/fleet-systems-architect/job"
    assert j.source == "icims"
    assert j.posted_days is not None


@responses.activate
def test_handles_empty_icims_page() -> None:
    responses.get(PAGE0_URL, body=HTML_PAGE1, content_type="text/html")

    jobs = IcimsScraper(COMPANY).fetch_jobs()
    assert jobs == []
