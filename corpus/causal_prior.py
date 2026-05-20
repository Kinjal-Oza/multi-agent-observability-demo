"""Learned causal prior from the synthetic incident corpus.

Computes P(cause_pattern | classification) from the frequency table in
incidents.jsonl. Returns a prior probability used by the confidence
calibration module to modulate raw LLM confidence.

This is the "learned prior" used by the calibrated-confidence module. In a production
system, this table would be updated continuously from resolved incidents.
"""
from __future__ import annotations

import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

_CORPUS_PATH = Path(__file__).parent / "incidents.jsonl"


@lru_cache(maxsize=1)
def _load_frequency_table() -> dict[str, dict[str, float]]:
    """Load and compute P(cause | classification) from the corpus.

    Returns: {classification: {cause_pattern: probability}}
    """
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    totals: dict[str, int] = defaultdict(int)

    with _CORPUS_PATH.open() as f:
        for line in f:
            inc = json.loads(line)
            cls = inc["classification"]
            cause = inc["true_cause_pattern"]
            counts[cls][cause] += 1
            totals[cls] += 1

    table: dict[str, dict[str, float]] = {}
    for cls, cause_counts in counts.items():
        total = totals[cls]
        table[cls] = {cause: count / total for cause, count in cause_counts.items()}
    return table


def prior_for(classification: str, hypothesis_summary: str) -> float:
    """Return P(hypothesis_cause | classification) from the corpus prior.

    Matches hypothesis_summary against known cause pattern keywords.
    Falls back to a uniform prior (1/8) if nothing matches.
    """
    table = _load_frequency_table()
    cls_priors = table.get(classification, {})

    summary_lower = hypothesis_summary.lower()
    best_match_prob = 0.0

    for cause_pattern, prob in cls_priors.items():
        # Match on the first significant word of the cause pattern
        keywords = cause_pattern.split()
        if any(kw in summary_lower for kw in keywords):
            if prob > best_match_prob:
                best_match_prob = prob

    # Uniform fallback: 1 / number_of_cause_patterns
    return best_match_prob if best_match_prob > 0.0 else 0.125


def all_priors_for(classification: str) -> dict[str, float]:
    """Return full prior distribution for a classification type."""
    return _load_frequency_table().get(classification, {})
