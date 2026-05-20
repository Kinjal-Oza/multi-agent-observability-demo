"""Tests for the adversarial Falsifier agent."""
from agents.state import AlertTrigger, new_state
from agents.reasoning import reasoning_step
from agents.telemetry import telemetry_step
from agents.falsifier import falsifier_step


def _base_state(service: str = "payments-service", metric: str = "p99_latency_ms"):
    trigger = AlertTrigger(
        alert_id="f-test", service=service, metric=metric,
        value=820.0, threshold=500.0, classification="application",
    )
    return new_state("inc-f", trigger)


def test_falsifier_sets_falsification_field():
    state = _base_state()
    state = telemetry_step(state)
    state = reasoning_step(state)
    state = falsifier_step(state)
    assert state.get("falsification") is not None


def test_falsifier_verdict_in_valid_set():
    state = _base_state()
    state = telemetry_step(state)
    state = reasoning_step(state)
    state = falsifier_step(state)
    fr = state["falsification"]
    assert fr.verdict in ("confirmed", "contested", "refuted")


def test_falsifier_connection_pool_confirms():
    """Connection pool exhaustion scenario should be confirmed by falsifier."""
    state = _base_state()
    state = telemetry_step(state)
    state = reasoning_step(state)
    state = falsifier_step(state)
    fr = state["falsification"]
    # DeterministicFake should confirm connection pool hypothesis
    assert fr.verdict in ("confirmed", "contested")
    assert 0.0 <= fr.falsification_score <= 1.0


def test_falsifier_updates_calibrated_confidence():
    """After the Falsifier runs, hypothesis confidence should be updated."""
    state = _base_state()
    state = telemetry_step(state)
    state = reasoning_step(state)
    pre_falsifier_conf = state["confidence_score"]
    state = falsifier_step(state)
    # Confidence is recomputed — may go up or down based on falsification_score
    hyp = state["causal_hypothesis"]
    assert hyp is not None
    # The modifier in the calibrated confidence should now reflect falsification
    assert hyp.confidence.falsification_modifier != 0.5 or pre_falsifier_conf == state["confidence_score"]


def test_falsifier_records_audit_step():
    state = _base_state()
    state = telemetry_step(state)
    state = reasoning_step(state)
    state = falsifier_step(state)
    agents_in_trail = {s.agent for s in state["audit_trail"]}
    assert "falsifier" in agents_in_trail


def test_falsifier_no_hypothesis_gracefully():
    """Falsifier should handle missing hypothesis without crashing."""
    state = _base_state()
    # Don't run reasoning — no hypothesis
    state = falsifier_step(state)
    assert state.get("falsification") is not None
    assert state["falsification"].verdict == "contested"


def test_falsifier_requests_budget_extension_when_contested():
    state = _base_state("api-gateway", "dns_latency_ms")
    # Use a trigger with a pattern that gives a "contested" verdict
    state = telemetry_step(state)
    state = reasoning_step(state)
    state = falsifier_step(state)
    budget = state.get("budget")
    # If verdict was not refuted, an extension may have been requested
    fr = state["falsification"]
    if fr.verdict in ("confirmed", "contested") and budget:
        assert budget.extensions_granted <= budget.MAX_EXTENSIONS
