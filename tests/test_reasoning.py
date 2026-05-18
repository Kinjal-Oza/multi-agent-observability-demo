from agents.reasoning import reasoning_step
from agents.state import AlertTrigger, Finding, new_state


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
    assert 0.0 < hyp.confidence <= 1.0


def test_reasoning_confidence_falls_back_when_no_signal():
    trigger = AlertTrigger(
        alert_id="a-2", service="svc", metric="m", value=1.0,
        threshold=0.5, classification="application",
    )
    state = new_state(incident_id="inc-2", trigger=trigger)
    # No findings → fallback hypothesis
    out = reasoning_step(state)
    hyp = out["causal_hypothesis"]
    assert hyp is not None
    assert hyp.confidence < 0.5
