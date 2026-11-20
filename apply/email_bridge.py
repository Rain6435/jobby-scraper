"""Email Verification Bridge: extract 6-digit OTPs or verification links via IMAP."""

from __future__ import annotations

import email
import imaplib
import re
from email.message import Message
from typing import TypedDict

OTP_RE = re.compile(r"\b(\d{6})\b")
VERIFY_LINK_RE = re.compile(
    r"https?://[^\s\"'<>]+(?:verify|confirm|activate|token)[^\s\"'<>]*", re.I
)


class VerificationMatch(TypedDict):
    otp_code: str
    verification_url: str
    sender: str
    subject: str


def extract_verification_from_text(body: str) -> tuple[str, str]:
    """Extract (6-digit OTP, verification URL) from an email body."""
    otp_m = OTP_RE.search(body)
    link_m = VERIFY_LINK_RE.search(body)
    return (otp_m.group(1) if otp_m else "", link_m.group(0) if link_m else "")


def _message_text(msg: Message) -> str:
    if msg.is_multipart():
        parts: list[str] = []
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype in ("text/plain", "text/html"):
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    parts.append(payload.decode("utf-8", errors="replace"))
        return "\n".join(parts)
    payload = msg.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace")
    return str(payload or "")


def poll_imap_for_verification(
    *,
    host: str,
    username: str,
    password: str,
    sender_allowlist: list[str],
    port: int = 993,
    mailbox: str = "INBOX",
    limit: int = 10,
) -> VerificationMatch | None:
    """Connect to IMAP over SSL and scan recent messages from ATS allowlisted senders."""
    with imaplib.IMAP4_SSL(host, port) as client:
        client.login(username, password)
        client.select(mailbox, readonly=True)
        status, data = client.search(None, "ALL")
        if status != "OK" or not data or not data[0]:
            return None
        msg_ids = data[0].split()[-limit:]
        for msg_id in reversed(msg_ids):
            f_status, msg_data = client.fetch(msg_id, "(RFC822)")
            if f_status != "OK" or not msg_data:
                continue
            raw_bytes: bytes | None = None
            for item in msg_data:
                if isinstance(item, tuple) and len(item) >= 2:
                    raw_bytes = item[1]
                    break
            if raw_bytes is None:
                continue
            msg = email.message_from_bytes(raw_bytes)
            sender = str(msg.get("From") or "")
            subject = str(msg.get("Subject") or "")
            if sender_allowlist and not any(
                dom.lower() in sender.lower() for dom in sender_allowlist
            ):
                continue
            otp, url = extract_verification_from_text(_message_text(msg))
            if otp or url:
                return {
                    "otp_code": otp,
                    "verification_url": url,
                    "sender": sender,
                    "subject": subject,
                }
    return None
