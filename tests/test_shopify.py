import responses

from scraper.boards.shopify import (
    CAREERS_URL,
    ShopifyScraper,
    clean_shopify_location,
    parse_shopify_detail,
)
from scraper.config_types import ShopifyConfig

COMPANY: ShopifyConfig = {"name": "Shopify", "board": "shopify", "fetch_details": True}

MOCK_HTML = """
<html>
<body>
    <div class="p-3">
        <a class="group" href="/careers/senior-lead-federal-government-affairs-us_7d3f4fe7-7a8c-4919-b181-74f2f6f3c6d8">
            <h4 class="font-bold text-xl grow">Senior Lead, Federal Government Affairs (US)</h4>
            <div class="flex items-center gap-1 location">
                <span class="text-sm uppercase text-[#1338bf] font-bold">Remote - Americas</span>
            </div>
        </a>
        <a class="group" href="/careers/head-of-merch-programs_11a67059-84b1-406e-a5b9-11e509f3d52c">
            <h4 class="font-bold text-xl grow">Head of Merch Programs</h4>
            <div class="flex items-center gap-1 location">
                <span class="text-sm uppercase text-[#1338bf] font-bold">Remote - Canada</span>
            </div>
        </a>
        <a class="group" href="/careers/developer-relations-lead_22a67059-84b1-406e-a5b9-11e509f3d52d">
            <h4 class="font-bold text-xl grow">Developer Relations Lead</h4>
            <div class="flex items-center gap-1 location">
                <span class="text-sm uppercase text-[#1338bf] font-bold">Toronto</span>
            </div>
        </a>
    </div>
</body>
</html>
"""

MOCK_DETAIL_JSON = [
    "root",
    "title",
    "Senior Lead, Federal Government Affairs (US)",
    "descriptionPlain",
    "Drive federal government affairs for Shopify across North America.",
    "publishedDate",
    "2026-08-10",
]


@responses.activate
def test_fetches_jobs_with_details():
    responses.add(responses.GET, CAREERS_URL, body=MOCK_HTML, status=200)
    for jid in [
        "senior-lead-federal-government-affairs-us_7d3f4fe7-7a8c-4919-b181-74f2f6f3c6d8",
        "head-of-merch-programs_11a67059-84b1-406e-a5b9-11e509f3d52c",
        "developer-relations-lead_22a67059-84b1-406e-a5b9-11e509f3d52d",
    ]:
        responses.add(
            responses.GET,
            f"https://www.shopify.com/careers/{jid}.data",
            json=MOCK_DETAIL_JSON,
            status=200,
        )

    scraper = ShopifyScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 3

    j1 = jobs[0]
    assert j1.id == "shopify:7d3f4fe7-7a8c-4919-b181-74f2f6f3c6d8"
    assert j1.title == "Senior Lead, Federal Government Affairs (US)"
    assert j1.company == "Shopify"
    assert j1.location == "Remote, Americas"
    assert j1.locations == ["Remote, Americas"]
    assert (
        j1.url
        == "https://www.shopify.com/careers/senior-lead-federal-government-affairs-us_7d3f4fe7-7a8c-4919-b181-74f2f6f3c6d8"
    )
    assert j1.source == "shopify"
    assert j1.posted_date == "2026-08-10"
    assert j1.description == "Drive federal government affairs for Shopify across North America."

    j2 = jobs[1]
    assert j2.location == "Remote, Canada"

    j3 = jobs[2]
    assert j3.location == "Toronto"


@responses.activate
def test_skips_detail_fetch_when_disabled():
    responses.add(responses.GET, CAREERS_URL, body=MOCK_HTML, status=200)

    company: ShopifyConfig = {"name": "Shopify", "board": "shopify", "fetch_details": False}
    scraper = ShopifyScraper(company)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 3
    assert jobs[0].description == ""
    assert jobs[0].posted_date is None


@responses.activate
def test_filters_by_location():
    responses.add(responses.GET, CAREERS_URL, body=MOCK_HTML, status=200)

    company: ShopifyConfig = {
        "name": "Shopify",
        "board": "shopify",
        "location": "Canada",
        "fetch_details": False,
    }
    scraper = ShopifyScraper(company)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].id == "shopify:11a67059-84b1-406e-a5b9-11e509f3d52c"


@responses.activate
def test_filters_by_keyword():
    responses.add(responses.GET, CAREERS_URL, body=MOCK_HTML, status=200)

    company: ShopifyConfig = {
        "name": "Shopify",
        "board": "shopify",
        "keyword": "Developer",
        "fetch_details": False,
    }
    scraper = ShopifyScraper(company)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].id == "shopify:22a67059-84b1-406e-a5b9-11e509f3d52d"


def test_clean_shopify_location():
    assert clean_shopify_location("Remote - Canada") == "Remote, Canada"
    assert clean_shopify_location("Remote - Americas") == "Remote, Americas"
    assert clean_shopify_location("Toronto") == "Toronto"
    assert clean_shopify_location("Montreal") == "Montreal"


def test_parse_shopify_detail():
    date, desc = parse_shopify_detail(MOCK_DETAIL_JSON)
    assert date == "2026-08-10"
    assert desc == "Drive federal government affairs for Shopify across North America."
