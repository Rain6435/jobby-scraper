# Job Monitor

A personal job monitoring system that scrapes multiple Workday company career pages, notifies you on Discord when new jobs matching your criteria appear, and displays all current listings on a GitHub Pages dashboard.

---

## How It Works

```
Every 3 hours
    → Hit all configured Workday URLs
    → Compare results to last snapshot
    → If new jobs match criteria:
        → Post Discord notification with summary + dashboard link
        → Update GitHub Pages dashboard
```

---

## Stack

| Layer | Tool |
|---|---|
| Scraper | Python script (POST to Workday API) |
| Scheduler | GitHub Actions (cron every 3h) |
| Storage | `jobs.json` committed to the repo |
| Dashboard | GitHub Pages (static HTML, reads `jobs.json`) |
| Notifications | Discord Webhook |

> No server needed. Everything runs on GitHub Actions for free.

---

## The Workday API

Workday career pages expose a public undocumented API. Each company has an endpoint at:

```
https://<company>.wd<N>.myworkdayjobs.com/wday/cxs/<company>/<tenant>/jobs
```

It requires a **POST** request with this body:

```json
{
  "appliedFacets": {},
  "limit": 20,
  "offset": 0,
  "searchText": ""
}
```

The response returns:

```json
{
  "total": 283,
  "jobPostings": [...],
  "facets": [...]
}
```

Each job posting contains: `title`, `postedOn`, `locationsText`, `externalPath`.

> To find a company's exact URL and tenant: open their careers page, F12 → Network → XHR, click "Load more jobs", inspect the POST request.

---

## Configured Companies

Add your target companies in a `config.json`:

```json
{
  "companies": [
    {
      "name": "CAE",
      "url": "https://cae.wd3.myworkdayjobs.com/wday/cxs/cae/career/jobs"
    }
  ],
  "criteria": {
    "keywords": ["rotation", "intern", "junior"],
    "locations": ["Montreal", "Remote"]
  }
}
```

---

## Discord Notification

When new matching jobs are found, the bot posts to a Discord channel via webhook:

```
🆕 3 new jobs found at CAE

• Software Engineer Intern — Montreal
• Data Rotation Program — Remote
• Junior Systems Analyst — Montreal

→ View all jobs: https://<you>.github.io/<repo>
```

---

## Dashboard

A static GitHub Pages site that reads `jobs.json` from the repo and displays:

- All current listings across all companies
- Filter by keyword, company, location
- Badge showing how many are new since last check
- Each job links directly to the Workday application page

---

## Setup (to do)

- [ ] Python scraper script
- [ ] `config.json` with companies + criteria
- [ ] GitHub Actions workflow (cron every 3h)
- [ ] Discord webhook integration
- [ ] `jobs.json` snapshot storage
- [ ] GitHub Pages dashboard (HTML/JS)

## other site found for now

- https://td.wd3.myworkdayjobs.com/en-US/TD_Bank_Careers


---


# Scraping BambooHR Job Listings

BambooHR career pages are JS-rendered. Don't use a headless browser — call the JSON API the page itself uses.

Replace `{company}` with the subdomain (e.g. `euna`).

## Endpoints

| Purpose | URL |
|---|---|
| All open jobs | `https://{company}.bamboohr.com/careers/list` |
| Single job detail | `https://{company}.bamboohr.com/careers/{id}/detail` |

`/list` has no posting date. `/detail` includes it (field name varies: `datePosted` / `postedDate`).

## Script

```python
import requests, time

COMPANY = "euna"
BASE = f"https://{COMPANY}.bamboohr.com/careers"
H = {"Accept": "application/json"}

jobs = requests.get(f"{BASE}/list", headers=H).json()["result"]

for j in jobs:
    d = requests.get(f"{BASE}/{j['id']}/detail", headers=H).json()["result"]
    print(j["id"], j["jobOpeningName"], j["departmentLabel"],
          j["location"].get("city"), d.get("datePosted"))
    time.sleep(0.5)  # be polite
```

## Notes

- `/list` fields: `id`, `jobOpeningName`, `departmentLabel`, `employmentStatusLabel`, `location`.
- One `/detail` call per job only if you need the date/description — otherwise `/list` alone is enough.
- Rate-limit yourself (~0.5s). Check the site's robots.txt / ToS before running.

---

# Scraping Greenhouse Job Boards

Do NOT scrape HTML. Greenhouse exposes a free public JSON API. No auth, no key, no JS rendering.

## Board token
Each company has a `board_token`. Find it in the careers URL: `boards.greenhouse.io/{token}` or in the page's network requests.
Example: Asana = `asana`.

## Endpoints
Base: `https://boards-api.greenhouse.io/v1/boards/{token}`

| Purpose | Endpoint |
|---|---|
| All jobs | `/jobs` |
| All jobs + descriptions | `/jobs?content=true` |
| Single job | `/jobs/{id}` |
| Departments (jobs nested) | `/departments` |
| Offices | `/offices` |

## Job object fields
- `id` — int, unique
- `title` — string
- `location.name` — string
- `absolute_url` — public apply URL
- `updated_at` — ISO timestamp
- `content` — HTML description (only when `content=true`); HTML-entity-encoded
- `departments` — list of `{id, name}`
- `offices` — list of `{id, name}`
- `metadata` — list of custom fields (varies by company)

## Python
```python
import requests, html, re

TOKEN = "asana"
url = f"https://boards-api.greenhouse.io/v1/boards/{TOKEN}/jobs"

jobs = requests.get(url, params={"content": "true"}).json()["jobs"]

def to_text(content):
    return re.sub(r"<[^>]+>", "", html.unescape(content or "")).strip()

for j in jobs:
    print(j["id"], j["title"], j["location"]["name"], j["absolute_url"])
    # j_text = to_text(j["content"])
```

## Notes
- `content` is HTML-encoded: run `html.unescape()` then strip tags for plain text.
- `/jobs` returns the full list in one response (no pagination needed).
- Safe to poll periodically; use `updated_at` to detect changes.
- Same pattern works for any Greenhouse company — only swap `{token}`.
- If a company embeds Greenhouse via iframe/JS, the API still works directly; ignore the host site.


---


# Scraping Jobs from Rippling ATS

Rippling exposes a **public, no-auth JSON API** behind every board.

## Find the board ID

It's the slug in the board URL.

```
https://ats.rippling.com/octasic-inc/jobs   ->  board_id = octasic-inc
```

## Endpoints

| Purpose | URL |
|---|---|
| List jobs (metadata only) | `https://ats.rippling.com/api/v2/board/{board_id}/jobs?page=0&pageSize=50` |
| Job detail (full description) | `https://ats.rippling.com/api/v2/board/{board_id}/jobs/{job_id}` |

- No API key required.
- List returns `totalItems`, `totalPages`, `items[]` (id, title, department, location) — **not** descriptions.
- Fetch each `{job_id}` separately to get the description.
- No official rate limit; add delays to be polite.

## List response shape

```json
{
  "totalItems": 21,
  "totalPages": 2,
  "items": [
    { "id": "83fb1287-...", "name": "Backend Senior Developer", "department": {...}, "workLocation": {...} }
  ]
}
```

## Python

```python
import requests, time

board = "octasic-inc"
base = f"https://ats.rippling.com/api/v2/board/{board}/jobs"

# 1. paginate listings
jobs, page = [], 0
while True:
    data = requests.get(base, params={"page": page, "pageSize": 50}, timeout=10).json()
    jobs += data["items"]
    if page >= data["totalPages"] - 1:
        break
    page += 1

# 2. fetch full detail per job
for j in jobs:
    j["detail"] = requests.get(f"{base}/{j['id']}", timeout=10).json()
    time.sleep(0.3)

print(len(jobs), "jobs")
```

## Notes

- `job_id` values are the UUIDs already visible in `/jobs/{uuid}` page URLs.
- Set a real `User-Agent` header if requests get blocked.
- Check the target's terms of service before scraping at scale.