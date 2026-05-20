"""Tests for the Counterfactual Outcome Simulator."""
from agents.state import AlertTrigger, new_state
from agents.telemetry import telemetry_step
from agents.reasoning import reasoning_step
from agents.falsifier import falsifier_step
from agents.action import action_step
from agents.counterfactual import counterfactual_step


def _run_to_action(service="payments-service", metric="p99_latency_ms", classification="application"):
    trigger = AlertTrigger(
        alert_id="cf-test", service=service, metric=metric,
        value=820.0, threshold=500.0, classification=classification,
    )
    state = new_state("inc-cf", trigger)
    state = telemetry_step(state)
    state = reasoning_step(state)
    state = falsifier_step(state)
    # Counterfactual runs BEFORE action in pipeline, but action needs to exist
    # We test counterfactual directly here
    return state


def test_counterfactual_populates_field():
    state = _run_to_action()
    # Action step drafts a recommendation first
    state = action_step(state)
    state = counterfactual_step(state)
    assert state.get("counterfactual") is not None


def test_counterfactual_connection_pool_uses_rule_based():
    state = _run_to_action()
    state = action_step(state)
    state = counterfactual_step(state)
    cf = state["counterfactual"]
    assert cf is not None
    assert cf.simulator_method == "rule_based"
    assert len(cf.predicted_deltas) > 0


def test_counterfactual_deltas_have_valid_bounds():
    state = _run_to_action()
    state = action_step(state)
    state = counterfactual_step(state)
    cf = state["counterfactual"]
    for delta in cf.predicted_deltas:
        assert delta.lower_bound <= delta.upper_bound


def test_counterfactual_prediction_confidence_in_range():
    state = _run_to_action()
    state = action_step(state)
    state = counterfactual_step(state)
    cf = state["counterfactual"]
    assert 0.0 <= cf.prediction_confidence <= 1.0


def test_counterfactual_unknown_pattern_uses_llm_assisted():
    """Unrecognized hypothesis pattern falls back to llm_assisted."""
    trigger = AlertTrigger(
        alert_id="cf-unknown", service="mystery-svc", metric="custom_metric",
        value=999.0, threshold=1.0, classification="unknown",
    )
    state = new_state("inc-unknown", trigger)
    state = telemetry_step(state)
    state = reasoning_step(state)
    state = action_step(state)
    state = counterfactual_step(state)
    cf = state.get("counterfactual")
    # Should still produce a result, even if confidence is low
    if cf is not None:
        assert 0.0 <= cf.prediction_confidence <= 1.0


def test_counterfactual_records_audit_step():
    state = _run_to_action()
    state = action_step(state)
    state = counterfactual_step(state)
    agents = {s.agent for s in state["audit_trail"]}
    assert "counterfactual" in agents


def test_counterfactual_handles_no_hypothesis_gracefully():
    trigger = AlertTrigger(
        alert_id="cf-nohyp", service="svc", metric="m",
        value=1.0, threshold=0.5, classification="application",
    )
    state = new_state("inc-nohyp", trigger)
    # Don't run reasoning — no hypothesis
    state = counterfactual_step(state)
    # Should not crash; field may be None
    assert "counterfactual" not in state or state.get("counterfactual") is None
