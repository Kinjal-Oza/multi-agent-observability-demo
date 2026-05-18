"""Mock deploy log.

Returns synthetic deploy events to feed the telemetry agent's correlation
logic. In a real integration this would query the CD system (ArgoCD,
Spinnaker, Jenkins, etc.).
"""
from __future__ import annotations

_DEPLOYS: dict[str, list[dict]] = {
    "db-proxy": [
        {"service": "db-proxy", "version": "2.3.1", "deployed_at": "T-18m"},
    ],
    "payments-service": [
        {"service": "payments-service", "version": "1.42.0", "deployed_at": "T-3h"},
    ],
    "inventory-service": [],
}


def recent_deploys(service: str, window_minutes: int = 60) -> list[dict]:
    """Return deploys recorded for the given service within the window."""
    return list(_DEPLOYS.get(service, []))
