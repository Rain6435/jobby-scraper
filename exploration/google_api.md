# Google Careers API Specification

## Overview

Google operates a unified career portal across `careers.google.com` and `google.com/about/careers/applications/jobs/results`. The frontend is built on Google's internal BoQ Web UI framework (`boq_corp-hiring-boq-cportal-frontend`).

Rather than separate XHR calls or proprietary authentication, the server pre-renders search results directly into the static HTML document via Wiz/BoQ `AF_initDataCallback` blocks (specifically `key: "ds:1"`).

- **Portal URL**: `https://www.google.com/about/careers/applications/jobs/results` (or `https://careers.google.com`)
- **Authentication**: None required (public search page)
- **Data Carrier**: `<script>AF_initDataCallback({key: 'ds:1', ... data:[...]})</script>`
- **Direct Job Posting URL**: `https://www.google.com/about/careers/applications/jobs/results/{job_id}`

---

## 1. Request Query Parameters

```http
GET https://www.google.com/about/careers/applications/jobs/results?page=1&q=software&location=Seattle&company=Google
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | `integer` | `1` | Page number (1-indexed; 20 postings per page) |
| `q` | `string` | `""` | Search keyword / role query (e.g. `"software"`, `"deepmind"`) |
| `location` | `string` | `""` | Location text filter (e.g. `"Seattle"`, `"New York"`, `"London"`) |
| `company` | `string` | `""` | Entity filter (`"Google"`, `"DeepMind"`, `"YouTube"`, `"GFiber"`) |

---

## 2. Response Structure (`ds:1`)

The JavaScript initialization callback `AF_initDataCallback` contains an array of 4 elements:
```javascript
AF_initDataCallback({
  key: 'ds:1',
  data: [
    [ /* array of 20 job objects */ ],
    null,
    3383, /* total number of matching live postings */
    20    /* page size */
  ]
})
```

### Job Item Schema
Each job is represented as an array of 21 positional elements:

| Index | Type | Description | Example |
|-------|------|-------------|---------|
| `[0]` | `string` | Stable numeric Job ID | `"138153832042373830"` |
| `[1]` | `string` | Job Title | `"AI Technical Delivery Lead, Google Cloud"` |
| `[2]` | `string` | Application sign-in / redirect URL | `"https://www.google.com/about/careers/applications/signin?..."` |
| `[3]` | `[null, string]` | Responsibilities (HTML) | `[null, "<ul><li>Define AI deployment goals...</li></ul>"]` |
| `[4]` | `[null, string]` | Qualifications (HTML) | `[null, "<h3>Minimum qualifications:</h3>..."]` |
| `[5]` | `string` | Internal proto resource path | `"projects/gweb-careers-proto/tenants/..."` |
| `[7]` | `string` | Company / division name | `"Google"`, `"DeepMind"`, or `"YouTube"` |
| `[8]` | `string` | Language locale code | `"en-US"` |
| `[9]` | `list[list]` | Standardized locations | `[["London, UK", ["1 St Giles High St..."], "London", ...]]` |
| `[10]` | `[null, string]` | Job Overview / About the Job (HTML) | `[null, "<p>The Google Cloud Consulting team guides...</p>"]` |
| `[12]` | `[int, int]` | Creation timestamp (epoch seconds) | `[1788952097, 317000000]` |
| `[13]` | `[int, int]` | Update timestamp (epoch seconds) | `[1788952097, 317000000]` |

---

## 3. Data Extraction Details

1. **Job ID & URL**:
   - `id`: `google:{job[0]}`
   - `url`: `https://www.google.com/about/careers/applications/jobs/results/{job[0]}`
2. **Locations**:
   - Primary: `job[9][0][0]` (e.g. `"Mountain View, CA, USA"`)
   - All locations: `[loc[0] for loc in job[9]]`
3. **Posting Date**:
   - Parsed from epoch timestamp `job[12][0]` -> `YYYY-MM-DD` and relative days.
4. **Description**:
   - Concatenation of About the Job (`job[10][1]`), Responsibilities (`job[3][1]`), and Qualifications (`job[4][1]`), stripped via `html_to_text`. Zero secondary detail HTTP requests needed.
