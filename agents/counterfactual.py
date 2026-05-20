"""Counterfactual Outcome Simulator.

Given a proposed remediation action and the current investigation state,
predicts the post-action system state BEFORE the human approves.

The human approver sees not just "what does the system recommend" but
"what does the system predict will happen if I approve this action."
This fundamentally changes the approver's decision context.

Design rationale (Pearl, 2009):
  Standard reasoning asks "what IS happening?" (observation).
  Counterfactual reasoning asks "what WOULD happen if we intervened?"
  (do-calculus). This is the formal basis for causal inference. Applying
  it to incident response — predicting post-remediation state rather than
  just diagnosing current state — is the novel contribution of this module.

Implementation:
  Primary path: deterministic rule table keyed by hypothesis substring.
  This is intentionally rule-based so it is testable, auditable, and the
  design can be specified without ambiguity. The alternative path (LLM-
  driven prediction for unmatched patterns) is also implemented and exposed.
"""
from __future__ import annotations

import re

from agents.llm import get_backend
from agents.state import (
    AgentStep,
    CounterfactualPrediction,
    InvestigationState,
    PredictedDelta,
)


# Deterministic causal rule table — primary prediction path.
# Keys: hypothesis summary substrings (matched via `in`, lowercased).
# Values: (list[PredictedDelta], prediction_confidence)
_CAUSAL_RULES: list[tuple[str, list[PredictedDelta], float]] = [
    (
        "connection pool",
        [
            PredictedDelta(
                target="payments-service", metric="p99_latency_ms",
                expected_change="drops 60–80% from current elevated value within ~2 min",
                lower_bound=0.60, upper_bound=0.80,
            ),
            PredictedDelta(
                target="db-proxy", metric="utilization",
                expected_change="recovers to baseline ~0.45",
                lower_bound=0.55, upper_bound=0.75,
            ),
            PredictedDelta(
                target="auth-service", metric="utilization",
                expected_change="no significant change expected",
                lower_bound=-0.05, upper_bound=0.05,
            ),
        ],
        0.78,
    ),
    (
        "thermal throttling",
        [
            PredictedDelta(
                target="affected-hosts", metric="cpu_throttle_ratio",
                expected_change="drops to 0 on drained hosts within 5 min",
                lower_bound=0.80, upper_bound=0.95,
            ),
            PredictedDelta(
                target="cluster", metric="request_throughput",
                expected_change="recovers after traffic rebalances (2–4 min)",
                lower_bound=0.60, upper_bound=0.85,
            ),
        ],
        0.70,
    ),
    (
        "dns resolution",
        [
            PredictedDelta(
                target="network", metric="dns_latency_ms",
                expected_change="drops 30–50% if misconfiguration is transient",
                lower_bound=0.30, upper_bound=0.50,
            ),
            PredictedDelta(
                target="services", metric="error_rate",
                expected_change="uncertain — depends on whether upstream resolver is also affected",
                lower_bound=0.10, upper_bound=0.60,
            ),
        ],
        0.48,
    ),
    (
        "deploy regression",
        [
            PredictedDelta(
                target="affected-service", metric="p99_latency_ms",
                expected_change="returns to pre-deploy baseline within 2–3 min post-rollback",
                lower_bound=0.65, upper_bound=0.85,
            ),
        ],
        0.75,
    ),
    (
        "regression",
        [
            PredictedDelta(
                target="affected-service", metric="p99_latency_ms",
                expected_change="returns to pre-deploy baseline within 2–3 min post-rollback",
                lower_bound=0.65, upper_bound=0.85,
            ),
        ],
        0.75,
    ),
    (
        "memory pressure",
        [
            PredictedDelta(
                target="affected-service", metric="memory_utilization",
                expected_change="drops to ~0.40 immediately post-restart",
                lower_bound=0.55, upper_bound=0.80,
            ),
            PredictedDelta(
                target="affected-service", metric="oom_event_rate",
                expected_change="drops to 0 immediately post-restart",
                lower_bound=0.90, upper_bound=1.00,
            ),
        ],
        0.72,
    ),
    (
        "certificate",
        [
            PredictedDelta(
                target="tls-layer", metric="tls_error_rate",
                expected_change="drops to 0 within seconds of certificate rotation",
                lower_bound=0.90, upper_bound=1.00,
            ),
        ],
        0.85,
    ),
    (
        "disk pressure",
        [
            PredictedDelta(
                target="disk-subsystem", metric="disk_io_wait",
                expected_change="drops 50–70% after volume expansion completes",
                lower_bound=0.50, upper_bound=0.70,
            ),
        ],
        0.68,
    ),
    (
        "dependency cascade",
        [
            PredictedDelta(
                target="local-service", metric="error_rate",
                expected_change="drops 40–60% after dependency isolation",
                lower_bound=0.40, upper_bound=0.60,
            ),
        ],
        0.58,
    ),
]


def _rule_based_predict(hypothesis_summary: str, action_description: str) -> tuple[list[PredictedDelta], float] | None:
    summary_lower = hypothesis_summary.lower()
    for key, deltas, confidence in _CAUSAL_RULES:
        if key in summary_lower:
            return deltas, confidence
    return None


def _llm_predict(state: InvestigationState) -> tuple[list[PredictedDelta], float]:
    """Fallback: ask the LLM to predict the outcome."""
    hypothesis = state["causal_hypothesis"]
    actions = state.get("recommended_actions", [])
    action_desc = actions[0].description if actions else "proposed remediation"

    prompt = (
        f"Counterfactual prediction task.\n"
        f"Hypothesis: {hypothesis.summary}\n"
        f"Proposed action: {action_desc}\n\n"
        f"Predict the post-action state changes for each affected metric.\n"
        f"Format:\n"
        f"DELTA 1: <target> <metric> | change: <description> | lower: <float> | upper: <float>\n"
        f"PREDICTION_CONFIDENCE: <float>\n"
        f"METHOD: llm_assisted\n"
    )

    backend = get_backend()
    raw = backend.complete(prompt)

    deltas: list[PredictedDelta] = []
    confidence = 0.30
    for line in raw.splitlines():
        line = line.strip()
        if line.upper().startswith("DELTA"):
            # DELTA N: <target> <metric> | change: ... | lower: <f> | upper: <f>
            parts = re.split(r"\|\s*", line, flags=re.IGNORECASE)
            if len(parts) >= 3:
                header = re.sub(r"DELTA\s+\d+:\s*", "", parts[0], flags=re.IGNORECASE).split()
                target = header[0] if header else "unknown"
                metric = header[1] if len(header) > 1 else "unknown"
                change = parts[1].replace("change:", "").strip() if len(parts) > 1 else ""
                lower = 0.0
                upper = 1.0
                for p in parts[2:]:
                    if p.lower().startswith("lower:"):
                        try:
                            lower = float(p.split(":", 1)[1].strip())
                        except ValueError:
                            pass
                    elif p.lower().startswith("upper:"):
                        try:
                            upper = float(p.split(":", 1)[1].strip())
                        except ValueError:
                            pass
                deltas.append(PredictedDelta(target=target, metric=metric,
                                             expected_change=change,
                                             lower_bound=lower, upper_bound=upper))
        elif line.upper().startswith("PREDICTION_CONFIDENCE:"):
            try:
                confidence = float(line.split(":", 1)[1].strip())
            except ValueError:
                pass

    if not deltas:
        deltas = [PredictedDelta(
            target="primary-service", metric="primary-metric",
            expected_change="unknown — no matching rule", lower_bound=0.0, upper_bound=1.0,
        )]
    return deltas, max(0.0, min(1.0, confidence))


def counterfactual_step(state: InvestigationState) -> InvestigationState:
    hypothesis = state.get("causal_hypothesis")
    actions = state.get("recommended_actions", [])
    action_desc = actions[0].description if actions else "proposed remediation"

    if hypothesis is None:
        state.setdefault("audit_trail", []).append(AgentStep(
            agent="counterfactual",
            description="Skipped — no hypothesis available for counterfactual simulation.",
        ))
        return state

    # Try rule-based first
    rule_result = _rule_based_predict(hypothesis.summary, action_desc)
    if rule_result is not None:
        deltas, confidence = rule_result
        method = "rule_based"
    else:
        deltas, confidence = _llm_predict(state)
        method = "llm_assisted"

    prediction = CounterfactualPrediction(
        action_description=action_desc,
        predicted_deltas=deltas,
        prediction_confidence=confidence,
        simulator_method=method,  # type: ignore[arg-type]
    )
    state["counterfactual"] = prediction

    delta_summary = "; ".join(
        f"{d.target}/{d.metric}: [{d.lower_bound:.0%}–{d.upper_bound:.0%}] improvement"
        for d in deltas[:2]
    )
    state.setdefault("audit_trail", []).append(AgentStep(
        agent="counterfactual",
        description=(
            f"Simulated outcome via {method} (confidence={confidence:.2f}). "
            f"Predicted deltas: {delta_summary}"
        ),
    ))
    return state
