import responses

from scraper.boards.idc_career_centre import FEED_URL, IdcCareerCentreScraper
from scraper.config_types import IdcCareerCentreConfig

COMPANY: IdcCareerCentreConfig = {
    "name": "IDC Career Centre",
    "board": "idc_career_centre",
}

_FEED_XML = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"
	xmlns:content="http://purl.org/rss/1.0/modules/content/"
	xmlns:job_listing="https://idcanada.org"
>
<channel>
<item>
	<title>Intermediate Interior Designer</title>
	<link>https://idcanada.org/job/intermediate-interior-designer-10/</link>
	<pubDate>Thu, 20 Aug 2026 21:07:14 +0000</pubDate>
	<guid isPermaLink="false">https://idcanada.org/?post_type=job_listing&#038;p=24915</guid>
	<description><![CDATA[Short excerpt&#8230;]]></description>
	<content:encoded><![CDATA[<p><strong>PARTISANS</strong> is looking for an Intermediate Interior Designer.</p>]]></content:encoded>
	<job_listing:company><![CDATA[PARTISANS]]></job_listing:company>
	<job_listing:location><![CDATA[Toronto]]></job_listing:location>
	<job_listing:job_type><![CDATA[Full Time]]></job_listing:job_type>
</item>
<item>
	<title>A&#038;D Product Consultant (Sales)</title>
	<link>https://idcanada.org/job/ad-product-consultant-sales/</link>
	<pubDate>Sun, 15 Aug 2026 12:00:00 +0000</pubDate>
	<guid isPermaLink="false">https://idcanada.org/?post_type=job_listing&#038;p=24967</guid>
	<content:encoded><![CDATA[<p>Division9 is hiring.</p>]]></content:encoded>
	<job_listing:company><![CDATA[Division9]]></job_listing:company>
	<job_listing:location><![CDATA[Vancouver, BC]]></job_listing:location>
</item>
</channel>
</rss>
"""


@responses.activate
def test_extracts_and_maps_postings() -> None:
    responses.get(FEED_URL, body=_FEED_XML)

    jobs = IdcCareerCentreScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 2
    job = jobs[0]
    assert job.id == "idc-career-centre:24915"
    assert job.title == "Intermediate Interior Designer"
    assert job.company == "PARTISANS"
    assert job.location == "Toronto"
    assert job.url == "https://idcanada.org/job/intermediate-interior-designer-10/"
    assert job.source == "idc_career_centre"
    assert "Intermediate Interior Designer" in job.description
    assert job.posted_days is not None


@responses.activate
def test_decodes_html_entity_in_title() -> None:
    responses.get(FEED_URL, body=_FEED_XML)

    jobs = IdcCareerCentreScraper(COMPANY).fetch_jobs()

    assert jobs[1].title == "A&D Product Consultant (Sales)"


@responses.activate
def test_falls_back_to_board_name_when_company_missing() -> None:
    xml = _FEED_XML.replace("<job_listing:company><![CDATA[Division9]]></job_listing:company>", "")
    responses.get(FEED_URL, body=xml)

    jobs = IdcCareerCentreScraper(COMPANY).fetch_jobs()

    assert jobs[1].company == "IDC Career Centre"


@responses.activate
def test_skips_items_without_a_guid_id() -> None:
    xml = _FEED_XML.replace(
        '<guid isPermaLink="false">https://idcanada.org/?post_type=job_listing&#038;p=24967</guid>',
        '<guid isPermaLink="false">https://idcanada.org/malformed</guid>',
    )
    responses.get(FEED_URL, body=xml)

    jobs = IdcCareerCentreScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
