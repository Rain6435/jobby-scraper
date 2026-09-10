import time

import responses

from scraper.boards.microsoft import (
    DETAIL_URL,
    SEARCH_URL,
    MicrosoftDetailData,
    MicrosoftDetailResponse,
    MicrosoftPosition,
    MicrosoftScraper,
    MicrosoftSearchData,
    MicrosoftSearchResponse,
    posted_days_from_epoch,
)
from scraper.config_types import MicrosoftConfig

COMPANY: MicrosoftConfig = {"name": "Microsoft", "board": "microsoft"}


def _position(
    pos_id: int = 1970393556986872,
    name: str = "Critical Environment Program Manager",
    standardized_locations: list[str] | None = None,
    locations: list[str] | None = None,
    posted_ts: int | None = None,
    position_url: str = "/careers/job/1970393556986872",
) -> MicrosoftPosition:
    if posted_ts is None:
        posted_ts = int(time.time()) - 86400  # 1 day ago
    return MicrosoftPosition(
        id=pos_id,
        name=f"  {name}  ",
        standardizedLocations=standardized_locations
        if standardized_locations is not None
        else ["Quincy, WA, US"],
        locations=locations if locations is not None else ["United States, Washington, Quincy"],
        postedTs=posted_ts,
        positionUrl=position_url,
    )


def _search_page(
    positions: list[MicrosoftPosition], count: int | None = None
) -> MicrosoftSearchResponse:
    return MicrosoftSearchResponse(
        status=200,
        data=MicrosoftSearchData(
            count=count if count is not None else len(positions),
            positions=positions,
        ),
    )


def _detail(
    desc: str = "<p>Design next generation datacenter architecture.</p>",
) -> MicrosoftDetailResponse:
    return MicrosoftDetailResponse(
        status=200,
        data=MicrosoftDetailData(jobDescription=desc),
    )


@responses.activate
def test_maps_a_position_with_details() -> None:
    responses.get(SEARCH_URL, json=_search_page([_position()]))
    responses.get(DETAIL_URL, json=_detail())

    jobs = MicrosoftScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    j = jobs[0]
    assert j.id == "microsoft:1970393556986872"
    assert j.company == "Microsoft"
    assert j.title == "Critical Environment Program Manager"
    assert j.location == "Quincy, WA, US"
    assert j.locations == ["Quincy, WA, US"]
    assert j.url == "https://apply.careers.microsoft.com/careers/job/1970393556986872"
    assert j.source == "microsoft"
    assert j.posted_days == 1
    assert j.posted_on == "Yesterday"
    assert "Design next generation datacenter architecture." in j.description


@responses.activate
def test_skips_detail_fetch_when_configured_false() -> None:
    cfg: MicrosoftConfig = {"name": "Microsoft", "board": "microsoft", "fetch_details": False}
    responses.get(SEARCH_URL, json=_search_page([_position()]))

    jobs = MicrosoftScraper(cfg).fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].description == ""
    assert len(responses.calls) == 1  # only search was called


def test_posted_days_from_epoch() -> None:
    now_ts = int(time.time())
    assert posted_days_from_epoch(now_ts) == 0
    assert posted_days_from_epoch(now_ts - 86400 * 3) == 3
    assert posted_days_from_epoch(None) is None


@responses.activate
def test_location_fallbacks() -> None:
    pos = _position(standardized_locations=[], locations=["Redmond, WA"])
    cfg: MicrosoftConfig = {"name": "Microsoft", "board": "microsoft", "fetch_details": False}
    responses.get(SEARCH_URL, json=_search_page([pos]))

    jobs = MicrosoftScraper(cfg).fetch_jobs()

    assert jobs[0].location == "Redmond, WA"
    assert jobs[0].locations == ["Redmond, WA"]


@responses.activate
def test_paginates_until_all_fetched() -> None:
    cfg: MicrosoftConfig = {"name": "Microsoft", "board": "microsoft", "fetch_details": False}
    p1 = _position(pos_id=1)
    p2 = _position(pos_id=2)
    p3 = _position(pos_id=3)

    responses.get(SEARCH_URL, json=_search_page([p1, p2], count=3))
    responses.get(SEARCH_URL, json=_search_page([p3], count=3))

    jobs = MicrosoftScraper(cfg).fetch_jobs()

    assert {j.id for j in jobs} == {"microsoft:1", "microsoft:2", "microsoft:3"}
    assert len(responses.calls) == 2


@responses.activate
def test_passes_filter_parameters() -> None:
    cfg: MicrosoftConfig = {
        "name": "Microsoft",
        "board": "microsoft",
        "location": "Remote",
        "query": "Azure",
        "fetch_details": False,
    }
    responses.get(SEARCH_URL, json=_search_page([_position()]))

    MicrosoftScraper(cfg).fetch_jobs()

    url = responses.calls[0].request.url or ""
    assert "location=Remote" in url
    assert "query=Azure" in url
