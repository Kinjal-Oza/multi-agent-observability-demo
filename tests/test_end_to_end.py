"""End-to-end pipeline tests including all six stages."""
from agents.graph import run_investigation
from agents.state import AlertTrigger, new_state


def _trigger(service="payments-service", metric="p99_latency_ms", classification="application"):
    return AlertTrigger(
        alert_id="a-1", service=service, metric=metric,
        value=820.0, threshold=500.0, classification=classification,
    )


def test_full_pipeline_runs_and_produces_human_approval_request():
    state = new_state(incident_id="inc-1", trigger=_trigger())
    final = run_investigation(state)

    agents_in_trail = {s.agent for s in final["audit_trail"]}
    # All six stages must appear in the audit trail
    assert {"supervisor", "telemetry", "reasoning", "falsifier", "counterfactual", "action"} <= agents_in_trail

    assert len(final["telemetry_findings"]) >= 1
    assert final["causal_hypothesis"] is not None
    assert len(final["recommended_actions"]) == 1
    assert final["requires_human_approval"] is True


def test_full_pipeline_populates_falsification():
    """Falsification field must be populated."""
    state = new_state(incident_id="inc-2", trigger=_trigger())
    final = run_investigation(state)
    assert final.get("falsification") is not None
    assert final["falsification"].verdict in ("confirmed", "contested", "refuted")


def test_full_pipeline_hypothesis_has_provenance_bound_claims():
    """Provenance: every claim must cite at least one Finding ID."""
    state = new_state(incident_id="inc-3", trigger=_trigger())
    final = run_investigation(state)
    hyp = final["causal_hypothesis"]
    assert hyp is not None
    for claim in hyp.claims:
        assert len(claim.supporting_finding_ids) > 0


def test_full_pipeline_confidence_is_calibrated():
    """Calibrated confidence must have prior and modifier components."""
    state = new_state(incident_id="inc-4", trigger=_trigger())
    final = run_investigation(state)
    hyp = final["causal_hypothesis"]
    assert hyp is not None
    cc = hyp.confidence
    assert hasattr(cc, "raw_llm")
    assert hasattr(cc, "prior")
    assert hasattr(cc, "falsification_modifier")
    assert hasattr(cc, "final")
    assert 0.0 <= cc.final <= 1.0


def test_full_pipeline_network_classification():
    state = new_state(incident_id="inc-5", trigger=_trigger(
        service="api-gateway", metric="dns_latency_ms", classification="network",
    ))
    final = run_investigation(state)
    agents_in_trail = {s.agent for s in final["audit_trail"]}
    assert "falsifier" in agents_in_trail
    assert "counterfactual" in agents_in_trail


def test_full_pipeline_budget_assigned():
    trigger = AlertTrigger(
        alert_id="a-budget", service="payments-service", metric="p99_latency_ms",
        value=820.0, threshold=500.0, classification="application", severity="critical",
    )
    state = new_state(incident_id="inc-budget", trigger=trigger)
    final = run_investigation(state)
    assert final.get("budget") is not None
    assert final["budget"].initial_depth == 5
