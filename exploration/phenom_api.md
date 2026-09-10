# Phenom People Career Portal Architecture & API Documentation

## Overview

Phenom People is an enterprise talent experience platform (TXP / ATS frontend) powering career portals for many global and Canadian enterprise companies:
- **OpenText** (Waterloo, ON HQ): `https://careers.opentext.com/us/en`
- **Bell Canada** (Montreal, QC HQ): `https://jobs.bell.ca/ca/en`
- **Air Canada** (Montreal, QC HQ): `https://careers.aircanada.com/ca/en`
- **Cisco** (Major R&D hub in Ottawa/Kanata, ON): `https://careers.cisco.com/global/en`
- Many other Fortune 500 / Global 2000 enterprises.

Phenom uses server-side rendering (SSR) where the full dataset for the current view is serialized into a JavaScript global object: `phApp.ddo` (*Dynamic Data Object*).

---

## 1. Search Results Endpoint

Phenom portals expose a canonical search endpoint at:
```
GET https://{domain}/{locale}/search-results?from={offset}&s=1
```

### URL Normalization
Given a configured company URL (e.g. `https://jobs.bell.ca/ca/en` or `https://jobs.bell.ca/ca/en/search-results`):
- `portal_url`: Base URL without `/search-results` (e.g. `https://jobs.bell.ca/ca/en`)
- `search_url`: Target search results endpoint (e.g. `https://jobs.bell.ca/ca/en/search-results`)

### Pagination
- Page size is fixed at **10 jobs per page** in SSR responses.
- `from=0` (or omitted): Page 1 (offset 0..9)
- `from=10`: Page 2 (offset 10..19)
- `from=20`: Page 3 (offset 20..29)
- `from={p * 10}`: Page `p + 1`
- Parameter `s=1` signals a direct search query execution.

---

## 2. Extracting Data from `phApp.ddo`

Within the HTML response, the payload is defined inside a `<script>` tag:
```html
<script type="text/javascript">
  phApp.ddo = {
    "eagerLoadRefineSearch": {
      "totalHits": 374,
      "data": {
        "jobs": [ ... ]
      }
    },
    ...
  };
</script>
```

### Regular Expression
```python
re.search(r"phApp\.ddo\s*=\s*(\{.*?\});\s*(?:phApp|window|<\/script>)", html, re.DOTALL)
```

### Job Schema Fields in `eagerLoadRefineSearch.data.jobs`
Each item in `jobs` contains:
| Field | Type | Example | Purpose |
|---|---|---|---|
| `jobId` | `str` | `"427797"` | Numeric or alphanumeric job ID |
| `reqId` | `str` | `"427797"` | Requisition identifier |
| `jobSeqNo` | `str` | `"BECACA427797EXTERNALENCA"` | Unique internal Phenom sequence number |
| `title` | `str` | `"Senior Security Architect"` | Clean job title |
| `location` | `str` | `"Montreal, Quebec"` | Primary location |
| `multi_location` | `list[str]` | `["Montreal, Quebec", ...]` | Expanded location list |
| `city` | `str` | `"Montreal"` | City name |
| `state` | `str` | `"Quebec"` | State / Province name |
| `country` | `str` | `"Canada"` or `"CAN"` | Country identifier |
| `category` | `str` | `"Security"` | Functional category |
| `multi_category` | `list[str]` | `["Security", "IT"]` | Categorization list |
| `postedDate` | `str` | `"2026-08-28T00:00:00.000+0000"` | ISO-8601 posting timestamp |
| `descriptionTeaser` | `str` | `"Lead the scoping, design..."` | Concise summary / teaser text |

---

## 3. Canonical Job URLs & Detail Pages

### Canonical Job URL
A direct link to any posting is constructed as:
```
{portal_url}/job/{jobId}
```
If `jobId` is missing, fall back to `jobSeqNo`. Both resolve cleanly and return HTTP 200.

### Optional Detail Fetching (`fetch_details: true`)
Visiting `{portal_url}/job/{jobId}` renders `phApp.ddo` containing:
```json
{
  "jobDetail": {
    "data": {
      "job": {
        "description": "<p>Full job description HTML...</p>"
      }
    }
  }
}
```
Converting `description` via `html_to_text()` provides the complete job description text.
By default, `fetch_details` is disabled (`false`) because `descriptionTeaser` provides an immediate summary and listing pagination takes only ~1-2 seconds even for hundreds of postings.

---

## 4. Config Format

```json
{
  "name": "Bell Canada",
  "board": "phenom",
  "url": "https://jobs.bell.ca/ca/en",
  "blurb": "Canada's largest telecommunications and media enterprise."
}
```

Optional filters:
- `"location"`: Substring match against `location`, `country`, or `multi_location` (case-insensitive).
- `"category"`: Substring match against `category` or `multi_category`.
- `"keyword"`: Substring match against `title` or `descriptionTeaser`.
- `"max_pages"`: Cap on number of 10-job pages to fetch (default: 50 = 500 jobs).
- `"fetch_details"`: Boolean to fetch full HTML descriptions per job (default: false).
