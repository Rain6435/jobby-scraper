# Job-board API exploration

**Status: IMPLEMENTED.** All three boards now ship as real scrapers in
[scraper/boards/](../scraper/boards/) (`greenhouse.py`, `rippling.py`, `bamboohr.py`).
These probe scripts remain as live API references. Decisions made at implementation:
list endpoints only (no per-job detail); **keyword-gated** storage; Greenhouse uses
its real `first_published` date, Rippling/BambooHR are date-less and tracked via
`first_seen`. Applicant-count priority was dropped — none of the three expose it.

Originally throwaway probe scripts + my understanding of three new boards
(BambooHR, Greenhouse, Rippling), validated against live endpoints on 2026-06-19.

Run any probe: `python exploration/explore_<board>.py [company_or_token]`

## How each maps to our existing pipeline

Our scraper produces a `Job` (see [scraper/models.py](../scraper/models.py)) with:
`id` (diff key, must be stable), `title`, `location`, `locations[]`, `url`,
`posted_on`, `posted_days`, `source`. A new board = one `BaseScraper` subclass
implementing `fetch_jobs()`. Below is what each API gives us toward that.

---

## 1. Greenhouse — the easy one ✅

- **Auth:** none. **Base:** `https://boards-api.greenhouse.io/v1/boards/{token}`
- **One GET** `/jobs?content=true` returns **every** job (title, location,
  description, dates, apply URL) — **no pagination, no per-job calls.** Asana = 139 jobs in one response.
- **Stable id:** `id` (int) — also `requisition_id` (e.g. `"JR105926"`).
- **Posting date:** `first_published` (ISO+tz) — present in the list, so age-filtering is free. `updated_at` also available.
- **Location:** `location.name` — a **free-form string** ("Dublin", "San Francisco", "Warsaw"). `offices[].location` gives a richer "City, Country".
- **Apply URL:** `absolute_url`.
- **Job → our model:** `id={slug}:{id}`, `title`, `location=location.name`,
  `locations=[location.name]`, `url=absolute_url`, `posted_on/posted_days` from `first_published`, `source="greenhouse"`.
- **Cost:** 1 request per company. Cheapest of the three.
- **Note:** `content` is HTML-entity-encoded — `html.unescape()` then strip tags if we ever use it. We probably don't need it.

## 2. Rippling — rich list, date needs detail

- **Auth:** none. **Base:** `https://ats.rippling.com/api/v2/board/{board}/jobs`
- **Paginated list** (`?page=&pageSize=50`, has `totalPages`). octasic-inc = 26 jobs, 1 page.
- **Location is already structured in the list** — `locations[]` with
  `name` ("Hybrid (Montreal, QC, CA)"), `city`, `state`, `country`, `countryCode`, `workplaceType`. **No detail call needed for location or title.**
- **Posting date only in detail:** `GET /jobs/{uuid}` → `createdOn` (ISO+tz). Detail also has `description`, `employmentType`, `payRangeDetails`.
- **Stable id:** `id` (UUID).
- **Apply URL:** `url` (in the list).
- **Job → our model:** `id={slug}:{uuid}`, `title=name`, `locations=[l.name ...]`,
  `url`, `posted_on/posted_days` from `createdOn` (detail), `source="rippling"`.
- **Cost:** 1 list request + 1 detail per job *only if we want the posting date*.
- **Relevance:** octasic-inc is a **Montreal** company with French titles
  ("Développeur Logiciel", "Ingénieur(e) en Vérification") — great fit for our QC/ON + French criteria.

## 3. BambooHR — date is buried, multi-location splits rows

- **Auth:** none. **Base:** `https://{company}.bamboohr.com/careers`
- **`/list`** returns all openings (euna = 45), **no page params seen.** Fields:
  `id`, `jobOpeningName`, `departmentLabel`, `employmentStatusLabel`, `location{city,state}`, `isRemote`, `locationType`.
- **⚠️ Doc discrepancy:** [Job_Scraper.md](../Job_Scraper.md) says the date is
  `result.datePosted` / `postedDate`. **Actually** it's nested at
  **`result.jobOpening.datePosted`** (date-only, e.g. `"2026-02-25"`), and `/detail` returns `{jobOpening, formFields}`, not a flat object.
- **⚠️ Multi-location = separate rows:** a role in two cities appears as **two
  list entries** with the same `jobOpeningName` but different `id` + `location`
  (e.g. "Senior Software Architect" → Oakville **and** Atlanta). So `id` is unique per posting-location; no multi-location merging needed (unlike Workday).
- **Stable id:** `id` (string, e.g. `"562"`).
- **Apply URL:** `jobOpening.jobOpeningShareUrl` (= `https://{company}.bamboohr.com/careers/{id}`) — can be built without a detail call.
- **Location:** `location.city` + `location.state` → "Oakville, Ontario".
- **Job → our model:** `id={slug}:{id}`, `title=jobOpeningName`,
  `location="city, state"`, `url=careers/{id}`, `posted_on/posted_days` from detail's `datePosted`, `source="bamboohr"`.
- **Cost:** 1 list request + 1 detail per job for the date.

---

## Cross-cutting observations (for planning)

| | Greenhouse | Rippling | BambooHR |
|---|---|---|---|
| Auth / key | none | none | none |
| List returns everything | ✅ (1 call) | paginated | ✅ (1 call) |
| Posting date in list | ✅ `first_published` | ❌ (detail `createdOn`) | ❌ (detail `datePosted`) |
| Location in list | ✅ string | ✅ structured | ✅ city/state |
| Stable id | int / req_id | UUID | string |
| Per-job detail needed | no | only for date | only for date |
| Config field | `board_token` | `board_id` (slug) | `company` (subdomain) |

**Key design questions for the planning step:**
1. **Posting date vs N detail calls.** Greenhouse gives dates free. Rippling/BambooHR
   need one detail call per job to get the date. Options: (a) accept the extra
   calls (boards are small — 26/45 jobs), (b) skip age-filtering for these boards
   and rely purely on snapshot-diffing for "new", fetching detail lazily only for
   unseen jobs. Our `max_age_days` cutoff is the thing that wants the date.
2. **Config schema.** Each board needs a different identifier key
   (`board_token` / `board_id` / `company`). The existing `"board"` field in
   config.json already selects the scraper; we'd add the board-specific id field.
3. **Location → classifier.** All three emit location strings our existing
   [docs/locations.js](../docs/locations.js) classifier already handles well
   (Rippling's "Montreal, QC, CA" → good; Asana's "Dublin"/"Warsaw" → foreign).
4. **Politeness.** All are undocumented/public. Send a real `User-Agent`, add
   ~0.3–0.5s between detail calls, check each target's ToS/robots before scaling.

## Examples (verified companies)

Each block is a ready-to-run probe command plus the `config.json` entry that wires
the same company into the real scraper.

### Greenhouse — `asana`
```bash
python exploration/explore_greenhouse.py asana
```
```json
{ "name": "Asana", "board": "greenhouse", "token": "asana" }
```

### Rippling — `octasic-inc`  (Montreal, French postings — great fit)
```bash
python exploration/explore_rippling.py octasic-inc
```
```json
{ "name": "Octasic", "board": "rippling", "board_id": "octasic-inc" }
```

### BambooHR — `euna`  (Oakville ON + Atlanta)
```bash
python exploration/explore_bamboohr.py euna
```
```json
{ "name": "Euna", "board": "bamboohr", "company": "euna" }
```
