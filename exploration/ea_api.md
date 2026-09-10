# Electronic Arts (EA) Careers API Specification

## Overview

Electronic Arts operates a custom branded career portal across `ea.com/careers` and `jobs.ea.com`.

- **Portal URL**: `https://jobs.ea.com/en_US/careers`
- **Search Endpoint**: `https://jobs.ea.com/en_US/careers/SearchJobs`
- **Authentication**: None required (public candidate search)
- **Active Postings**: ~326 live global roles

---

## 1. Search & Pagination Parameters

```http
GET https://jobs.ea.com/en_US/careers/SearchJobs/?search=engineer&jobRecordsPerPage=20&jobOffset=0
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `jobRecordsPerPage` | `integer` | `20` | Page size (20 items per page) |
| `jobOffset` | `integer` | `0` | Offset index for pagination (0, 20, 40, 60...) |
| `search` | `string` | `""` | Optional role title or keyword filter |

---

## 2. Page Structure & Data Extraction

The search results page renders each job inside an `<article class="article article--result ...">` block:

1. **Job Link & ID**:
   - Matches: `<a class="link link_result" href="https://jobs.ea.com/en_US/careers/JobDetail/{title-slug}/{job_id}">`
   - Stable numeric ID: extracted from end of JobDetail URL (e.g. `215930`).
2. **Title**: Text inside `<a class="link link_result">...</a>`.
3. **Location**: `<span class="list-item-location">{location}</span>` (e.g. `Hyderabad, India`, `Redwood City, California, United States`).
4. **Worker Type**: `<span class="list-item-workerType">{type}</span>` (e.g. `Regular`, `Intern - Temporary Employee`).
5. **Department**: `<span class="list-item-department">{department}</span>`.

---

## 3. Detail Page (`JobDetail`)

```http
GET https://jobs.ea.com/en_US/careers/JobDetail/{title-slug}/{job_id}
```
The detail page displays the full role description within:
```html
<div class="article__content__view__field__value">...</div>
```
The description is extracted by selecting the longest field value block and passing through `html_to_text`. Detail calls are made concurrently and cached across runs via `BaseScraper._fetch_details_concurrent`.
