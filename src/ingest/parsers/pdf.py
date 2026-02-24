"""PDF parser using pdfminer.six."""
from __future__ import annotations

from io import StringIO

import structlog

log = structlog.get_logger()


def parse_pdf(path: str) -> str:
    """Extract text from a PDF file. Returns empty string on failure."""
    try:
        from pdfminer.high_level import extract_text
        text = extract_text(path)
        return text or ""
    except Exception as exc:
        log.error("pdf_parse_error", path=path, error=str(exc))
        raise
