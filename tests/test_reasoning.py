"""Tests for the reasoning agent (provenance-bound hypotheses)."""
from agents.reasoning import reasoning_step
from agents.state import AlertTrigger, Claim, Finding, new_state


def test_reasoning_produces_hypothesis_from_connection_pool_findings():
    trigger = AlertTrigger(
        alert_id="a-1",
        service="payments-service",
        metric="p99_latency_ms",
        value=820.0,
        threshold=500.0,
        classification="application",
    )
    state = new_state(incident_id="inc-1", trigger=trigger)
    state["telemetry_findings"] = [
        Finding(
            source="prometheus",
            description="connection pool utilization at 0.97",
            severity="warning",
            raw={},
        ),
        Finding(
            source="deploy_log",
            description="db-proxy v2.3.1 deployed recently",
            severity="info",
            raw={},
        ),
    ]
    out = reasoning_step(state)
    hyp = out["causal_hypothesis"]
    assert hyp is not None
    assert "pool" in hyp.summary.lower() or "deploy" in hyp.summary.lower()
    # v2: confidence is a CalibratedConfidence object
    assert 0.0 < hyp.confidence.final <= 1.0


def test_reasoning_confidence_falls_back_when_no_signal():
    trigger = AlertTrigger(
        alert_id="a-2", service="svc", metric="m", value=1.0,
        threshold=0.5, classification="application",
    )
    state = new_state(incident_id="inc-2", trigger=trigger)
    out = reasoning_step(state)
    hyp = out["causal_hypothesis"]
    assert hyp is not None
    assert hyp.confidence.final < 0.6  # fallback LLM gives 0.30 raw


def test_reasoning_produces_provenance_bound_claims():
    """Provenance: every Claim in the hypothesis must cite a Finding ID."""
    trigger = AlertTrigger(
        alert_id="a-3",
        service="payments-service",
        metric="p99_latency_ms",
        value=820.0,
        threshold=500.0,
        classification="application",
    )
    state = new_state(incident_id="inc-3", trigger=trigger)
    state["telemetry_findings"] = [
        Finding(source="prometheus", description="connection pool at 0.97",
                severity="warning", raw={}),
        Finding(source="deploy_log", description="db-proxy deployed",
                severity="info", raw={}),
        Finding(source="logs", description="no errors", severity="info", raw={}),
    ]
    out = reasoning_step(state)
    hyp = out["causal_hypothesis"]
    assert hyp is not None
    # Every claim must have at least one supporting_finding_id
    for claim in hyp.claims:
        assert isinstance(claim, Claim)
        assert len(claim.supporting_finding_ids) > 0, \
            f"Claim '{claim.statement}' has no provenance"


def test_reasoning_supporting_finding_ids_in_bounds():
    """Finding IDs in claims must be valid indices into telemetry_findings."""
    trigger = AlertTrigger(
        alert_id="a-4",
        service="payments-service",
        metric="p99_latency_ms",
        value=820.0,
        threshold=500.0,
        classification="application",
    )
    state = new_state(incident_id="inc-4", trigger=trigger)
    state["telemetry_findings"] = [
        Finding(source="prometheus", description="connection pool at 0.97",
                severity="warning", raw={}),
        Finding(source="deploy_log", description="db-proxy deployed",
                severity="info", raw={}),
    ]
    out = reasoning_step(state)
    hyp = out["causal_hypothesis"]
    if hyp and hyp.claims:
        n = len(out["telemetry_findings"])
        for claim in hyp.claims:
            for idx in claim.supporting_finding_ids:
                assert 0 <= idx < n, f"Finding ID {idx} out of bounds (n={n})"


def test_reasoning_calibrated_confidence_has_components():
    trigger = AlertTrigger(
        alert_id="a-5", service="payments-service", metric="p99_latency_ms",
        value=820.0, threshold=500.0, classification="application",
    )
    state = new_state(incident_id="inc-5", trigger=trigger)
    state["telemetry_findings"] = [
        Finding(source="prometheus", description="connection pool at 0.97",
                severity="warning", raw={}),
    ]
    out = reasoning_step(state)
    hyp = out["causal_hypothesis"]
    assert hyp is not None
    cc = hyp.confidence
    assert hasattr(cc, "raw_llm")
    assert hasattr(cc, "prior")
    assert hasattr(cc, "final")
    assert "formula" in cc.components
