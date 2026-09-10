# IBM Careers API Documentation & Exploration

## Overview

IBM does not use a standard commercial Applicant Tracking System (such as Greenhouse, Lever, Workday, or Ashby) for its career portal. Instead, **www.ibm.com/careers/search** is backed by an internal Elasticsearch search service called **Genesis**:

- **Endpoint:** `POST https://www-api.ibm.com/search/api/v2`
- **Authentication:** None required (public API)
- **Required Headers:**
  - `Content-Type: application/json`
  - `Referer: https://www.ibm.com/`
  - `Accept: application/json, text/plain, */*`
- **Language / Locale:** Defaults to `"lang": "en"` (or `"lang": "zz"` for language-agnostic search)
- **Index:** `genesis-prod-*`

---

## Discovered Field Catalog

The Elasticsearch document uses custom field names with strict schema validation. Requesting unmapped fields in `_source` or `aggs` causes an API validation error (`Invalid value`).

| Field Name | Type | Description | Example Values |
| :--- | :--- | :--- | :--- |
| `_id` | `string` | Unique SHA-256 hash generated per posting | `"0f4831b26e3dd9abad68616071fe49863039..."` |
| `field_text_01` | `int` / `string` | Numeric internal Job ID used in careers portal URLs | `129622` |
| `title` | `string` | Official job title | `"Senior Software Engineer - Cloud"` |
| `url` | `string` | Canonical direct URL to job detail page | `"https://careers.ibm.com/careers/JobDetail?jobId=129622"` |
| `description` | `string` | Full job description text / HTML body | `"The IBM Sales Accelerator Program..."` |
| `language` | `string` | Language code of the posting | `"en"`, `"fr"`, `"ja"` |
| `field_keyword_05` | `keyword` | **Country** | `"United States"`, `"India"`, `"Canada"`, `"United Kingdom"`, `"Germany"`, `"Switzerland"`, `"Japan"`, `"Australia"`, etc. (40+ countries) |
| `field_keyword_08` | `keyword` | **Career Area / Job Category** | `"Software Engineering"`, `"Data & Analytics"`, `"Consulting"`, `"Enterprise Operations"`, `"Infrastructure & Technology"`, `"Cloud"`, `"Security"`, `"Sales"`, `"Research"`, `"Design & UX"`, `"Product Management"`, `"Project Management"` |
| `field_keyword_17` | `keyword` | **Workplace Type** | `"Hybrid"`, `"Remote"`, or empty (On-site/unspecified) |
| `field_keyword_18` | `keyword` | **Experience Level** | `"Professional"`, `"Internship"`, `"Entry Level"` |
| `field_keyword_19` | `keyword` | **Location String (City, State/Country)** | `"Austin, US"`, `"Toronto, CA"`, `"Zurich, CH"`, `"Bangalore, IN"`, `"Multiple Cities"` |
| `field_keyword_20` | `keyword` | **Legal Entity / Subsidiary** | `"(0147) International Business Machines Corporation"`, `"(0026) IBM Canada Limited"`, `"(0063) IBM India Private Limited"`, etc. |
| `pageviews` | `int` | Document page view count (used for sorting) | `0`, `124` |
| `_score` | `float` | Elasticsearch relevance score | `1.0` |

> Note: When `field_keyword_19` is set to `"Multiple Cities"`, `field_keyword_05` still contains the specific country (e.g. `"United States"` or `"Canada"`). This makes `field_keyword_05` valuable for country-level geolocation resolution.

---

## Querying and Filtering Mechanisms

The API accepts full Elasticsearch Query DSL. Filters can be applied either within `query.bool.must` (which affects score calculations and facet counts) or within `post_filter` (which filters search hits without altering aggregation counts).

### 1. Filtering by Work Type (`field_keyword_17`)
To retrieve only remote roles:
```json
{
  "term": { "field_keyword_17": "Remote" }
}
```
Or for hybrid:
```json
{
  "term": { "field_keyword_17": "Hybrid" }
}
```

### 2. Filtering by Country (`field_keyword_05`)
Single country:
```json
{
  "term": { "field_keyword_05": "United States" }
}
```
Multiple countries:
```json
{
  "terms": { "field_keyword_05": ["United States", "Canada"] }
}
```

### 3. Filtering by Career Area (`field_keyword_08`)
```json
{
  "term": { "field_keyword_08": "Software Engineering" }
}
```

### 4. Filtering by Experience Level (`field_keyword_18`)
```json
{
  "term": { "field_keyword_18": "Entry Level" }
}
```

### 5. Full-Text Search on Title or Description
```json
{
  "match": { "title": "Kubernetes" }
}
```
Or combining multiple criteria in a boolean query:
```json
{
  "query": {
    "bool": {
      "must": [
        { "term": { "field_keyword_05": "United States" } },
        { "term": { "field_keyword_08": "Software Engineering" } },
        { "term": { "field_keyword_17": "Remote" } },
        { "match": { "title": "Staff" } }
      ]
    }
  }
}
```

---

## Aggregations (Facets)

The IBM careers portal retrieves live facet counts using Elasticsearch aggregations. The following aggregations are validated by the backend:

```json
{
  "aggs": {
    "work_types": {
      "terms": { "field": "field_keyword_17", "size": 10 }
    },
    "categories": {
      "terms": { "field": "field_keyword_08", "size": 25 }
    },
    "levels": {
      "terms": { "field": "field_keyword_18", "size": 10 }
    },
    "countries": {
      "terms": { "field": "field_keyword_05", "size": 100 }
    },
    "locations": {
      "terms": { "field": "field_keyword_19", "size": 50 }
    }
  }
}
```

---

## Complete Request Example

Below is a complete payload illustrating pagination, multi-field filtering, field selection (`_source`), and sorting:

```json
{
  "appId": "careers",
  "scopes": ["careers2"],
  "query": {
    "bool": {
      "must": [
        { "terms": { "field_keyword_05": ["United States", "Canada"] } },
        { "term": { "field_keyword_08": "Software Engineering" } },
        { "term": { "field_keyword_17": "Remote" } }
      ]
    }
  },
  "size": 100,
  "from": 0,
  "sort": [
    { "_score": "desc" },
    { "pageviews": "desc" }
  ],
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
    "field_keyword_20"
  ]
}
```

---

## Pagination Guidelines

- **Safety Cap:** The API returns `hits.total.value` with the total number of matched jobs.
- **`size`:** Up to 100 results per request.
- **`from`:** `page * size` (e.g. `0`, `100`, `200`, ...).
- **Termination:** Stop when `offset + len(hits) >= hits.total.value` or when `hits` is empty.
