"""Resume ingestion, profile onboarding, and application email aliasing."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from apply.llm import extract_profile_from_resume
from apply.models import CandidateProfile, EmailAliasStrategy


def extract_text_from_resume(file_path: Path) -> str:
    """Extract plain text from a PDF or UTF-8 text/markdown resume."""
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(file_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()
    return file_path.read_text(encoding="utf-8", errors="replace").strip()


def onboard_resume(file_path: Path) -> CandidateProfile:
    """Read a resume file and parse it into a structured CandidateProfile."""
    text = extract_text_from_resume(file_path)
    return extract_profile_from_resume(text)


def resolve_application_email(
    primary_email: str,
    strategy: EmailAliasStrategy,
    company_slug: str,
) -> str:
    """Compute the email address to use for a specific company/tenant."""
    clean = primary_email.strip()
    if not clean or "@" not in clean or strategy != "plus_address":
        return clean
    local, domain = clean.split("@", 1)
    base_local = local.split("+", 1)[0]
    safe_slug = "".join(ch for ch in company_slug.lower() if ch.isalnum() or ch == "-")
    if not safe_slug:
        return clean
    return f"{base_local}+{safe_slug}@{domain}"
