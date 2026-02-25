"""Evaluate PII scanner accuracy against the labeled corpus (Story 1.7).

Accuracy targets (regex-only, spaCy disabled in test env):
  Recall on PII chunks:    >= 90%
  Precision on clean text: >= 92%
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

CORPUS_PATH = Path(__file__).parent / "pii_test_corpus" / "corpus.json"


@pytest.fixture(scope="module")
def corpus():
    return json.loads(CORPUS_PATH.read_text())


def test_corpus_has_correct_shape(corpus):
    assert len(corpus["pii"]) == 50
    assert len(corpus["clean"]) == 50
    for chunk in corpus["pii"]:
        assert "id" in chunk and "text" in chunk and "signals" in chunk
    for chunk in corpus["clean"]:
        assert "id" in chunk and "text" in chunk and "signals" in chunk


def test_pii_corpus_recall(corpus):
    """PII scanner must detect >= 90% of PII-positive chunks."""
    from src.ingest.pii import has_pii

    pii_chunks = corpus["pii"]
    detected = sum(1 for c in pii_chunks if has_pii(c["text"]))
    recall = detected / len(pii_chunks)

    print(f"\nPII recall: {detected}/{len(pii_chunks)} = {recall:.1%}")
    assert recall >= 0.90, (
        f"PII recall {recall:.1%} below 90% threshold — "
        f"missed: {[c['id'] for c in pii_chunks if not has_pii(c['text'])]}"
    )


def test_pii_corpus_precision(corpus):
    """PII scanner must not flag >= 92% of clean chunks."""
    from src.ingest.pii import has_pii

    clean_chunks = corpus["clean"]
    false_positives = [c for c in clean_chunks if has_pii(c["text"])]
    precision = 1.0 - len(false_positives) / len(clean_chunks)

    print(f"\nClean precision: {len(clean_chunks) - len(false_positives)}/{len(clean_chunks)} = {precision:.1%}")
    assert precision >= 0.92, (
        f"False-positive rate {1-precision:.1%} above 8% threshold — "
        f"false positives: {[c['id'] for c in false_positives]}"
    )


def test_pii_ssn_chunks_all_detected(corpus):
    """Every chunk with SSN signal must be detected."""
    from src.ingest.pii import has_pii

    ssn_chunks = [c for c in corpus["pii"] if "ssn" in c["signals"]]
    missed = [c["id"] for c in ssn_chunks if not has_pii(c["text"])]
    assert not missed, f"SSN chunks not detected: {missed}"


def test_pii_credit_card_chunks_all_detected(corpus):
    """Every chunk with credit_card signal must be detected."""
    from src.ingest.pii import has_pii

    cc_chunks = [c for c in corpus["pii"] if "credit_card" in c["signals"]]
    missed = [c["id"] for c in cc_chunks if not has_pii(c["text"])]
    assert not missed, f"Credit card chunks not detected: {missed}"


def test_pii_medical_term_chunks_detected(corpus):
    """Chunks with medical_term signal detected at >= 95%."""
    from src.ingest.pii import has_pii

    med_chunks = [c for c in corpus["pii"] if "medical_term" in c["signals"]]
    detected = sum(1 for c in med_chunks if has_pii(c["text"]))
    if med_chunks:
        recall = detected / len(med_chunks)
        assert recall >= 0.95, f"Medical term recall {recall:.1%} < 95%"


def test_pii_corpus_f1(corpus):
    """F1 score across the corpus must be >= 0.90."""
    from src.ingest.pii import has_pii

    tp = sum(1 for c in corpus["pii"] if has_pii(c["text"]))
    fp = sum(1 for c in corpus["clean"] if has_pii(c["text"]))
    fn = len(corpus["pii"]) - tp

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    print(f"\nF1={f1:.3f}  precision={precision:.3f}  recall={recall:.3f}")
    assert f1 >= 0.90, f"F1 {f1:.3f} below 0.90 threshold"
