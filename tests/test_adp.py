import json
from datetime import UTC, datetime, timedelta

import responses

from scraper.boards.adp import AdpScraper
from scraper.config_types import AdpConfig

COMPANY: AdpConfig = {
    "name": "Midland Manufacturing",
    "board": "adp",
    "cid": "c020d588-4c90-4824-8ba6-b08e2fce13ec",
    "cc_id": "19000101_000001",
}
API_URL = "https://workforcenow.adp.com/mascsr/default/careercenter/public/static/v1/reqs"


@responses.activate
def test_maps_adp_requisitions() -> None:
    posted = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    mock_data = {
        "jobRequisitions": [
            {
                "itemID": "19000101_000001_88899",
                "requisitionTitle": "Senior Mechanical Engineer",
                "postDate": posted,
                "requisitionDescription": "<p>Design high precision components.</p>",
                "requisitionLocations": [
                    {
                        "nameCode": {"shortName": "Detroit, MI, US"},
                        "address": {
                            "cityName": "Detroit",
                            "countrySubdivisionLevel1": {"codeValue": "MI"},
                            "countryCode": "US",
                        },
                    }
                ],
            },
            {
                "itemID": "19000101_000001_88900",
                "requisitionTitle": "Operations Associate",
                "postDate": posted,
                "requisitionLocations": [
                    {
                        "address": {
                            "cityName": "Chicago",
                            "countrySubdivisionLevel1": {"codeValue": "IL"},
                            "countryCode": "US",
                        }
                    }
                ],
            },
        ],
        "meta": {"totalNumber": 2},
    }

    responses.get(
        f"{API_URL}?cid=c020d588-4c90-4824-8ba6-b08e2fce13ec&ccId=19000101_000001&lang=en_US",
        body=json.dumps(mock_data),
        content_type="application/json",
    )

    jobs = AdpScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 2
    j1 = jobs[0]
    assert j1.id == "midland-manufacturing:19000101_000001_88899"
    assert j1.company == "Midland Manufacturing"
    assert j1.title == "Senior Mechanical Engineer"
    assert j1.location == "Detroit, MI, US"
    assert j1.locations == ["Detroit, MI, US"]
    assert j1.posted_days == 1
    assert j1.posted_on == "Yesterday"
    assert "Design high precision components." in j1.description
    assert j1.source == "adp"

    j2 = jobs[1]
    assert j2.id == "midland-manufacturing:19000101_000001_88900"
    assert j2.location == "Chicago, IL, US"


@responses.activate
def test_handles_empty_adp_response() -> None:
    responses.get(
        f"{API_URL}?cid=c020d588-4c90-4824-8ba6-b08e2fce13ec&ccId=19000101_000001&lang=en_US",
        body=json.dumps({"jobRequisitions": []}),
        content_type="application/json",
    )

    jobs = AdpScraper(COMPANY).fetch_jobs()
    assert jobs == []
