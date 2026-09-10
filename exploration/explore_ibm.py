"""EXPLORATION ONLY — not the real scraper. Probes the IBM Careers Elasticsearch API.

Run:
    python exploration/explore_ibm.py
    python exploration/explore_ibm.py --country "United States" --remote
    python exploration/explore_ibm.py --category "Software Engineering"

Endpoint:
    POST https://www-api.ibm.com/search/api/v2
    Headers:
      Content-Type: application/json
      Referer: https://www.ibm.com/
      Accept: application/json, text/plain, */*

Documentation:
    See exploration/ibm_api.md for full field mappings and Elasticsearch query schemas.
"""

from __future__ import annotations

import argparse

import requests

API = "https://www-api.ibm.com/search/api/v2"
HEADERS = {
    "Content-Type": "application/json",
    "Referer": "https://www.ibm.com/",
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0",
}


def probe(
    country: str | None = None,
    category: str | None = None,
    remote: bool = False,
    query_text: str | None = None,
    limit: int = 5,
) -> None:
    must_clauses: list[dict] = []
    if country:
        must_clauses.append({"term": {"field_keyword_05": country}})
    if category:
        must_clauses.append({"term": {"field_keyword_08": category}})
    if remote:
        must_clauses.append({"term": {"field_keyword_17": "Remote"}})
    if query_text:
        must_clauses.append({"match": {"title": query_text}})

    payload = {
        "appId": "careers",
        "scopes": ["careers2"],
        "query": {"bool": {"must": must_clauses}},
        "size": limit,
        "from": 0,
        "sort": [{"_score": "desc"}, {"pageviews": "desc"}],
        "lang": "en",
        "_source": [
            "_id",
            "title",
            "url",
            "description",
            "field_text_01",
            "field_keyword_05",
            "field_keyword_08",
            "field_keyword_17",
            "field_keyword_18",
            "field_keyword_19",
            "field_keyword_20",
        ],
        "aggs": {
            "top_categories": {"terms": {"field": "field_keyword_08", "size": 5}},
            "top_countries": {"terms": {"field": "field_keyword_05", "size": 5}},
            "work_types": {"terms": {"field": "field_keyword_17", "size": 5}},
        },
    }

    resp = requests.post(API, headers=HEADERS, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    total = data.get("hits", {}).get("total", {}).get("value", 0)
    hits = data.get("hits", {}).get("hits", [])
    print(f"Total matched jobs: {total}")
    print(f"Showing first {len(hits)} results:\n")

    for i, h in enumerate(hits, 1):
        src = h.get("_source", {})
        print(f"{i}. {src.get('title')}")
        print(f"   Job ID (numeric): {src.get('field_text_01')}")
        print(f"   Location:         {src.get('field_keyword_19')} (Country: {src.get('field_keyword_05')})")
        print(f"   Workplace:        {src.get('field_keyword_17') or 'On-site/Standard'}")
        print(f"   Career Area:      {src.get('field_keyword_08')}")
        print(f"   Level:            {src.get('field_keyword_18')}")
        print(f"   URL:              {src.get('url')}\n")

    aggs = data.get("aggregations", {})
    if aggs:
        print("Facet Aggregations:")
        for name, agg in aggs.items():
            buckets = [f"{b['key']} ({b['doc_count']})" for b in agg.get("buckets", [])]
            print(f"  {name}: {', '.join(buckets)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Probe IBM Careers Elasticsearch API")
    parser.add_argument("--country", help="Filter by country, e.g. 'United States' or 'Canada'")
    parser.add_argument("--category", help="Filter by career area, e.g. 'Software Engineering'")
    parser.add_argument("--remote", action="store_true", help="Filter for remote roles")
    parser.add_argument("--query", dest="query_text", help="Text search on title")
    parser.add_argument("--limit", type=int, default=5, help="Number of jobs to display")
    args = parser.parse_args()

    probe(
        country=args.country,
        category=args.category,
        remote=args.remote,
        query_text=args.query_text,
        limit=args.limit,
    )
