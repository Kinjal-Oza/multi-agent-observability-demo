"""Load the synthetic incident corpus for benchmarking."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from agents.state import AlertTrigger, Finding

_CORPUS_PATH = Path(__file__).parent.parent / "corpus" / "incidents.jsonl"


@dataclass
class Scenario:
    trigger: AlertTrigger
    findings: list[Finding]
    true_cause_pattern: str
    ground_truth_action: str
    expected_falsifier_verdict: str
    incident_id: str


def _parse_finding(raw: dict) -> Finding:
    return Finding(
        source=raw["source"],
        description=raw["description"],
        severity=raw["severity"],
        raw=raw.get("raw", {}),
    )


def load_corpus(limit: int | None = None) -> list[Scenario]:
    """Load all (or a subset of) corpus scenarios.

    The corpus includes pre-built findings for each scenario. The benchmark
    injects these findings directly into the state, bypassing the telemetry
    mock (which only covers a handful of service/metric pairs). This lets
    the benchmark test reasoning quality, not mock coverage.
    """
    scenarios: list[Scenario] = []
    with _CORPUS_PATH.open() as f:
        for i, line in enumerate(f):
            if limit is not None and i >= limit:
                break
            inc = json.loads(line)
            trigger = AlertTrigger(
                alert_id=inc["incident_id"],
                service=inc["service"],
                metric=inc["metric"],
                value=inc["value"],
                threshold=inc["threshold"],
                classification=inc["classification"],
                severity=inc.get("severity", "warning"),
            )
            findings = [_parse_finding(f) for f in inc.get("findings", [])]
            scenarios.append(Scenario(
                trigger=trigger,
                findings=findings,
                true_cause_pattern=inc["true_cause_pattern"],
                ground_truth_action=inc["ground_truth_action"],
                expected_falsifier_verdict=inc["expected_falsifier_verdict"],
                incident_id=inc["incident_id"],
            ))
    return scenarios
