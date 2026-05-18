from agents.state import AlertTrigger, new_state
from agents.supervisor import ROUTING_TABLE, supervisor_step


def _state(classification: str):
    trigger = AlertTrigger(
        alert_id="a-1", service="svc", metric="m", value=1.0,
        threshold=0.5, classification=classification,
    )
    return new_state(incident_id="inc-1", trigger=trigger)


def test_supervisor_routes_application_to_full_chain():
    state = _state("application")
    out = supervisor_step(state)
    assert out["routed_to"] == ROUTING_TABLE["application"]


def test_supervisor_routes_network_to_telemetry_reasoning():
    state = _state("network")
    out = supervisor_step(state)
    assert "telemetry" in out["routed_to"]
    assert "reasoning" in out["routed_to"]


def test_supervisor_falls_back_to_unknown_when_classification_missing():
    state = _state("unknown")
    out = supervisor_step(state)
    assert out["routed_to"] == ROUTING_TABLE["unknown"]


def test_supervisor_appends_audit_step():
    state = _state("application")
    initial = len(state["audit_trail"])
    out = supervisor_step(state)
    assert len(out["audit_trail"]) == initial + 1
    assert out["audit_trail"][-1].agent == "supervisor"
