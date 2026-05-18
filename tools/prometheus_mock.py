"""Mock Prometheus client.

Returns synthetic metric data keyed by (service, metric). The data is
deterministic so tests can assert against it.
"""
from __future__ import annotations

from typing import TypedDict


class MetricResult(TypedDict, total=False):
    service: str
    metric: str
    summary: str
    anomaly: bool
    dependencies: list[str]
    raw_samples: list[float]


# Synthetic scenarios — extend as needed for additional test cases.
_SCENARIOS: dict[tuple[str, str], MetricResult] = {
    ("payments-service", "p99_latency_ms"): {
        "summary": "p99 elevated to ~820ms vs baseline 220ms over last 5 min",
        "anomaly": True,
        "dependencies": ["db-proxy", "auth-service"],
        "raw_samples": [220, 225, 410, 720, 820, 815],
    },
    ("db-proxy", "utilization"): {
        "summary": "connection pool utilization at 0.97 vs baseline 0.45",
        "anomaly": True,
        "dependencies": [],
        "raw_samples": [0.42, 0.48, 0.81, 0.94, 0.97],
    },
    ("auth-service", "utilization"): {
        "summary": "utilization within normal range (0.32)",
        "anomaly": False,
        "dependencies": [],
        "raw_samples": [0.31, 0.30, 0.33, 0.32, 0.32],
    },
    ("inventory-service", "p99_latency_ms"): {
        "summary": "p99 elevated to ~610ms; correlated with thermal alert on rack hardware",
        "anomaly": True,
        "dependencies": ["object-store"],
        "raw_samples": [180, 200, 410, 580, 610],
    },
    ("object-store", "utilization"): {
        "summary": "utilization normal (0.41)",
        "anomaly": False,
        "dependencies": [],
        "raw_samples": [0.40, 0.42, 0.41, 0.41, 0.41],
    },
}


def query_metric(service: str, metric: str, window_minutes: int = 15) -> MetricResult:
    """Return a synthetic metric result for the given series.

    Falls back to a benign 'no anomaly' result if the scenario isn't defined,
    so unknown services don't blow up the pipeline.
    """
    key = (service, metric)
    if key in _SCENARIOS:
        result: MetricResult = dict(_SCENARIOS[key])  # type: ignore[assignment]
        result["service"] = service
        result["metric"] = metric
        return result
    return MetricResult(
        service=service,
        metric=metric,
        summary="no data available for this series in mock backend",
        anomaly=False,
        dependencies=[],
        raw_samples=[],
    )
