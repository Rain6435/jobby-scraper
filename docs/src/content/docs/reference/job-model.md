---
title: Job model
description: The Job dataclass every board produces.
---

Every board returns a list of `Job` objects, defined in [`scraper/models.py`](https://github.com/Rain6435/jobby-scraper/blob/main/scraper/models.py). This is also the JSON shape printed by `--url`.

| Field | Type | Set by | Description |
| ----- | ---- | ------ | ----------- |
| `id` | `str` | board | `{company_slug}:{requisition_id}`. The diff key; must be stable across runs. |
| `company` | `str` | board | Company name, normally the config `name`. Aggregator boards set it per posting. |
| `title` | `str` | board | Posting title. |
| `location` | `str` | board | Primary location (the first of `locations`). |
| `url` | `str` | board | Direct link to the posting. |
| `posted_on` | `str` | board | Raw date text from the board, e.g. `"Posted 3 Days Ago"`. Not stored. |
| `source` | `str` | board | The board name, e.g. `"workday"`. |
| `locations` | `list[str]` | board | Every location the posting lists, as raw strings. |
| `posted_days` | `int \| None` | board | Days since posting, at scrape time. `None` for date-less boards. Not stored. |
| `description` | `str` | board | Full plain-text description, HTML stripped, never truncated. |
| `first_seen` | `str` | pipeline | ISO 8601 UTC timestamp of the first run that saw this id. |
| `posted_date` | `str \| None` | pipeline | `YYYY-MM-DD`, derived once from `first_seen - posted_days` and kept forever. |
| `role_summary` | `str` | external | Short AI summary, filled in by a separate process. Carried forward. |
| `company_blurb` | `str` | pipeline | From the company's config entry. |
| `company_logo` | `str` | pipeline | From the company's config entry. |
| `company_group` | `str` | board | Umbrella name for boards that split one employer into many `company` values (e.g. GC Jobs departments). Empty otherwise. |
| `default_country` | `str` | pipeline | From the company's config entry. Used only as a location-parsing fallback. |

"Pipeline" fields are filled in by `scraper/main.py` after the board returns; boards leave them at their defaults.
