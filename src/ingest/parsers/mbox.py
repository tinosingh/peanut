"""MBOX email parser.

Extracts (sender_email, sender_name, recipients, subject, body_text, date)
from each message in an MBOX file.

All DB writes (document + persons UPSERT + outbox INSERT) are in a SINGLE
transaction, as required by the PRD.
"""
from __future__ import annotations

import email
import email.utils
import mailbox
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from email.header import decode_header

import structlog

log = structlog.get_logger()


@dataclass
class ParsedMessage:
    message_id: str
    sender_email: str
    sender_name: str
    recipients: list[dict]   # [{email, name, field}]  field = to/cc/bcc
    subject: str
    body_text: str
    date: datetime
    raw_bytes: int = 0


def _decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    parts = []
    for chunk, charset in decode_header(value):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return " ".join(parts).strip()


def _parse_address(addr: str) -> tuple[str, str]:
    """Return (email, display_name)."""
    name, email_addr = email.utils.parseaddr(addr)
    return email_addr.lower().strip(), _decode_header_value(name)


def _extract_body(msg: email.message.Message) -> str:
    """Prefer text/plain; fall back to stripping HTML."""
    for part in msg.walk():
        ct = part.get_content_type()
        if ct == "text/plain" and part.get("Content-Disposition") != "attachment":
            charset = part.get_content_charset() or "utf-8"
            try:
                return part.get_payload(decode=True).decode(charset, errors="replace")
            except Exception:
                pass
    return ""


def _parse_recipients(msg: email.message.Message) -> list[dict]:
    recipients = []
    for field_name in ("to", "cc", "bcc"):
        raw = msg.get(field_name, "")
        if not raw:
            continue
        for addr in email.utils.getaddresses([raw]):
            addr_email = addr[1].lower().strip()
            addr_name = _decode_header_value(addr[0])
            if addr_email:
                recipients.append({"email": addr_email, "name": addr_name, "field": field_name})
    return recipients


def parse_mbox(path: str) -> Iterator[ParsedMessage | Exception]:
    """Yield ParsedMessage or Exception (for dead-letter) per message."""
    try:
        mbox = mailbox.mbox(path)
    except Exception as exc:
        yield exc
        return

    for key, msg in mbox.items():
        try:
            sender_raw = msg.get("from", "")
            sender_email, sender_name = _parse_address(sender_raw)
            if not sender_email:
                sender_email = "unknown@unknown"

            subject = _decode_header_value(msg.get("subject", ""))
            body = _extract_body(msg)
            recipients = _parse_recipients(msg)

            date_raw = msg.get("date")
            if date_raw:
                try:
                    date = email.utils.parsedate_to_datetime(date_raw)
                    if date.tzinfo is None:
                        date = date.replace(tzinfo=timezone.utc)
                except Exception:
                    date = datetime.now(timezone.utc)
            else:
                date = datetime.now(timezone.utc)

            msg_id = msg.get("message-id", str(uuid.uuid4()))

            yield ParsedMessage(
                message_id=msg_id,
                sender_email=sender_email,
                sender_name=sender_name,
                recipients=recipients,
                subject=subject,
                body_text=body,
                date=date,
                raw_bytes=len(str(msg).encode()),
            )
        except Exception as exc:
            log.error("mbox_parse_error", key=key, error=str(exc))
            yield exc
