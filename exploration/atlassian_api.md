# Atlassian Careers API Documentation

## Overview
Atlassian (maker of Jira, Confluence, Trello, Bitbucket) hosts their primary public career portal at:
`https://www.atlassian.com/company/careers/all-jobs`

Their frontend fetches all currently active job postings through an unauthenticated public JSON endpoint:
`GET https://www.atlassian.com/endpoint/careers/listings`

## API Details
- **HTTP Method:** `GET`
- **Endpoint:** `https://www.atlassian.com/endpoint/careers/listings`
- **Authentication:** None required.
- **Headers:** Standard `User-Agent`.
- **Response Format:** JSON array of job objects.
- **Pagination:** None — all active openings (typically ~240-250 jobs) are returned in a single HTTP response.
- **Performance:** ~0.4s to 0.6s total turnaround time.

## Response Payload Schema
Each element in the returned array represents one job posting:

| Field | Type | Description |
|---|---|---|
| `id` | `int` | Unique posting ID (e.g. `27075`) |
| `title` | `string` | Job title |
| `portalId` | `int` | iCIMS portal ID (e.g. `17` for global, `242` for APAC) |
| `category` | `string` | Team/function (`Engineering`, `Sales`, `Design`, `Analytics & Data Science`, etc.) |
| `type` | `string` | Employment type (e.g. `Full-Time`) |
| `locations` | `list[str]` | Array of location strings (e.g. `["Bengaluru - India -   Bengaluru,  560071 India", "Remote - Remote"]`) |
| `overview` | `string` | HTML role overview & team description |
| `responsibilities` | `string` | HTML responsibilities section |
| `qualifications` | `string` | HTML qualifications & requirements section |
| `compensation` | `string` | HTML compensation statement |
| `payRanges` | `string` | HTML base pay ranges by location/currency (when available) |
| `applyUrl` | `string` | Direct apply URL on iCIMS (`.../job?mode=apply`) |
| `portalJobPost.portalUrl` | `string` | Canonical job detail URL on iCIMS |
| `portalJobPost.updatedDate`| `string` | Last updated timestamp, formatted as `%Y-%m-%d %I:%M %p` (e.g. `2026-09-08 01:00 AM`) |

## Location Cleaning
Atlassian's location strings are structured with hyphen delimiters:
- `Austin - United States -   Austin, Texas 78702 United States` -> `Austin, United States`
- `Remote - Americas - Remote` -> `Remote, Americas`
- `Remote - Remote` -> `Remote`
- `Mountain View - United States or Remote - ...` -> `Mountain View, United States or Remote`

## Pipeline Mapping
- **`Job.id`**: `f"atlassian:{item['id']}"`
- **`Job.title`**: `item.get("title")`
- **`Job.location`**: Cleaned primary location string
- **`Job.locations`**: List of cleaned location strings
- **`Job.url`**: `item.get("portalJobPost", {}).get("portalUrl")` or `item.get("applyUrl")`
- **`Job.posted_on`**: Parsed ISO timestamp from `item["portalJobPost"]["updatedDate"]`
- **`Job.posted_days`**: Age in days computed from `posted_on`
- **`Job.description`**: Concatenation of `overview`, `responsibilities`, `qualifications`, `payRanges`, and `compensation` (100% zero-detail-call scraping)
- **`Job.source`**: `"atlassian"`
