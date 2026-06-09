"""Thermal throttling incident scenario.

Demonstrates the pipeline handling a GPU/CPU thermal event that manifests
as latency degradation — a class of incident where the root cause is
hardware-level but the symptom appears in application metrics.

The trigger looks like a standard p99 latency alert. The telemetry agent
finds elevated temperature readings alongside the latency spike. The
reasoning agent connects the thermal event to the performance degradation
via the throttling pathway.

Usage:
    python -m examples.run_thermal_incident
"""
from __future__ import annotations

from agents.graph import run_investigation
from agents.state import AlertTrigger, new_state


def main() -> None:
    # Alert fires on compute-service latency.
    # Root cause: thermal throttling on inference hosts after cooling unit fault.
    trigger = AlertTrigger(
        alert_id="alert-thermal-001",
        service="compute-service",
        metric="p99_latency_ms",
        value=1240.0,
        threshold=600.0,
        classification="infra",
        severity="critical",
    )
    state = new_state(incident_id="inc-2026-thermal-001", trigger=trigger)
    final = run_investigation(state)

    print("=" * 72)
    print(f"INCIDENT  : {final['incident_id']}")
    print(f"ALERT     : {trigger.service} / {trigger.metric} = {trigger.value} (> {trigger.threshold})")
    print(f"CLASS     : {trigger.classification} / {trigger.severity}")
    print(f"ROUTED TO : {final.get('routed_to', [])}")
    budget = final.get("budget")
    if budget:
        print(f"BUDGET    : depth={budget.initial_depth}, extensions={budget.extensions_granted}")
    print("-" * 72)

    print("FINDINGS:")
    for i, f in enumerate(final.get("telemetry_findings", [])):
        flag = " *** THERMAL ***" if "thermal" in f.description.lower() or "temp" in f.description.lower() else ""
        print(f"  [{i}] ({f.source:11s}) [{f.severity:8s}] {f.description}{flag}")
    print("-" * 72)

    hyp = final.get("causal_hypothesis")
    if hyp:
        print(f"HYPOTHESIS  : {hyp.summary}")
        cc = hyp.confidence
        print(f"CONFIDENCE  : {cc.final:.2f}  "
              f"(raw_llm={cc.raw_llm:.2f}, prior={cc.prior:.2f}, "
              f"falsification_mod={cc.falsification_modifier:.2f})")
        print(f"CLAIMS ({len(hyp.claims)}):")
        for c in hyp.claims:
            print(f"  - {c.text}  [confidence={c.confidence:.2f}]")
        print(f"  Supported by findings: {hyp.supported_by_finding_ids}")
    print("-" * 72)

    falsification = final.get("falsification_result")
    if falsification:
        print(f"FALSIFICATION : {falsification.verdict.upper()}")
        if falsification.contested_claims:
            print(f"  Contested   : {falsification.contested_claims}")
        if falsification.supporting_evidence:
            print(f"  Supporting  : {falsification.supporting_evidence}")

    print("-" * 72)
    counterfactual = final.get("counterfactual_prediction")
    if counterfactual:
        print(f"COUNTERFACTUAL ({counterfactual.method}):")
        print(f"  Predicted latency post-action : {counterfactual.predicted_state.get('p99_latency_ms', 'n/a')}")
        print(f"  Confidence                    : {counterfactual.confidence:.2f}")
        if counterfactual.caveats:
            for caveat in counterfactual.caveats:
                print(f"  Caveat: {caveat}")

    print("-" * 72)
    rec = final.get("action_recommendation")
    if rec:
        print(f"RECOMMENDED ACTION : {rec.action_type.upper()} — {rec.description}")
        print(f"  Risk              : {rec.risk_level} | Auto-executable: {rec.auto_executable}")
        print(f"  Rationale         : {rec.rationale}")
        print(f"  Approval required : {not rec.auto_executable}")
    print("=" * 72)


if __name__ == "__main__":
    main()
