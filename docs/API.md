# API

`docs/jobs.json` is a static, read-only JSON snapshot — refreshed hourly by the
same GitHub Actions cron job that powers the dashboard. It is not a live
server: there's no backend process, no query params, nothing to deploy.

GitHub Pages already gives this a stable public URL, free hosting, and
default CORS headers, and the data is fully public and read-only — so a real
server (Flask/FastAPI/etc.) was considered and deliberately skipped. It would
add hosting cost, an auth surface, and a process to maintain for zero
functional gain over the static file.

## Base URL

```
https://faradumatin.github.io/JobScraper/jobs.json
```

## Request

Plain `GET`. No query parameters, no auth, no request body.

```
GET /JobScraper/jobs.json HTTP/1.1
Host: faradumatin.github.io
```

## Response shape

```json
{
  "updated_at": "2026-07-14T15:06:23+00:00",
  "jobs": [ { "...": "..." } ]
}
```

- `updated_at` — ISO 8601 timestamp of the last successful scrape run.
- `jobs` — array of job objects, see field reference below.

## Job field reference

| Field | Type | Notes |
|---|---|---|
| `id` | string | Stable diff key, `"{company_slug}:{requisition_id}"`. Safe to use as a primary key across runs — never recycled. |
| `company` | string | Company display name. |
| `title` | string | Job title, as posted. |
| `location` | string | Primary location — equal to `locations[0]`. |
| `locations` | string[] | All locations for the posting, expanded. |
| `url` | string | Direct link to the posting. |
| `posted_on` | string | Raw text from the board (e.g. `"Posted Today"`). Display-only — not reliably parseable. |
| `posted_days` | int \| **null** | Days since posting. **`null`** on Rippling/BambooHR sources, which don't expose a date at all — do not treat `null` as `0`. |
| `source` | string | Board name: `workday`, `greenhouse`, `rippling`, `bamboohr`, `ashby`, `breezy`, `lever`, `smartrecruiters`, `recruitee`, `personio`, `usajobs`, `workable`, or `teamtailor`. |
| `first_seen` | string | ISO 8601 timestamp of when this job first appeared in any scrape. Use as the age fallback when `posted_days` is `null`. |
| `is_new` | bool | Means "new since the previous scrape run" (an hourly window) — **not** "posted today." Flips back to `false` on the next run. |
| `description` | string | Plain-text job posting (HTML stripped), full length — no longer truncated (it was capped at ~1500 chars until the cap was removed, which was discarding the requirements section of most postings). `""` if the source board doesn't expose one (currently: `breezy`) or the detail fetch failed. Consumers that need a bounded string should truncate on their own side. |
| `role_summary` | string | 1-2 sentence AI-generated summary of this specific posting. Populated for every new job on a run with `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` set; `""` for jobs scraped before that credential was configured, or if the AI call failed. |
| `company_blurb` | string | 1-2 sentence AI-generated blurb about the company, generated once and cached in `config.json`, then copied onto every job of that company. `""` until that company has been backfilled. |

## What's already filtered

`jobs.json` is an unfiltered pool: every listing each board's scraper
returns is stored, with no keyword, title, location, or age curation. A job
leaves the pool only once a fresh scrape's listing no longer includes it
(closed/filled/expired) — see `first_seen`/`is_new` above for how the
dashboard tracks age instead.

`jobs.json` is not itself keyword-filtered for any particular job type or
seniority level — that's left to consumers. [`config.json`](../config.json)'s
`criteria` (`keywords`, `blacklist_keywords`) is kept only as a reference
keyword bank consumer apps can borrow from; it is not applied by the scraper.

## Update cadence

Scraped hourly (skipping a quiet window overnight); the commit is skipped
entirely if nothing changed. Poll roughly hourly and key freshness off
`updated_at` rather than polling aggressively — this is served from GitHub
Pages' shared CDN.

## CORS & auth

Public, `GET`-only, no auth. GitHub Pages sends
`Access-Control-Allow-Origin: *` by default, so browser-based fetches from
any origin work. No enforced rate limit, but be a reasonable citizen.

## Stability

No version field today. Breaking field changes will be called out in
[`CLAUDE.md`](../CLAUDE.md) and commit messages — treat unknown fields as
safe to ignore (forward-compatible reads).

## Integration snippets

**curl**

```bash
curl -s https://faradumatin.github.io/JobScraper/jobs.json | jq '.jobs[] | select(.is_new)'
```

**JavaScript**

```js
const { updated_at, jobs } = await fetch(
  'https://faradumatin.github.io/JobScraper/jobs.json'
).then(r => r.json());

const newJobs = jobs.filter(j => j.is_new);
```

**Python**

```python
import requests

data = requests.get("https://faradumatin.github.io/JobScraper/jobs.json").json()
matches = [j for j in data["jobs"] if "intern" in j["title"].lower()]
```
