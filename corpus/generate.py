"""Generate a synthetic incident corpus for benchmarking.

Produces 100 deterministic incidents (seeded) across 8 cause patterns
and 4 classification types. Run once to regenerate incidents.jsonl:

    python -m corpus.generate
"""
from __future__ import annotations

import json
import random
from pathlib import Path

SEED = 42

CAUSE_PATTERNS = [
    "connection pool exhaustion",
    "deploy regression",
    "thermal throttling",
    "dns resolution failure",
    "certificate expiry",
    "disk pressure",
    "memory pressure",
    "dependency cascade",
]

CLASSIFICATION_MAP: dict[str, list[str]] = {
    "application": ["connection pool exhaustion", "deploy regression", "dependency cascade"],
    "infra":       ["thermal throttling", "disk pressure", "memory pressure"],
    "network":     ["dns resolution failure", "certificate expiry", "dependency cascade"],
    "unknown":     CAUSE_PATTERNS,
}

SERVICES = [
    "payments-service", "auth-service", "inventory-service",
    "api-gateway", "db-proxy", "cache-cluster", "notification-service",
    "order-service",
]

METRICS = {
    "application": ["p99_latency_ms", "error_rate", "request_throughput"],
    "infra":       ["cpu_throttle_ratio", "disk_io_wait", "memory_utilization"],
    "network":     ["dns_latency_ms", "tcp_retransmit_rate", "packet_loss_rate"],
    "unknown":     ["p99_latency_ms", "cpu_throttle_ratio", "dns_latency_ms"],
}

GROUND_TRUTH_ACTIONS: dict[str, str] = {
    "connection pool exhaustion": "rollback_deploy",
    "deploy regression":          "rollback_deploy",
    "thermal throttling":         "drain_and_ticket",
    "dns resolution failure":     "flush_dns_cache",
    "certificate expiry":         "rotate_certificate",
    "disk pressure":              "expand_volume",
    "memory pressure":            "restart_service",
    "dependency cascade":         "isolate_dependency",
}

# Whether the falsifier should be able to disprove this cause with available findings.
# "refuted" cases test the Falsifier's ability to catch wrong hypotheses.
FALSIFIER_OUTCOMES: dict[str, str] = {
    "connection pool exhaustion": "confirmed",
    "deploy regression":          "confirmed",
    "thermal throttling":         "confirmed",
    "dns resolution failure":     "contested",
    "certificate expiry":         "confirmed",
    "disk pressure":              "confirmed",
    "memory pressure":            "confirmed",
    "dependency cascade":         "contested",
}


def _make_findings(cause: str, classification: str, rng: random.Random) -> list[dict]:
    findings = []
    # primary signal
    findings.append({
        "source": "prometheus",
        "description": f"primary metric anomaly consistent with {cause}",
        "severity": "warning",
        "raw": {"anomaly": True},
    })
    # supporting signal
    if cause == "connection pool exhaustion":
        findings.append({
            "source": "prometheus",
            "description": "db-proxy connection pool utilization at 0.97",
            "severity": "warning",
            "raw": {"utilization": 0.97},
        })
        findings.append({
            "source": "deploy_log",
            "description": "db-proxy deployed 18 minutes ago",
            "severity": "info",
            "raw": {"minutes_ago": 18},
        })
    elif cause == "thermal throttling":
        findings.append({
            "source": "prometheus",
            "description": "cpu_throttle_ratio elevated on 3 of 8 nodes in rack",
            "severity": "warning",
            "raw": {"nodes_affected": 3},
        })
    elif cause == "dns resolution failure":
        findings.append({
            "source": "logs",
            "description": "repeated NXDOMAIN errors in service logs",
            "severity": "warning",
            "raw": {"error_count": rng.randint(20, 80)},
        })
    elif cause == "memory pressure":
        findings.append({
            "source": "prometheus",
            "description": "memory utilization at 0.94, OOM events in last 5 min",
            "severity": "warning",
            "raw": {"utilization": 0.94},
        })
    # noise finding
    findings.append({
        "source": "prometheus",
        "description": "unrelated metric within normal range",
        "severity": "info",
        "raw": {"anomaly": False},
    })
    return findings


def generate(n: int = 100) -> list[dict]:
    rng = random.Random(SEED)
    incidents = []
    for i in range(n):
        classification = rng.choice(list(CLASSIFICATION_MAP.keys()))
        cause = rng.choice(CLASSIFICATION_MAP[classification])
        service = rng.choice(SERVICES)
        metric = rng.choice(METRICS[classification])
        threshold = rng.choice([100.0, 200.0, 500.0, 0.8, 0.9])
        value = threshold * rng.uniform(1.3, 2.5)
        incidents.append({
            "incident_id": f"bench-{i:04d}",
            "classification": classification,
            "service": service,
            "metric": metric,
            "value": round(value, 2),
            "threshold": threshold,
            "severity": rng.choice(["warning", "critical", "page"]),
            "true_cause_pattern": cause,
            "ground_truth_action": GROUND_TRUTH_ACTIONS[cause],
            "expected_falsifier_verdict": FALSIFIER_OUTCOMES[cause],
            "findings": _make_findings(cause, classification, rng),
        })
    return incidents


def main() -> None:
    incidents = generate()
    out = Path(__file__).parent / "incidents.jsonl"
    with out.open("w") as f:
        for inc in incidents:
            f.write(json.dumps(inc) + "\n")
    print(f"Wrote {len(incidents)} incidents to {out}")


if __name__ == "__main__":
    main()
