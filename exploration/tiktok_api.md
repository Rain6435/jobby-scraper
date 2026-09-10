# TikTok Careers API Specification

## Overview

TikTok (ByteDance) operates an in-house, proprietary ATS and candidate portal hosted across `lifeattiktok.com` and `careers.tiktok.com`. The career portal interacts with an API gateway powered by ByteDance's internal Stargate (`TLB`) microservice infrastructure at `https://api.lifeattiktok.com/`.

- **Portal URL**: `https://lifeattiktok.com/search` (also reachable via `https://careers.tiktok.com/position`)
- **API Base**: `https://api.lifeattiktok.com/`
- **Authentication**: None required (public supplier career search endpoint)
- **Required Headers**:
  - `Content-Type: application/json`
  - `website-path: tiktok` (mandatory gateway routing header; omitted requests return 400 Bad Request)
  - `Referer: https://lifeattiktok.com/search`
  - Standard browser `User-Agent`

---

## 1. Search Endpoint

### Endpoint
```http
POST https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts
```

### Request Payload (JSON)
```json
{
  "keyword": "",
  "limit": 100,
  "offset": 0,
  "job_category_id_list": [],
  "location_code_list": [],
  "recruitment_id_list": [],
  "subject_id_list": []
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `keyword` | `string` | `""` | Search text matching title or keywords |
| `limit` | `integer` | `12` | Page size (up to `100` tested reliably) |
| `offset` | `integer` | `0` | Starting index for pagination (0, 100, 200...) |
| `job_category_id_list` | `list[string]` | `[]` | Category filter IDs (e.g. `"6704215862603155720"` for R&D) |
| `location_code_list` | `list[string]` | `[]` | Location filter codes (e.g. `"CT_94"` for Los Angeles) |
| `recruitment_id_list` | `list[string]` | `[]` | Recruit type filter (e.g. Intern vs Regular) |

---

## 2. Response Structure

### Root Response
```json
{
  "code": 0,
  "data": {
    "count": 4200,
    "job_post_list": [ ... ]
  }
}
```

`code == 0` signifies success. `count` contains the total number of matched postings globally (~4,200 active roles).

### Job Post Item (`job_post_list[i]`)
```json
{
  "id": "7669925556293601541",
  "code": "A28333",
  "title": "Category Manager Intern (TikTok Shop - Operations-Beauty, Food & Beverage ) - 2027 Summer (MBA)",
  "description": "About the Team\nThe commerce industry has seen tremendous growth...",
  "requirement": "Minimum Qualifications:\n- Currently pursuing a MBA Degree...",
  "recruit_type": {
    "id": "202",
    "en_name": "Intern",
    "i18n_name": "Intern"
  },
  "job_category": {
    "id": "6704215882479962371",
    "en_name": "Operations",
    "i18n_name": "Operations",
    "parent": null
  },
  "city_info": {
    "code": "CT_94",
    "location_type": 3,
    "en_name": "Los Angeles",
    "i18n_name": "Los Angeles",
    "parent": {
      "code": "ST_31",
      "location_type": 2,
      "en_name": "California",
      "i18n_name": "California",
      "parent": {
        "code": "CN_6",
        "location_type": 1,
        "en_name": "United States of America",
        "i18n_name": "United States of America",
        "parent": null
      }
    }
  },
  "job_post_info": {
    "min_salary": null,
    "max_salary": null,
    "currency": null,
    "required_degree": null,
    "experience": null,
    "sequence": null,
    "expiry_time": null
  }
}
```

### Key Highlights
- **Full Text Included**: Unlike most ATS platforms that require secondary detail queries per job, TikTok includes both `description` (responsibilities, overview) and `requirement` (minimum and preferred qualifications) directly in the search response payload.
- **Structured Hierarchical Locations**: `city_info` provides a structured linked list of `city -> state/province -> country` with English names (`en_name`).
- **Canonical Post URL**: `https://lifeattiktok.com/position/{id}`.

---

## 3. Filters Endpoint

```http
POST https://api.lifeattiktok.com/api/v1/public/supplier/config/job/filters
```
Returns list of available cities, job types, categories, and tags.
