"""Run a synthetic incident end-to-end and print what a human approver would see.

Usage:
    python -m examples.run_synthetic_incident
"""
from __future__ import annotations

from agents.graph import run_investigation
from agents.state import AlertTrigger, new_state


def main() -> None:
    trigger = AlertTrigger(
        alert_id="alert-001",
        service="payments-service",
        metric="p99_latency_ms",
        value=820.0,
        threshold=500.0,
        classification="application",
    )
    state = new_state(incident_id="inc-2026-0001", trigger=trigger)
    final = run_investigation(state)

    print("=" * 72)
    print(f"INCIDENT  : {final['incident_id']}")
    print(f"ALERT     : {trigger.service} / {trigger.metric} = {trigger.value} (> {trigger.threshold})")
    print(f"ROUTED TO : {final.get('routed_to', [])}")
    print("-" * 72)
    print("FINDINGS:")
    for i, f in enumerate(final.get("telemetry_findings", [])):
        print(f"  [{i}] ({f.source:11s}) [{f.severity:8s}] {f.description}")
    print("-" * 72)
    hyp = final.get("causal_hypothesis")
    if hyp:
        print(f"HYPOTHESIS  : {hyp.summary}")
        print(f"CONFIDENCE  : {hyp.confidence:.2f}")
        print(f"SUPPORTING  : {hyp.supporting_finding_ids}")
    print("-" * 72)
    print("RECOMMENDED ACTIONS:")
    for a in final.get("recommended_actions", []):
        print(f"  - [{a.risk_level:6s}] {a.description}")
        print(f"             rationale: {a.rationale}")
        print(f"             approval required: {a.requires_approval}")
    print("-" * 72)
    print("AUDIT TRAIL:")
    for step in final.get("audit_trail", []):
        print(f"  [{step.timestamp.isoformat()}] {step.agent:11s}  {step.description}")
    print("=" * 72)


if __name__ == "__main__":
    main()
