"""Dynamic per-job resume tailoring and ATS-friendly PDF generation."""

from __future__ import annotations

import html
import re
from pathlib import Path

from apply.models import CandidateProfile


def _score_relevance(text: str, job_tokens: set[str]) -> int:
    tokens = {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}
    return len(tokens & job_tokens)


def render_tailored_resume_html(
    profile: CandidateProfile,
    job_title: str,
    job_description: str,
) -> str:
    """Build clean, ATS-friendly HTML prioritizing skills/bullets matching the job."""
    job_tokens = {
        t for t in re.findall(r"[a-z0-9]+", f"{job_title} {job_description}".lower()) if len(t) > 2
    }

    skills = list(profile.get("skills", []))
    skills.sort(key=lambda s: _score_relevance(s, job_tokens), reverse=True)

    exp_blocks: list[str] = []
    for exp in profile.get("work_experience", []):
        bullets = list(exp.get("highlights", []))
        bullets.sort(key=lambda b: _score_relevance(b, job_tokens), reverse=True)
        bullet_html = "".join(f"<li>{html.escape(b)}</li>" for b in bullets[:5])
        dates = f"{html.escape(exp['start_date'])} – {html.escape(exp.get('end_date', 'Present'))}"
        exp_blocks.append(
            f"<div class='exp'><h3>{html.escape(exp['title'])} · {html.escape(exp['company'])}</h3>"
            f"<div class='meta'>{dates}</div><ul>{bullet_html}</ul></div>"
        )

    edu_blocks = [
        f"<div><strong>{html.escape(ed['degree'])}</strong> — {html.escape(ed['institution'])}"
        + (f" ({html.escape(ed.get('graduation_year', ''))})" if ed.get("graduation_year") else "")
        + "</div>"
        for ed in profile.get("education", [])
    ]

    contact_parts = [
        p
        for p in (
            profile.get("email", ""),
            profile.get("phone", ""),
            profile.get("location", ""),
            profile.get("linkedin_url", ""),
            profile.get("github_url", ""),
        )
        if p
    ]
    contact_line = " | ".join(html.escape(p) for p in contact_parts)
    skills_line = ", ".join(html.escape(s) for s in skills[:20])

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; color: #111; margin: 36px; font-size: 11pt; line-height: 1.4; }}
  h1 {{ margin: 0 0 4px; font-size: 20pt; }}
  .contact {{ color: #444; font-size: 9.5pt; margin-bottom: 14px; }}
  h2 {{ font-size: 12pt; border-bottom: 1px solid #ccc; padding-bottom: 3px; margin: 14px 0 8px; text-transform: uppercase; letter-spacing: 0.04em; }}
  h3 {{ font-size: 11pt; margin: 8px 0 2px; }}
  .meta {{ color: #555; font-size: 9.5pt; margin-bottom: 4px; }}
  ul {{ margin: 4px 0 8px 18px; padding: 0; }}
  li {{ margin-bottom: 3px; }}
</style>
</head>
<body>
  <h1>{html.escape(profile.get("full_name") or "Candidate")}</h1>
  <div class="contact">{contact_line}</div>
  {f"<p>{html.escape(profile.get('summary', ''))}</p>" if profile.get("summary") else ""}
  {f"<h2>Skills</h2><p>{skills_line}</p>" if skills_line else ""}
  {f"<h2>Experience</h2>{''.join(exp_blocks)}" if exp_blocks else ""}
  {f"<h2>Education</h2>{''.join(edu_blocks)}" if edu_blocks else ""}
</body>
</html>"""


def tailor_resume_for_job(
    profile: CandidateProfile,
    *,
    job_id: str,
    job_title: str,
    job_description: str,
    output_dir: Path = Path(".apply_data/tailored_resumes"),
) -> Path:
    """Render a tailored ATS-friendly PDF resume using Playwright Chromium."""
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", job_id)
    pdf_path = output_dir / f"{safe_id}.pdf"
    html_doc = render_tailored_resume_html(profile, job_title, job_description)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html_doc, wait_until="load")
        page.pdf(path=str(pdf_path), format="Letter")
        browser.close()
    return pdf_path
