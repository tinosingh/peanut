"""Tests for T-013 (parsers + detector) and T-014 (chunker + PII scanner)."""
import os
import tempfile
from pathlib import Path

from src.ingest.parsers.detector import detect_type
from src.ingest.parsers.markdown_parser import parse_markdown
from src.ingest.chunker import chunk_text, Chunk
from src.ingest.pii import has_pii, scan_text


# ── T-013: Detector ────────────────────────────────────────────────────────

def test_detect_type_by_extension():
    assert detect_type("inbox.mbox") == "mbox"
    assert detect_type("inbox.mbx") == "mbox"
    assert detect_type("report.pdf") == "pdf"
    assert detect_type("notes.md") == "markdown"
    assert detect_type("README.markdown") == "markdown"


def test_detect_type_unknown():
    assert detect_type("file.xyz123") == "unknown"


def test_detect_type_case_insensitive():
    assert detect_type("REPORT.PDF") == "pdf"
    assert detect_type("NOTES.MD") == "markdown"


# ── T-013: Markdown parser ─────────────────────────────────────────────────

def test_parse_markdown_strips_headers():
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as f:
        f.write("# Title\n\nSome content here.\n\n## Section\n\nMore text.")
        path = f.name
    try:
        result = parse_markdown(path)
        assert "Title" in result
        assert "#" not in result
    finally:
        os.unlink(path)


def test_parse_markdown_strips_frontmatter():
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as f:
        f.write("---\ntitle: Test\nauthor: Alice\n---\n\nActual content here.")
        path = f.name
    try:
        result = parse_markdown(path)
        assert "Actual content" in result
        assert "title:" not in result
    finally:
        os.unlink(path)


def test_parse_markdown_strips_links():
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as f:
        f.write("[Click here](https://example.com) for info.")
        path = f.name
    try:
        result = parse_markdown(path)
        assert "Click here" in result
        assert "https://example.com" not in result
    finally:
        os.unlink(path)


# ── T-014: Chunker ─────────────────────────────────────────────────────────

def test_chunk_text_returns_chunks():
    text = "This is a test sentence. " * 200
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    assert len(chunks) >= 2
    assert all(isinstance(c, Chunk) for c in chunks)


def test_chunk_text_indices_are_sequential():
    text = "Word " * 1000
    chunks = chunk_text(text, chunk_size=100, overlap=10)
    for i, c in enumerate(chunks):
        assert c.index == i


def test_chunk_text_empty_input():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_chunk_text_short_input_is_one_chunk():
    text = "This is a short text."
    chunks = chunk_text(text, chunk_size=512, overlap=50)
    assert len(chunks) == 1
    assert "This is a short text" in chunks[0].text


def test_chunk_text_overlap_seeds_next_chunk():
    """Last words of chunk N should appear at start of chunk N+1."""
    text = ". ".join([f"Sentence number {i} with some content here" for i in range(100)])
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    if len(chunks) >= 2:
        last_words_c0 = set(chunks[0].text.split()[-5:])
        first_words_c1 = set(chunks[1].text.split()[:10])
        assert last_words_c0 & first_words_c1  # overlap exists


# ── T-014: PII scanner ─────────────────────────────────────────────────────

def test_pii_detects_ssn():
    assert has_pii("Patient SSN is 123-45-6789.") is True


def test_pii_detects_credit_card():
    assert has_pii("Card number: 4111 1111 1111 1111") is True


def test_pii_detects_medical_term():
    assert has_pii("The diagnosis was confirmed.") is True


def test_pii_clean_text():
    assert has_pii("The quarterly sales report showed strong growth in Q3.") is False


def test_scan_text_returns_dict():
    result = scan_text("Patient SSN 123-45-6789.")
    assert isinstance(result, dict)
    assert "pii_detected" in result
    assert result["pii_detected"] is True


def test_pii_no_crash_on_empty():
    assert has_pii("") is False
