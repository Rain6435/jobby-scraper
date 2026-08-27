import responses

from scraper.boards.cip_planning import FEED_URL, CipPlanningScraper
from scraper.config_types import CipPlanningConfig

COMPANY: CipPlanningConfig = {
    "name": "CIP National Planning Job Board",
    "board": "cip_planning",
}

_FEED_XML = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"
	xmlns:content="http://purl.org/rss/1.0/modules/content/"
	xmlns:job_listing="https://www.cip-icu.ca"
>
<channel>
<item>
	<title>Planner I &#8211; Community Planning</title>
	<link>https://www.cip-icu.ca/job/planner-i-community-planning/</link>
	<pubDate>Sun, 23 Aug 2026 12:00:00 +0000</pubDate>
	<guid isPermaLink="false">https://www.cip-icu.ca/?post_type=job_listing&#038;p=47302</guid>
	<content:encoded><![CDATA[<p>City of Hamilton is hiring a Community Planner.</p>]]></content:encoded>
	<job_listing:company><![CDATA[City of Hamilton]]></job_listing:company>
	<job_listing:location><![CDATA[Hamilton, ON]]></job_listing:location>
</item>
</channel>
</rss>
"""


@responses.activate
def test_extracts_and_maps_postings() -> None:
    responses.get(FEED_URL, body=_FEED_XML)

    jobs = CipPlanningScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "cip-national-planning-job-board:47302"
    assert job.title == "Planner I – Community Planning"
    assert job.company == "City of Hamilton"
    assert job.location == "Hamilton, ON"
    assert job.url == "https://www.cip-icu.ca/job/planner-i-community-planning/"
    assert job.source == "cip_planning"
    assert "Community Planner" in job.description
