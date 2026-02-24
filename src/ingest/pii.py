"""PII scanner — flags chunks containing sensitive personal information.

Used at ingest time (per chunk) and via make scan-pii (retroactive).
Marks chunks.pii_detected = true if any signal fires.

Signals:
  1. spaCy PERSON entities
  2. Regex: SSN, credit card numbers, medical terms
"""
from __future__ import annotations

import re
import functools
from typing import TYPE_CHECKING

import structlog

log = structlog.get_logger()

_PII_PATTERNS = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),                              # SSN
    re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),           # credit card
    re.compile(r"\b(diagnosis|prescription|medical record|dob|date of birth)\b", re.I),
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),                  # dates of birth pattern
]


@functools.lru_cache(maxsize=1)
def _get_nlp():
    try:
        import spacy
        return spacy.load("en_core_web_sm")
    except (ImportError, OSError):
        log.warning("spacy_model_not_found", model="en_core_web_sm",
                    note="PII PERSON detection disabled — run: python -m spacy download en_core_web_sm")
        return None


def has_pii(text: str) -> bool:
    """Return True if text contains PII via spaCy PERSON entities or regex patterns."""
    # Regex check first (cheap)
    if any(p.search(text) for p in _PII_PATTERNS):
        return True

    # spaCy NER (heavier — only if regex clean)
    nlp = _get_nlp()
    if nlp is not None:
        doc = nlp(text)
        if any(ent.label_ == "PERSON" for ent in doc.ents):
            return True

    return False


def scan_text(text: str) -> dict:
    """Return detailed scan result for a chunk."""
    regex_match = next((p.pattern for p in _PII_PATTERNS if p.search(text)), None)
    nlp = _get_nlp()
    person_entities: list[str] = []
    if nlp is not None:
        doc = nlp(text)
        person_entities = [ent.text for ent in doc.ents if ent.label_ == "PERSON"]
    return {
        "pii_detected": bool(regex_match or person_entities),
        "regex_match": regex_match,
        "person_entities": person_entities,
    }
