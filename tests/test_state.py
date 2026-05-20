"""Tests for the shared state schema."""
import pytest
from agents.state import (
    AlertTrigger, AgentStep, Claim, CalibratedConfidence,
    FalsificationResult, CounterfactualPrediction, PredictedDelta,
    InvestigationBudget, new_state,
)


def test_new_state_initializes_required_fields():
    trigger = AlertTrigger(
        alert_id="a-1", service="svc", metric="m", value=1.0,
        threshold=0.5, classification="application",
    )
    state = new_state(incident_id="inc-1", trigger=trigger)
    assert state["incident_id"] == "inc-1"
    assert state["trigger"] is trigger
    assert state["telemetry_findings"] == []
    assert state["recommended_actions"] == []
    assert state["confidence_score"] == 0.0
    assert state["requires_human_approval"] is True
    assert len(state["audit_trail"]) == 1
    assert state["audit_trail"][0].agent == "system"


def test_agent_step_has_timestamp():
    step = AgentStep(agent="supervisor", description="routed")
    assert step.timestamp is not None


# --- Provenance enforcement ---

def test_claim_requires_supporting_findings():
    with pytest.raises(ValueError, match="no supporting finding IDs"):
        Claim(statement="latency elevated", supporting_finding_ids=[])


def test_claim_valid():
    c = Claim(statement="latency elevated", supporting_finding_ids=[0, 2])
    assert c.supporting_finding_ids == [0, 2]


def test_calibrated_confidence_fields():
    cc = CalibratedConfidence(
        raw_llm=0.72, prior=0.45, falsification_modifier=0.8,
        final=0.63, components={"formula": "test"},
    )
    assert 0.0 <= cc.final <= 1.0
    assert cc.raw_llm == 0.72


def test_falsification_result_verdicts():
    for verdict in ("confirmed", "contested", "refuted"):
        fr = FalsificationResult(
            verdict=verdict, contradictions=[], falsification_score=0.1,
        )
        assert fr.verdict == verdict


def test_investigation_budget_fields():
    budget = InvestigationBudget(initial_depth=5, remaining=5)
    assert budget.extensions_granted == 0
    assert budget.MAX_EXTENSIONS == 2


def test_new_state_initializes_budget():
    trigger = AlertTrigger(
        alert_id="t1", service="svc", metric="m", value=1.0,
        threshold=0.5, classification="application", severity="critical",
    )
    state = new_state("inc-1", trigger)
    assert state["budget"].initial_depth == 5
    assert state["budget"].remaining == 5


def test_new_state_warning_budget():
    trigger = AlertTrigger(
        alert_id="t2", service="svc", metric="m", value=1.0,
        threshold=0.5, classification="network", severity="warning",
    )
    state = new_state("inc-2", trigger)
    assert state["budget"].initial_depth == 3


def test_predicted_delta_fields():
    d = PredictedDelta(
        target="svc", metric="p99", expected_change="drops 60-80%",
        lower_bound=0.60, upper_bound=0.80,
    )
    assert d.lower_bound < d.upper_bound


def test_counterfactual_prediction_fields():
    cp = CounterfactualPrediction(
        action_description="rollback",
        predicted_deltas=[],
        prediction_confidence=0.75,
        simulator_method="rule_based",
    )
    assert cp.simulator_method == "rule_based"
