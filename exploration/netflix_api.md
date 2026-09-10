# Netflix Careers API Specification

## Overview

Netflix operates a modern career portal backed by Eightfold.ai at `explore.jobs.netflix.net`.

- **Portal URL**: `https://jobs.netflix.com` (redirects/links to `https://explore.jobs.netflix.net/careers`)
- **API Base**: `https://explore.jobs.netflix.net/api/apply/v2/`
- **Authentication**: None required for public candidate queries
- **Domain Parameter**: `domain=netflix.com`

---

## 1. Search Endpoint

### Endpoint
```http
GET https://explore.jobs.netflix.net/api/apply/v2/jobs?domain=netflix.com&start=0&num=10
```

### Query Parameters
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `domain` | `string` | `"netflix.com"` | Tenant domain identifier |
| `start` | `integer` | `0` | Offset for pagination |
| `num` | `integer` | `10` | Page size (10 returned per query) |
| `query` | `string` | `""` | Optional keyword / title search |
| `location` | `string` | `""` | Optional location filter |

### Search Response Structure
```json
{
  "domain": "netflix.com",
  "count": 495,
  "positions": [
    {
      "id": 790318358916,
      "name": "Front-End Developer - Netflix Animation Studios",
      "posting_name": "Front-End Developer - Netflix Animation Studios",
      "location": "Vancouver,Canada",
      "locations": ["Vancouver,Canada"],
      "department": "Feature Animation",
      "business_unit": "Animation",
      "t_create": 1788480000,
      "t_update": 1788998093,
      "canonicalPositionUrl": "https://explore.jobs.netflix.net/careers/job/790318358916",
      "ats_job_id": "JR42252"
    }
  ]
}
```

---

## 2. Details Endpoint

### Endpoint
```http
GET https://explore.jobs.netflix.net/api/apply/v2/jobs/{position_id}?domain=netflix.com
```

### Detail Response Structure
Returns complete job object with `job_description` containing HTML markup:
```json
{
  "id": 790318358916,
  "name": "Front-End Developer - Netflix Animation Studios",
  "job_description": "<p>Netflix is the world's leading streaming entertainment service...</p>",
  "canonicalPositionUrl": "https://explore.jobs.netflix.net/careers/job/790318358916?microsite=netflix.com",
  "t_create": 1788480000
}
```
