"""HTML-to-plain-text conversion for job descriptions."""

from __future__ import annotations

import re
from html import unescape

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def html_to_text(html: str, max_chars: int | None = None) -> str:
    """Strip tags, collapse whitespace, unescape entities, optionally truncate.

    No external dependency (no bs4/lxml) — job-posting HTML is simple enough
    (p/ul/li/br/div/strong) that a regex-based stripper is adequate. Block-level
    tags become newlines before stripping so list items and paragraphs don't run
    together into one unreadable line.

    max_chars defaults to None (no truncation). It used to default to 1500,
    which silently capped essentially every description on the boards that
    matter — downstream consumers parse these descriptions for skills and
    requirements, and the requirements section is routinely past the 1500th
    character, so the cap was discarding exactly the text that makes a
    posting useful. Callers that genuinely want a bounded string (a preview,
    a prompt with a token budget) pass max_chars explicitly; storage keeps
    the full text.
    """
    if not html:
        return ""
    text = re.sub(r"(?i)</(p|div|li|h[1-6])>", "\n", html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = _TAG_RE.sub("", text)
    text = unescape(text)
    text = _WS_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _BLANK_LINES_RE.sub("\n\n", text).strip()
    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "…"
    return text
