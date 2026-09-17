import responses

from scraper.boards.successfactors import SuccessFactorsScraper
from scraper.config_types import SuccessFactorsConfig

COMPANY: SuccessFactorsConfig = {
    "name": "Global SAP Co",
    "board": "successfactors",
    "company": "globalsap",
    "domain": "jobs.globalsap.com",
}
FEED_URL = "https://jobs.globalsap.com/services/rss/job/?locale=en_US&rows=2000"

XML_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Global SAP Careers</title>
    <link>https://jobs.globalsap.com</link>
    <description>Job Opportunities</description>
    <item>
      <title><![CDATA[Lead Infrastructure Engineer]]></title>
      <link>https://jobs.globalsap.com/job/Seattle-Lead-Infrastructure-Engineer-WA-98101/900123/</link>
      <guid>https://jobs.globalsap.com/job/Seattle-Lead-Infrastructure-Engineer-WA-98101/900123/</guid>
      <pubDate>Mon, 02 Mar 2026 12:00:00 GMT</pubDate>
      <description><![CDATA[<p>Responsible for enterprise <strong>cloud infrastructure</strong>.</p>]]></description>
      <category><![CDATA[Information Technology]]></category>
      <location><![CDATA[Seattle, WA]]></location>
    </item>
    <item>
      <title>Marketing Specialist</title>
      <link>https://jobs.globalsap.com/job/Boston-Marketing-Specialist-MA-02108/900124/</link>
      <guid>900124</guid>
      <description>Drive marketing campaigns.</description>
      <category>Marketing</category>
    </item>
    <item>
      <title>Channel Manager (Shanghai, CN)</title>
      <link>https://jobs.globalsap.com/job/Shanghai-Channel-Manager/1408073900/?feedId=null&amp;utm_source=J2WRSS</link>
      <guid>https://jobs.globalsap.com/job/Shanghai-Channel-Manager/1408073900/?feedId=null&amp;utm_source=J2WRSS</guid>
      <description>Manage regional channels.</description>
    </item>
  </channel>
</rss>
"""


@responses.activate
def test_maps_successfactors_rss_jobs() -> None:
    responses.get(FEED_URL, body=XML_FEED, content_type="application/rss+xml")

    jobs = SuccessFactorsScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 3
    j1 = jobs[0]
    assert j1.id == "global-sap-co:900123"
    assert j1.company == "Global SAP Co"
    assert j1.title == "Lead Infrastructure Engineer"
    assert j1.location == "Seattle, WA"
    assert j1.locations == ["Seattle, WA"]
    assert (
        j1.url
        == "https://jobs.globalsap.com/job/Seattle-Lead-Infrastructure-Engineer-WA-98101/900123/"
    )
    assert "Responsible for enterprise cloud infrastructure." in j1.description
    assert j1.source == "successfactors"
    assert j1.posted_days is not None

    j2 = jobs[1]
    assert j2.id == "global-sap-co:900124"
    assert j2.title == "Marketing Specialist"
    assert j2.location == "Marketing"

    j3 = jobs[2]
    assert j3.id == "global-sap-co:1408073900"
    assert j3.title == "Channel Manager"
    assert j3.location == "Shanghai, CN"


@responses.activate
def test_custom_rows_parameter() -> None:
    custom_company: SuccessFactorsConfig = {
        "name": "Custom SAP Co",
        "board": "successfactors",
        "company": "customsap",
        "domain": "jobs.customsap.com",
        "rows": 500,
    }
    custom_url = "https://jobs.customsap.com/services/rss/job/?locale=en_US&rows=500"
    responses.get(custom_url, body=XML_FEED, content_type="application/rss+xml")

    jobs = SuccessFactorsScraper(custom_company).fetch_jobs()
    assert len(jobs) == 3


@responses.activate
def test_handles_malformed_xml() -> None:
    responses.get(FEED_URL, body="<malformed><<>>", content_type="application/xml")

    jobs = SuccessFactorsScraper(COMPANY).fetch_jobs()
    assert jobs == []
