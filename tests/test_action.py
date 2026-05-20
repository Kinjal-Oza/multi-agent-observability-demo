"""Tests for the action agent (Falsifier-aware remediation)."""
from agents.action import action_step
from agents.state import (
    AlertTrigger, CalibratedConfidence, Claim, FalsificationResult,
    Finding, Hypothesis, new_state,
)


def _make_calibrated(final: float = 0.72) -> CalibratedConfidence:
    return CalibratedConfidence(
        raw_llm=final, prior=0.3, falsification_modifier=0.8,
        final=final, components={},
    )


def _state_with_hypothesis(summary: str, confidence: float = 0.72,
                            falsification_verdict: str | None = None):
    trigger = AlertTrigger(
        alert_id="a-1", service="svc", metric="m", value=1.0,
        threshold=0.5, classification="application",
    )
    state = new_state(incident_id="inc-1", trigger=trigger)
    finding = Finding(source="prometheus", description="anomaly", severity="warning", raw={})
    state["telemetry_findings"] = [finding]

    claim = Claim(statement="root cause identified", supporting_finding_ids=[0])
    state["causal_hypothesis"] = Hypothesis(
        summary=summary,
        claims=[claim],
        confidence=_make_calibrated(confidence),
        supporting_finding_ids=[0],
    )
    state["confidence_score"] = confidence

    if falsification_verdict is not None:
        state["falsification"] = FalsificationResult(
            verdict=falsification_verdict,
            contradictions=[],
            falsification_score=0.08 if falsification_verdict == "confirmed" else 0.85,
        )
    return state


def test_action_recommends_rollback_for_connection_pool_hypothesis():
    state = _state_with_hypothesis("connection pool exhaustion likely", 0.72)
    out = action_step(state)
    assert len(out["recommended_actions"]) == 1
    assert "roll back" in out["recommended_actions"][0].description.lower()


def test_action_defaults_to_escalation_when_no_pattern_matches():
    state = _state_with_hypothesis("unknown anomaly with unique signature", 0.3)
    out = action_step(state)
    assert "escalate" in out["recommended_actions"][0].description.lower()


def test_action_always_requires_approval_by_default():
    state = _state_with_hypothesis("connection pool issue", 0.99)
    out = action_step(state)
    assert out["requires_human_approval"] is True
    assert out["recommended_actions"][0].requires_approval is True


def test_action_falsifier_veto_overrides_recommendation():
    """If falsifier refutes hypothesis, action must escalate immediately."""
    state = _state_with_hypothesis(
        "connection pool exhaustion", 0.95, falsification_verdict="refuted"
    )
    out = action_step(state)
    desc = out["recommended_actions"][0].description
    assert "ESCALATE IMMEDIATELY" in desc or "falsif" in desc.lower() or "refuted" in desc.lower()
    assert out["requires_human_approval"] is True


def test_action_falsifier_veto_sets_high_risk():
    state = _state_with_hypothesis(
        "connection pool exhaustion", 0.95, falsification_verdict="refuted"
    )
    out = action_step(state)
    assert out["recommended_actions"][0].risk_level == "high"


def test_action_confirmed_hypothesis_uses_normal_pattern():
    state = _state_with_hypothesis(
        "thermal throttling on subset of hosts", 0.72, falsification_verdict="confirmed"
    )
    out = action_step(state)
    desc = out["recommended_actions"][0].description.lower()
    assert "drain" in desc or "thermal" in desc or "escalate" in desc


def test_action_records_falsifier_verdict_in_audit():
    state = _state_with_hypothesis(
        "connection pool exhaustion", 0.72, falsification_verdict="confirmed"
    )
    out = action_step(state)
    action_steps = [s for s in out["audit_trail"] if s.agent == "action"]
    assert len(action_steps) >= 1
    assert "confirmed" in action_steps[-1].description
