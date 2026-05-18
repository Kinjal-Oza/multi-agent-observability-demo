from agents.graph import run_investigation
from agents.state import AlertTrigger, new_state


def test_full_pipeline_runs_and_produces_human_approval_request():
    trigger = AlertTrigger(
        alert_id="a-1",
        service="payments-service",
        metric="p99_latency_ms",
        value=820.0,
        threshold=500.0,
        classification="application",
    )
    state = new_state(incident_id="inc-1", trigger=trigger)
    final = run_investigation(state)

    # All four agents ran
    agents_in_trail = {s.agent for s in final["audit_trail"]}
    assert {"supervisor", "telemetry", "reasoning", "action"} <= agents_in_trail

    # Findings collected
    assert len(final["telemetry_findings"]) >= 1
    # Hypothesis produced
    assert final["causal_hypothesis"] is not None
    # Action recommended
    assert len(final["recommended_actions"]) == 1
    # Human approval required (the non-negotiable gate)
    assert final["requires_human_approval"] is True
