"""Run a synthetic incident end-to-end and print what a human approver would see.

Demonstrates the six-stage pipeline:
  Supervisor → Telemetry → Reasoning → Falsifier → Counterfactual → Action

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
        severity="warning",
    )
    state = new_state(incident_id="inc-2026-0001", trigger=trigger)
    final = run_investigation(state)

    print("=" * 72)
    print(f"INCIDENT  : {final['incident_id']}")
    print(f"ALERT     : {trigger.service} / {trigger.metric} = {trigger.value} (> {trigger.threshold})")
    print(f"ROUTED TO : {final.get('routed_to', [])}")
    budget = final.get("budget")
    if budget:
        print(f"BUDGET    : depth={budget.initial_depth}, extensions_granted={budget.extensions_granted}")
    print("-" * 72)

    print("FINDINGS:")
    for i, f in enumerate(final.get("telemetry_findings", [])):
        print(f"  [{i}] ({f.source:11s}) [{f.severity:8s}] {f.description}")
    print("-" * 72)

    hyp = final.get("causal_hypothesis")
    if hyp:
        print(f"HYPOTHESIS  : {hyp.summary}")
        cc = hyp.confidence
        print(f"CONFIDENCE  : {cc.final:.2f}  "
              f"(raw_llm={cc.raw_llm:.2f}, prior={cc.prior:.2f}, "
              f"falsification_mod={cc.falsification_modifier:.2f})")
        print(f"CLAIMS ({len(hyp.claims)}):")
        for i, c in enumerate(hyp.claims):
            print(f"  [{i+1}] {c.statement}")
            print(f"       cites findings: {c.supporting_finding_ids}")
    print("-" * 72)

    falsification = final.get("falsification")
    if falsification:
        print(f"FALSIFIER   : verdict={falsification.verdict}, "
              f"score={falsification.falsification_score:.2f}")
        for i, contradiction in enumerate(falsification.contradictions):
            print(f"  CONTRADICTION {i+1}: {contradiction}")
    print("-" * 72)

    counterfactual = final.get("counterfactual")
    if counterfactual:
        print(f"COUNTERFACTUAL (method={counterfactual.simulator_method}, "
              f"confidence={counterfactual.prediction_confidence:.2f}):")
        for d in counterfactual.predicted_deltas:
            print(f"  {d.target}/{d.metric}: {d.expected_change} "
                  f"[{d.lower_bound:.0%}–{d.upper_bound:.0%} improvement]")
    print("-" * 72)

    print("RECOMMENDED ACTIONS:")
    for a in final.get("recommended_actions", []):
        print(f"  - [{a.risk_level:6s}] {a.description}")
        print(f"             rationale: {a.rationale}")
        print(f"             approval required: {a.requires_approval}")
    print("-" * 72)

    print("AUDIT TRAIL:")
    for step in final.get("audit_trail", []):
        print(f"  [{step.timestamp.isoformat()}] {step.agent:14s}  {step.description}")
    print("=" * 72)


if __name__ == "__main__":
    main()
