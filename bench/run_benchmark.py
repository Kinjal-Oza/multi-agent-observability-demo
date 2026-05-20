"""Run the full benchmark against the synthetic incident corpus.

Usage:
    python -m bench.run_benchmark [--limit N]

Runs the six-stage pipeline on every scenario in corpus/incidents.jsonl
using the DeterministicFake LLM backend. Total runtime < 30s.

The numbers printed here are the ones cited in the article and
cross-referenced in docs/methodology.md.
"""
from __future__ import annotations

import argparse
import sys
import time

from agents.reasoning import reasoning_step
from agents.falsifier import falsifier_step
from agents.counterfactual import counterfactual_step
from agents.action import action_step
from agents.supervisor import supervisor_step
from agents.state import new_state
from bench.metrics import (
    action_precision,
    brier_score,
    expected_calibration_error,
    falsifier_precision,
    falsifier_recall,
    hypothesis_accuracy,
)
from bench.scenarios import load_corpus


def run(limit: int | None = None) -> dict:
    scenarios = load_corpus(limit=limit)
    n = len(scenarios)
    print(f"Running benchmark on {n} scenarios...")

    confidences: list[float] = []
    outcomes: list[int] = []
    predicted_verdicts: list[str] = []
    true_verdicts: list[str] = []
    recommended: list[str] = []
    ground_truth: list[str] = []
    hyp_summaries: list[str] = []
    true_causes: list[str] = []

    t0 = time.monotonic()
    for s in scenarios:
        state = new_state(incident_id=s.incident_id, trigger=s.trigger)
        # Inject corpus findings directly — bypasses mock telemetry so the
        # benchmark measures reasoning/falsifier/action quality, not mock coverage.
        state["telemetry_findings"] = s.findings
        state = supervisor_step(state)
        state = reasoning_step(state)
        state = falsifier_step(state)
        state = action_step(state)
        state = counterfactual_step(state)
        final = state

        hyp = final.get("causal_hypothesis")
        conf = final.get("confidence_score", 0.0)

        # Determine if hypothesis was correct
        summary = hyp.summary if hyp else ""
        correct = int(any(kw in summary.lower() for kw in s.true_cause_pattern.split()))

        confidences.append(conf)
        outcomes.append(correct)

        falsification = final.get("falsification")
        predicted_verdicts.append(falsification.verdict if falsification else "contested")
        true_verdicts.append(s.expected_falsifier_verdict)

        rec_actions = final.get("recommended_actions", [])
        rec_desc = rec_actions[0].description if rec_actions else ""
        recommended.append(rec_desc)
        ground_truth.append(s.ground_truth_action)

        hyp_summaries.append(summary)
        true_causes.append(s.true_cause_pattern)

    elapsed = time.monotonic() - t0

    results = {
        "n_scenarios": n,
        "elapsed_s": round(elapsed, 2),
        "hypothesis_accuracy": hypothesis_accuracy(hyp_summaries, true_causes),
        "brier_score": brier_score(confidences, outcomes),
        "ece": expected_calibration_error(confidences, outcomes),
        "falsifier_precision": falsifier_precision(predicted_verdicts, true_verdicts),
        "falsifier_recall": falsifier_recall(predicted_verdicts, true_verdicts),
        "action_precision": action_precision(recommended, ground_truth),
    }
    return results


def _print_report(r: dict) -> None:
    bar = "─" * 52
    print(f"\n{bar}")
    print("  Multi-Agent Observability Benchmark Results")
    print(bar)
    print(f"  Scenarios:                {r['n_scenarios']}")
    print(f"  Elapsed:                  {r['elapsed_s']}s")
    print(bar)
    print(f"  Hypothesis accuracy:      {r['hypothesis_accuracy']:.2f}")
    print(f"  Brier score (↓ better):   {r['brier_score']:.3f}")
    print(f"  ECE (↓ better):           {r['ece']:.3f}")
    print(bar)
    print(f"  Falsifier precision:      {r['falsifier_precision']:.2f}")
    print(f"  Falsifier recall:         {r['falsifier_recall']:.2f}")
    print(f"  Action precision:         {r['action_precision']:.2f}")
    print(f"{bar}\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the observability benchmark")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only run the first N scenarios")
    args = parser.parse_args(argv)
    results = run(limit=args.limit)
    _print_report(results)


if __name__ == "__main__":
    main(sys.argv[1:])
