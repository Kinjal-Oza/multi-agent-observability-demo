from agents.action import action_step
from agents.state import AlertTrigger, Hypothesis, new_state


def _state_with_hypothesis(summary: str, confidence: float):
    trigger = AlertTrigger(
        alert_id="a-1", service="svc", metric="m", value=1.0,
        threshold=0.5, classification="application",
    )
    state = new_state(incident_id="inc-1", trigger=trigger)
    state["causal_hypothesis"] = Hypothesis(
        summary=summary, confidence=confidence, supporting_finding_ids=[]
    )
    state["confidence_score"] = confidence
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
    # Even at 0.99 confidence, default config keeps the human gate closed.
    assert out["requires_human_approval"] is True
    assert out["recommended_actions"][0].requires_approval is True
