# Microsoft Careers API Documentation & Exploration

## Overview

Microsoft does not use standard commercial ATS platforms (like Greenhouse, Lever, or Workday). Instead, **careers.microsoft.com** is powered by a custom career portal (PCSX / Eightfold):

- **Search Endpoint:** `GET https://apply.careers.microsoft.com/api/pcsx/search`
- **Position Details Endpoint:** `GET https://apply.careers.microsoft.com/api/pcsx/position_details`
- **Authentication:** None required (public API)
- **Headers:** `Accept: application/json`, standard `User-Agent`
- **Required Query Parameter:** `domain=microsoft.com`
- **Pagination:** Uses `start=0, 10, 20...` (page size is fixed at 10 results per page)

---

## Response Structure

### 1. Search Results (`/api/pcsx/search`)

```json
{
  "status": 200,
  "data": {
    "count": 2258,
    "positions": [
      {
        "id": 1970393556986872,
        "displayJobId": "200053481",
        "atsJobId": "200053481",
        "name": "Critical Environment Program Manager",
        "locations": ["United States, Washington, Quincy"],
        "standardizedLocations": ["Quincy, WA, US"],
        "postedTs": 1788994565,
        "department": "Data Center Operations Management",
        "workLocationOption": "onsite",
        "positionUrl": "/careers/job/1970393556986872"
      }
    ]
  }
}
```

### 2. Position Details (`/api/pcsx/position_details`)

- **URL:** `GET https://apply.careers.microsoft.com/api/pcsx/position_details?position_id={position_id}&domain=microsoft.com&hl=en`
- Returns full HTML body in `data.jobDescription`, employment type, profession, and role metadata.

---

## Field Reference & Mapping

| Field | Type | Description | Mapping to `Job` |
| :--- | :--- | :--- | :--- |
| `id` | `int` | Primary stable position identifier | `id = f"microsoft:{id}"` |
| `displayJobId` / `atsJobId` | `string` | Internal requisition number | Carried in metadata |
| `name` | `string` | Official job title | `title = name.strip()` |
| `standardizedLocations` | `list[str]` | Normalized location array (e.g. `["Redmond, WA, US"]`) | `locations = standardizedLocations` |
| `positionUrl` | `string` | Relative path to posting, e.g. `/careers/job/1970393556986872` | `url = f"https://apply.careers.microsoft.com{positionUrl}"` |
| `postedTs` | `int` | Unix epoch timestamp in seconds | Parsed via `datetime.fromtimestamp(ts, UTC)` into `posted_days` and `posted_on` |
| `workLocationOption` | `string` | Workplace type (`"onsite"` vs `"remote"`) | Workplace metadata |
| `jobDescription` | `string` | Full HTML posting body (from details endpoint) | Stripped via `html_to_text()` |

---

## Query Parameters & Filters

- **`domain`** (required): `"microsoft.com"`
- **`start`**: Offset for pagination (`0`, `10`, `20`, ...)
- **`query`**: Keyword search (e.g. `query=Azure`, `query=Kubernetes`)
- **`location`**: Location filter (e.g. `location=Remote`, `location=United States`, `location=Redmond, WA, United States`)
- **`sort_by`**: Sorting order (`timestamp`, `distance`)
