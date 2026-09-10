# Amazon Careers API Documentation & Exploration

## Overview

Amazon does not use an off-the-shelf ATS (like Greenhouse, Lever, or Workday) for its public careers experience. Instead, **www.amazon.jobs** is powered by an internal search service backed by an Elasticsearch index:

- **Endpoint:** `GET https://www.amazon.jobs/en/search.json`
- **Authentication:** None required (publicly open)
- **Headers:** `Accept: application/json`, standard `User-Agent`
- **Pagination Model:** `offset` + `result_limit`
  - `result_limit`: maximum `100` per request (values > 100 return an error).
  - `offset`: increments by 100 (`0`, `100`, `200`, ...).
  - Maximum window: Elasticsearch `max_result_window = 10000` (requests at `offset=10000` return `"Cannot return more than 10000 results at once"`).

---

## Response Structure

```json
{
  "hits": 10000,
  "jobs": [
    {
      "id_icims": "10535552",
      "id": "10535552",
      "title": "Front-End Engineer II, ECR",
      "company_name": "Amazon.com Services LLC",
      "job_path": "/en/jobs/10535552/front-end-engineer-ii-ecr",
      "location": "US, WA, Seattle",
      "normalized_location": "Seattle, Washington, USA",
      "locations": [
        "{\"normalizedStateName\":\"Washington\",\"normalizedCountryCode\":\"USA\",\"city\":\"Seattle\",\"countryIso3a\":\"USA\",\"countryIso2a\":\"US\",\"locationNonStemming\":\"United States, WA, Seattle\",\"coordinates\":\"47.60357,-122.32945\",\"normalizedCountyName\":\"King\",\"type\":\"ONSITE\",\"normalizedCountryName\":\"United States\",\"normalizedLocation\":\"Seattle, Washington, USA\",\"location\":\"US, WA, Seattle\",\"region\":\"WA\",\"buildingCodeList\":[\"SEA42\"],\"normalizedCityName\":\"Seattle\"}"
      ],
      "city": "Seattle",
      "state": "WA",
      "country_code": "USA",
      "posted_date": "September  9, 2026",
      "updated_time": "about 2 hours",
      "description": "<p>Job overview...</p>",
      "basic_qualifications": "- 3+ years of experience...",
      "preferred_qualifications": "- Experience with AWS...",
      "business_category": "amazon-web-services",
      "job_category": "Software Development"
    }
  ],
  "facets": {}
}
```

---

## Key Fields Mapping

| Field | Type | Description | Mapping to `Job` |
| :--- | :--- | :--- | :--- |
| `id_icims` / `id` | `string` / `int` | Stable internal unique requisition identifier | `id = f"{slug}:{id_icims}"` |
| `title` | `string` | Role title | `title = raw["title"].strip()` |
| `normalized_location` | `string` | Standardized `"City, State/Province, Country"` | Primary `location` |
| `locations` | `list[str]` | List of serialized JSON strings for each approved work site | Deserialized into `locations[]` |
| `job_path` | `string` | Relative path to posting, e.g. `/en/jobs/10535552/...` | `url = f"https://www.amazon.jobs{job_path}"` |
| `posted_date` | `string` | Human-readable date, e.g. `"September  9, 2026"` | Parsed into `posted_days` and `posted_on` |
| `description` | `string` | Full HTML role description | Cleaned via `html_to_text()` |
| `basic_qualifications` | `string` | HTML list of minimum requirements | Appended to description body |
| `preferred_qualifications`| `string` | HTML list of desired skills | Appended to description body |

---

## Query Parameters & Filters

The search endpoint supports granular filtering via URL query parameters:

- **Sort Order:** `sort=recent` (orders by newest postings first).
- **Country Filter:** `country[]=USA` or `country[]=CAN` (ISO 3-letter or common codes).
- **Career / Category:** `category[]=software-development`, `category[]=operations-it-support-engineering`.
- **Business Line:** `business_category[]=amazon-web-services`, `business_category[]=alexa-and-amazon-devices`, `business_category[]=fulfillment-ops`.
- **Schedule Type:** `schedule_type_id[]=Full-Time`, `schedule_type_id[]=Part-Time`.
- **Facets Request:** `facets[]=category&facets[]=business_category&facets[]=country` returns facet bucket counts in `facets`.
