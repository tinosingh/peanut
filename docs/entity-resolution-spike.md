# Entity Resolution Spike — Sprint 5

**Status:** Documented (threshold sweep requires labeled person pairs dataset)
**Story:** 3.2 — Jaro-Winkler threshold validation

## Objective

Determine the optimal threshold for entity deduplication and which scoring approach
minimises false merges while maintaining acceptable recall.

## Approach A — Jaro-Winkler on display_name only

```python
score = jaro_winkler(name_a.lower(), name_b.lower())
```

**Characteristics:**
- Fast (pure string comparison)
- Works well for spelling variants ("Alice Smith" vs "Alicia Smith")
- Fails on format differences ("Alice Smith" vs "Smith, Alice")
- No signal from shared email domain or document co-occurrence

## Approach B — Combined score (Implemented)

```python
score = 0.6 * jaro_winkler(name_a, name_b)
       + 0.3 * (1.0 if same_email_domain else 0.0)
       + 0.1 * min(shared_doc_count / 5, 1.0)
```

**Rationale:**
- Name similarity carries most weight (0.6)
- Exact email domain match is strong corroborating signal (0.3)
- Document co-occurrence reduces false positives (0.1, capped at 5 shared docs)

## Threshold Decision

Default: **0.90** (validated against canary pairs)

| Threshold | Expected Precision | Expected Recall | Recommendation |
|-----------|-------------------|-----------------|----------------|
| 0.99      | Very high         | Very low        | Miss obvious variants |
| 0.95      | High              | Medium          | Conservative |
| **0.90**  | **Good**          | **Good**        | **Default** |
| 0.85      | Medium            | High            | Risk of false merges |
| 0.80      | Low               | Very high       | Too aggressive |

## Canary Guard

`tests/canary_pairs.json` contains 15 known-distinct person pairs. After every
resolution run, the canary guard asserts none of them share a `merged_into` chain.

The guard prevents regression — if the threshold is lowered or the scoring function
changes, known-distinct pairs must not be merged.

## Implementation

- `src/ingest/entity_resolution.py`: `score_pair_a()`, `score_pair_b()`, `threshold_sweep()`
- `tests/canary_pairs.json`: 15 known-distinct pairs
- `tests/test_epic3.py`: canary guard tests

## Running a Threshold Sweep

```python
from src.ingest.entity_resolution import threshold_sweep
# pairs = list of (name_a, email_a, name_b, email_b, is_duplicate) tuples
results = threshold_sweep(pairs, lo=0.80, hi=0.99, step=0.01)
# Returns precision/recall at each threshold
```

## Future Work

If empirical testing on a real email archive shows poor results at 0.90:
1. Build a labeled dataset of 50 duplicate + 50 distinct person pairs from real data
2. Run `threshold_sweep()` and plot precision/recall curves
3. Update `THRESHOLD = 0.85` in `src/api/entities.py` based on results
4. Update this document with actual measured values
