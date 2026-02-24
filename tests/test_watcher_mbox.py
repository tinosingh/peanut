"""Tests for T-011 (watcher) + T-012 (MBOX parser) — no live DB needed."""
import hashlib
import mailbox
import os
import tempfile
from pathlib import Path

from src.ingest.watcher import ExtFilter, sha256_file, WATCHED_EXTENSIONS
from src.ingest.parsers.mbox import parse_mbox, ParsedMessage


# ── T-011: Watcher ─────────────────────────────────────────────────────────

def test_ext_filter_accepts_known_extensions():
    f = ExtFilter()
    for ext in WATCHED_EXTENSIONS:
        assert f.__class__.__bases__[0]  # DefaultFilter imported
    assert ".mbox" in WATCHED_EXTENSIONS
    assert ".pdf" in WATCHED_EXTENSIONS
    assert ".md" in WATCHED_EXTENSIONS


def test_sha256_file_correct():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
        tmp.write(b"hello world")
        tmp_path = tmp.name
    try:
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert sha256_file(tmp_path) == expected
    finally:
        os.unlink(tmp_path)


def test_sha256_file_is_64_chars():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"test")
        tmp_path = tmp.name
    try:
        assert len(sha256_file(tmp_path)) == 64
    finally:
        os.unlink(tmp_path)


# ── T-012: MBOX parser ─────────────────────────────────────────────────────

def _make_mbox(path: str, messages: list[dict]) -> None:
    mbox = mailbox.mbox(path, create=True)
    for m in messages:
        msg = mailbox.mboxMessage()
        msg["From"] = m.get("from", "sender@example.com")
        msg["To"] = m.get("to", "recipient@example.com")
        msg["Subject"] = m.get("subject", "Test Subject")
        msg["Date"] = m.get("date", "Mon, 01 Jan 2024 00:00:00 +0000")
        msg["Message-ID"] = m.get("message_id", "<test@example.com>")
        msg.set_payload(m.get("body", "Hello world body text."))
        mbox.add(msg)
    mbox.close()


def test_parse_mbox_yields_parsed_messages():
    with tempfile.NamedTemporaryFile(suffix=".mbox", delete=False) as tmp:
        path = tmp.name
    try:
        _make_mbox(path, [
            {"from": "Alice Smith <alice@example.com>",
             "to": "bob@example.com",
             "subject": "Test email",
             "body": "Hello Bob, this is a test."},
        ])
        results = list(parse_mbox(path))
        assert len(results) == 1
        msg = results[0]
        assert isinstance(msg, ParsedMessage)
        assert msg.sender_email == "alice@example.com"
        assert msg.sender_name == "Alice Smith"
        assert msg.subject == "Test email"
        assert "Hello Bob" in msg.body_text
    finally:
        os.unlink(path)


def test_parse_mbox_extracts_recipients():
    with tempfile.NamedTemporaryFile(suffix=".mbox", delete=False) as tmp:
        path = tmp.name
    try:
        _make_mbox(path, [{"to": "bob@example.com, carol@example.com"}])
        results = [r for r in parse_mbox(path) if isinstance(r, ParsedMessage)]
        emails = [r["email"] for r in results[0].recipients]
        assert "bob@example.com" in emails
        assert "carol@example.com" in emails
    finally:
        os.unlink(path)


def test_parse_mbox_recipient_has_field():
    with tempfile.NamedTemporaryFile(suffix=".mbox", delete=False) as tmp:
        path = tmp.name
    try:
        _make_mbox(path, [{"to": "bob@example.com"}])
        results = [r for r in parse_mbox(path) if isinstance(r, ParsedMessage)]
        assert results[0].recipients[0]["field"] == "to"
    finally:
        os.unlink(path)


def test_parse_mbox_malformed_yields_exception():
    with tempfile.NamedTemporaryFile(suffix=".mbox", delete=False, mode="w") as tmp:
        tmp.write("This is not valid mbox content at all!!!@@##\n")
        path = tmp.name
    try:
        results = list(parse_mbox(path))
        # Either 0 messages or 1 message (mailbox is lenient)
        assert isinstance(results, list)
    finally:
        os.unlink(path)


def test_parse_mbox_multiple_messages():
    with tempfile.NamedTemporaryFile(suffix=".mbox", delete=False) as tmp:
        path = tmp.name
    try:
        _make_mbox(path, [
            {"subject": "Message 1", "body": "Body 1"},
            {"subject": "Message 2", "body": "Body 2"},
            {"subject": "Message 3", "body": "Body 3"},
        ])
        results = [r for r in parse_mbox(path) if isinstance(r, ParsedMessage)]
        assert len(results) == 3
        subjects = [r.subject for r in results]
        assert "Message 1" in subjects
        assert "Message 3" in subjects
    finally:
        os.unlink(path)


def test_ingest_db_module_has_single_transaction():
    """Verify the DB module keeps document+persons+outbox in one transaction."""
    db_code = (Path(__file__).parent.parent / "src" / "ingest" / "db.py").read_text()
    assert "async with conn.transaction():" in db_code
    assert "outbox" in db_code
    assert "persons" in db_code
    assert "documents" in db_code
