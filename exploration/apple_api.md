# Apple Careers API & Hydration Data Exploration

## Overview

Apple's career portal (**jobs.apple.com**) runs a modern React/Remix architecture. Rather than requiring client-side API calls guarded by session handshakes or CSRF tokens, each search page request renders a static HTML response that embeds its entire search state in a global JavaScript object:

- **Search URL:** `GET https://jobs.apple.com/en-us/search?page={page}`
- **Authentication:** None required for public search listings
- **Page Size:** 20 listings per page
- **Hydration Variable:**
  ```javascript
  window.__staticRouterHydrationData = JSON.parse("{\"loaderData\":{\"search\":{...}}}");
  ```
- **Total Volume:** ~6,000+ live jobs globally across hardware, software, machine learning, services, and retail.

---

## Embedded Data Structure

Inside `loaderData.search`:

```json
{
  "totalRecords": 6089,
  "searchResults": [
    {
      "id": "PIPE-114438158",
      "positionId": "114438158",
      "postingTitle": "Machine Learning Engineer - Agentic AI",
      "transformedPostingTitle": "machine-learning-engineer-agentic-ai",
      "jobSummary": "The Machine Learning team is seeking an exceptional engineer...",
      "postingDate": "Sep 09, 2026",
      "postDateInGMT": "2026-09-09T23:52:29.432689422Z",
      "locations": [
        {
          "name": "Cupertino, California, United States",
          "city": "Cupertino",
          "stateProvince": "California",
          "countryName": "United States of America"
        }
      ],
      "team": {
        "teamName": "Machine Learning and AI",
        "teamCode": "MLAI"
      },
      "homeOffice": false
    }
  ]
}
```

---

## Field Reference & Mapping to `Job`

| Field | Type | Description | Mapping to `Job` |
| :--- | :--- | :--- | :--- |
| `positionId` | `string` | Canonical internal requisition ID | `id = f"apple:{positionId}"` |
| `postingTitle` | `string` | Job title | `title = postingTitle.strip()` |
| `transformedPostingTitle` | `string` | URL-friendly title slug | Appended to details URL |
| `locations` | `list[dict]` | Structured location objects with city, province, and country | Deserialized into `locations[]` |
| `postDateInGMT` | `string` | Precise ISO-8601 GMT timestamp | Passed to `posted_days_from_iso()` |
| `jobSummary` | `string` | Plain-text job description overview | `description = jobSummary` |
| Canonical URL | `string` | Direct link to posting | `f"https://jobs.apple.com/en-us/details/{positionId}/{transformedPostingTitle}"` |

---

## Query Parameters & Filters

- `page`: Page index (`1`, `2`, `3`, ...)
- `search`: Keyword search on title/skills (e.g. `search=compiler`)
- `location`: Predefined location key (e.g. `location=united-states-USA`, `location=canada-CAN`)
- `team`: Team code filter (e.g. `team=MLAI`, `team=SFTWR`)
- `sort`: Sorting (`relevance`, `newest`)
