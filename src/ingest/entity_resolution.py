"""Entity resolution: threshold sweep with Jaro-Winkler similarity.

Two scoring approaches:
  A — name similarity only (Jaro-Winkler)
  B — name + email domain match + shared document count (weighted)

Canary guard: tests/canary_pairs.json lists known-distinct pairs.

Usage:
  score_pair_a(name1, name2) -> float
  score_pair_b(name1, email1, name2, email2, shared_docs) -> float
  threshold_sweep(pairs, thresholds) -> {threshold: (precision, recall)}
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

# ── Jaro-Winkler ─────────────────────────────────────────────────────────────

def _jaro(s1: str, s2: str) -> float:
    """Compute Jaro similarity between two strings."""
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0
    match_dist = max(len1, len2) // 2 - 1
    match_dist = max(match_dist, 0)
    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = transpositions = 0
    for i in range(len1):
        lo = max(0, i - match_dist)
        hi = min(i + match_dist + 1, len2)
        for j in range(lo, hi):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = s2_matches[j] = True
            matches += 1
            break
    if matches == 0:
        return 0.0
    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1
    return (matches / len1 + matches / len2 + (matches - transpositions / 2) / matches) / 3


def jaro_winkler(s1: str, s2: str, p: float = 0.1) -> float:
    """Jaro-Winkler similarity (higher weight for common prefix)."""
    jaro = _jaro(s1.lower(), s2.lower())
    prefix = 0
    for c1, c2 in zip(s1[:4], s2[:4], strict=False):
        if c1.lower() == c2.lower():
            prefix += 1
        else:
            break
    return jaro + prefix * p * (1 - jaro)


# ── Scoring approaches ────────────────────────────────────────────────────────

def score_pair_a(name1: str, name2: str) -> float:
    """Approach A: name similarity only."""
    return jaro_winkler(name1, name2)


def score_pair_b(
    name1: str,
    email1: str,
    name2: str,
    email2: str,
    shared_docs: int = 0,
) -> float:
    """Approach B: name (0.6) + email domain (0.3) + shared docs (0.1)."""
    name_score = jaro_winkler(name1, name2)
    # Extract domain safely: get everything after the last @ symbol
    def _get_domain(email: str) -> str:
        if "@" not in email:
            return ""
        parts = email.rsplit("@", 1)
        return parts[-1].lower() if len(parts) > 1 else ""
    domain1 = _get_domain(email1)
    domain2 = _get_domain(email2)
    domain_score = 1.0 if domain1 and domain1 == domain2 else 0.0
    doc_score = min(shared_docs / 5.0, 1.0)  # saturates at 5 shared docs
    return 0.6 * name_score + 0.3 * domain_score + 0.1 * doc_score


# ── Threshold sweep ───────────────────────────────────────────────────────────

class PrecisionRecall(NamedTuple):
    precision: float
    recall: float
    f1: float


def threshold_sweep(
    pairs: list[dict],
    thresholds: list[float],
    approach: str = "a",
) -> dict[float, PrecisionRecall]:
    """Sweep thresholds and compute precision/recall.

    pairs: list of {name1, name2, email1?, email2?, shared_docs?, is_duplicate}
    """
    results = {}
    for thresh in thresholds:
        tp = fp = fn = tn = 0
        for p in pairs:
            if approach == "b":
                score = score_pair_b(
                    p["name1"], p.get("email1", ""),
                    p["name2"], p.get("email2", ""),
                    p.get("shared_docs", 0),
                )
            else:
                score = score_pair_a(p["name1"], p["name2"])
            predicted = score >= thresh
            actual = bool(p["is_duplicate"])
            if predicted and actual:
                tp += 1
            elif predicted and not actual:
                fp += 1
            elif not predicted and actual:
                fn += 1
            else:
                tn += 1
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        results[thresh] = PrecisionRecall(precision=precision, recall=recall, f1=f1)
    return results


# ── Canary guard ──────────────────────────────────────────────────────────────

def load_canary_pairs(path: str | Path) -> list[dict]:
    """Load canary pairs from JSON file."""
    return json.loads(Path(path).read_text())


def check_canary_guard(canary_pairs: list[dict], threshold: float) -> list[dict]:
    """Return any canary (known-distinct) pairs incorrectly predicted as duplicates.

    Returns list of violations. Empty list = guard passes.
    """
    violations = []
    for pair in canary_pairs:
        score_a = score_pair_a(pair["name1"], pair["name2"])
        score_b = score_pair_b(
            pair["name1"], pair.get("email1", ""),
            pair["name2"], pair.get("email2", ""),
        )
        if score_a >= threshold or score_b >= threshold:
            violations.append({**pair, "score_a": score_a, "score_b": score_b})
    return violations
