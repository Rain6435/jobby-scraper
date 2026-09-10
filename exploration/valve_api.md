# Valve Software Careers Architecture & Exploration

## Overview

Valve Corporation does not use an Applicant Tracking System. All careers at Valve are published directly on Valve's own custom flat website:

- **List URL:** `GET https://www.valvesoftware.com/en/jobs`
- **Detail URL:** `GET https://www.valvesoftware.com/en/jobs?job_id={job_id}`
- **Authentication:** None required (public static site)
- **Total Volume:** ~30–45 permanent roles across game development, Steam platform, hardware (Steam Deck/VR), audio, and operations.
- **Location:** All Valve roles are based at Valve HQ in **Bellevue, WA** (Seattle metropolitan area).

---

## Page Structure

### 1. Job Directory (`/en/jobs`)

Each listing is rendered as an `<a>` link:

```html
<a href="https://www.valvesoftware.com/en/jobs?job_id=85">
    Audio Software Engineer
</a>
```

Regex pattern:
```python
r"<a[^>]+href=[\"']https://www\.valvesoftware\.com/en/jobs\?job_id=(\d+)[\"'][^>]*>(.*?)</a>"
```

### 2. Job Detail (`/en/jobs?job_id={id}`)

Full role descriptions and "What We Offer" benefits are contained within:

```html
<div class="job_description_intro">
    <p>At Valve, audio software engineers push the boundaries...</p>
</div>
```

Regex pattern:
```python
r"<div class=[\"']job_description_intro[\"']>(.*?)</div>"
```

---

## Field Mapping to `Job`

| Field | Source | Mapping to `Job` |
| :--- | :--- | :--- |
| Job ID | URL query param `job_id` | `id = f"valve:{job_id}"` |
| Title | Link inner HTML stripped of tags | `title = title.strip()` |
| Location | Bellevue, Washington HQ | `location = "Bellevue, WA"`, `locations = ["Bellevue, WA"]` |
| URL | Direct link | `f"https://www.valvesoftware.com/en/jobs?job_id={job_id}"` |
| Description | `<div class="job_description_intro">` | Cleaned via `html_to_text()` |
| Posting Date | Not displayed on Valve's board | `posted_on = ""`, `posted_days = None` (age tracked via `first_seen`) |
