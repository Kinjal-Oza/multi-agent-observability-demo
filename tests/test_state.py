from agents.state import AlertTrigger, AgentStep, new_state


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
    # Audit trail starts with the system "opened" step
    assert len(state["audit_trail"]) == 1
    assert state["audit_trail"][0].agent == "system"


def test_agent_step_has_timestamp():
    step = AgentStep(agent="supervisor", description="routed")
    assert step.timestamp is not None
