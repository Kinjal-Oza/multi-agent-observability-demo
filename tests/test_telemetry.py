from agents.state import AlertTrigger, new_state
from agents.telemetry import telemetry_step


def test_telemetry_collects_findings_for_known_scenario():
    trigger = AlertTrigger(
        alert_id="a-1",
        service="payments-service",
        metric="p99_latency_ms",
        value=820.0,
        threshold=500.0,
        classification="application",
    )
    state = new_state(incident_id="inc-1", trigger=trigger)
    out = telemetry_step(state)
    findings = out["telemetry_findings"]

    # Should have the primary metric + dependencies + deploy + log signal
    sources = {f.source for f in findings}
    assert "prometheus" in sources
    assert "deploy_log" in sources
    assert "logs" in sources
    # At least one anomalous finding
    assert any(f.severity != "info" for f in findings)


def test_telemetry_unknown_service_does_not_crash():
    trigger = AlertTrigger(
        alert_id="a-2", service="nonexistent",
        metric="p99_latency_ms", value=1.0, threshold=0.5,
        classification="application",
    )
    state = new_state(incident_id="inc-2", trigger=trigger)
    out = telemetry_step(state)
    # Returns at least the primary metric query (even if benign)
    assert len(out["telemetry_findings"]) >= 1
