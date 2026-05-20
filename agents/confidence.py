"""Calibrated confidence module.

Computes a posterior confidence score as a weighted ensemble of:
  (a) raw LLM self-reported confidence  — weight 0.4
  (b) historical prior P(cause|class)   — weight 0.4
  (c) falsification modifier (1 - score)— weight 0.2

The formula is deliberately simple and inspectable so it can be audited,
measured (Brier score, ECE), and specified without ambiguity.

Why not just use the LLM's confidence number?
  Guo et al. (2017) showed that modern neural networks are systematically
  overconfident and that raw self-reported confidence does not correlate
  well with empirical accuracy. This module addresses that by anchoring
  the score against two independent signals.
"""
from __future__ import annotations

from agents.state import CalibratedConfidence, InvestigationState


def calibrate(
    state: InvestigationState,
    raw_llm: float,
    hypothesis_summary: str = "",
) -> CalibratedConfidence:
    """Compute calibrated confidence for a hypothesis.

    Args:
        state: current investigation state (provides trigger.classification)
        raw_llm: confidence the LLM self-reported (0-1)
        hypothesis_summary: summary text for corpus prior lookup

    Returns:
        CalibratedConfidence with explicit component breakdown.
    """
    from corpus.causal_prior import prior_for

    classification = state["trigger"].classification
    summary = hypothesis_summary or ""

    # Component (b): historical prior from incident corpus
    prior = prior_for(classification, summary)

    # Component (c): falsification modifier — unknown at reasoning time,
    # so we start at the neutral midpoint (0.5 modifier = 0.5 penalty weight).
    # The Falsifier agent updates this retroactively via update_with_falsification().
    falsification_modifier = 0.5

    final = _compute(raw_llm, prior, falsification_modifier)

    return CalibratedConfidence(
        raw_llm=raw_llm,
        prior=prior,
        falsification_modifier=falsification_modifier,
        final=final,
        components={
            "formula": "0.4*raw_llm + 0.4*prior + 0.2*falsification_modifier",
            "weights": {"raw_llm": 0.4, "prior": 0.4, "falsification_modifier": 0.2},
        },
    )


def update_with_falsification(
    cal: CalibratedConfidence,
    falsification_score: float,
) -> CalibratedConfidence:
    """Recompute final confidence after the Falsifier has run.

    falsification_score: 0 = nothing contradicts, 1 = fully contradicted.
    The modifier is (1 - falsification_score): a fully-contradicted hypothesis
    gets a 0 modifier, dropping its weight contribution to 0.
    """
    modifier = max(0.0, 1.0 - falsification_score)
    final = _compute(cal.raw_llm, cal.prior, modifier)
    return CalibratedConfidence(
        raw_llm=cal.raw_llm,
        prior=cal.prior,
        falsification_modifier=modifier,
        final=final,
        components=dict(cal.components) | {"falsification_score": falsification_score},
    )


def _compute(raw_llm: float, prior: float, falsification_modifier: float) -> float:
    raw = 0.4 * raw_llm + 0.4 * prior + 0.2 * falsification_modifier
    return max(0.0, min(1.0, raw))
