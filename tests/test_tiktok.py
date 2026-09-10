import json
from typing import cast

import responses
from requests import PreparedRequest

from scraper.boards.tiktok import (
    SEARCH_URL,
    TikTokCityInfo,
    TikTokJobPost,
    TikTokNamedEntity,
    TikTokScraper,
    _format_location,
)
from scraper.config_types import TikTokConfig

COMPANY: TikTokConfig = {"name": "TikTok", "board": "tiktok"}


def _mock_job(
    post_id: str = "7669925556293601541",
    title: str = "Software Engineer - Recommendations",
    desc: str = "We build state-of-the-art recommendation systems.",
    req: str = "BS/MS in Computer Science or related field.",
    city: str = "San Jose",
    state: str = "California",
    country: str = "United States of America",
) -> TikTokJobPost:
    return TikTokJobPost(
        id=post_id,
        code="A1001",
        title=title,
        description=desc,
        requirement=req,
        recruit_type=TikTokNamedEntity(en_name="Regular"),
        job_category=TikTokNamedEntity(en_name="R&D"),
        city_info=TikTokCityInfo(
            en_name=city,
            parent=TikTokCityInfo(
                en_name=state,
                parent=TikTokCityInfo(
                    en_name=country,
                    parent=None,
                ),
            ),
        ),
    )


@responses.activate
def test_fetches_jobs_successfully():
    job1 = _mock_job(post_id="101", title="Backend Engineer")
    job2 = _mock_job(
        post_id="102",
        title="Frontend Engineer",
        city="London",
        state="England",
        country="United Kingdom",
    )

    mock_resp = {
        "code": 0,
        "message": "success",
        "data": {
            "count": 2,
            "job_post_list": [job1, job2],
        },
    }

    responses.add(
        responses.POST,
        SEARCH_URL,
        json=mock_resp,
        status=200,
    )

    scraper = TikTokScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 2
    assert jobs[0].id == "tiktok:101"
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].company == "TikTok"
    assert jobs[0].source == "tiktok"
    assert jobs[0].location == "San Jose, California, United States of America"
    assert jobs[0].locations == ["San Jose, California, United States of America"]
    assert jobs[0].url == "https://lifeattiktok.com/position/101"
    assert "We build state-of-the-art" in jobs[0].description
    assert "BS/MS in Computer Science" in jobs[0].description

    assert jobs[1].id == "tiktok:102"
    assert jobs[1].location == "London, England, United Kingdom"


@responses.activate
def test_pagination():
    page1_jobs = [_mock_job(post_id=f"id_{i}") for i in range(100)]
    page2_jobs = [_mock_job(post_id="id_101")]

    empty_headers: dict[str, str] = {}

    def request_callback(request: PreparedRequest) -> tuple[int, dict[str, str], str]:
        body_bytes = request.body if isinstance(request.body, (str, bytes, bytearray)) else "{}"
        body_obj: object = json.loads(body_bytes)
        body: dict[str, object] = (
            cast(dict[str, object], body_obj) if isinstance(body_obj, dict) else {}
        )
        offset = body.get("offset", 0)
        if offset == 0:
            return (
                200,
                empty_headers,
                json.dumps({"code": 0, "data": {"count": 101, "job_post_list": page1_jobs}}),
            )
        elif offset == 100:
            return (
                200,
                empty_headers,
                json.dumps({"code": 0, "data": {"count": 101, "job_post_list": page2_jobs}}),
            )
        return (
            200,
            empty_headers,
            json.dumps({"code": 0, "data": {"count": 101, "job_post_list": []}}),
        )

    responses.add_callback(
        responses.POST,
        SEARCH_URL,
        callback=request_callback,
        content_type="application/json",
    )

    scraper = TikTokScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 101
    assert jobs[0].id == "tiktok:id_0"
    assert jobs[100].id == "tiktok:id_101"


@responses.activate
def test_handles_missing_fields_and_empty_id():
    bad_job = TikTokJobPost(id="", title="Missing ID")
    no_loc_job = TikTokJobPost(
        id="999", title="Remote Worker", city_info=None, description="work from anywhere"
    )

    responses.add(
        responses.POST,
        SEARCH_URL,
        json={"code": 0, "data": {"count": 2, "job_post_list": [bad_job, no_loc_job]}},
        status=200,
    )

    scraper = TikTokScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].id == "tiktok:999"
    assert jobs[0].location == "Remote"
    assert jobs[0].locations == ["Remote"]


@responses.activate
def test_handles_api_error_code():
    responses.add(
        responses.POST,
        SEARCH_URL,
        json={"code": 10001, "message": "Internal gateway error", "data": None},
        status=200,
    )

    scraper = TikTokScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert jobs == []


@responses.activate
def test_max_pages_config():
    responses.add(
        responses.POST,
        SEARCH_URL,
        json={"code": 0, "data": {"count": 500, "job_post_list": [_mock_job(post_id="p1")]}},
        status=200,
    )

    cfg: TikTokConfig = {"name": "TikTok", "board": "tiktok", "max_pages": 1}
    scraper = TikTokScraper(cfg)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 1
    assert len(responses.calls) == 1


def test_format_location():
    assert _format_location(None) == "Remote"
    ci = TikTokCityInfo(
        en_name="Seattle",
        parent=TikTokCityInfo(
            en_name="Washington",
            parent=TikTokCityInfo(en_name="United States of America"),
        ),
    )
    assert _format_location(ci) == "Seattle, Washington, United States of America"
