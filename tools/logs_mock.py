"""Mock log search.

Returns synthetic log lines matching a service + level filter.
"""
from __future__ import annotations

LEVEL_ORDER = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40, "FATAL": 50}


_LOG_FIXTURES: dict[str, list[dict]] = {
    "payments-service": [
        {"level": "ERROR", "msg": "db-proxy connection pool exhausted; retrying"},
        {"level": "ERROR", "msg": "request timed out waiting for downstream"},
        {"level": "WARN",  "msg": "elevated latency observed"},
    ],
    "inventory-service": [
        {"level": "WARN", "msg": "thermal sensor reading elevated on host inv-h-12"},
        {"level": "WARN", "msg": "throughput degraded on subset of hosts"},
    ],
    "auth-service": [
        {"level": "INFO", "msg": "auth-service healthy"},
    ],
}


def search_logs(service: str, window_minutes: int = 15, level_at_least: str = "WARN") -> list[dict]:
    """Return matching log entries from the fixture set."""
    floor = LEVEL_ORDER.get(level_at_least.upper(), 30)
    entries = _LOG_FIXTURES.get(service, [])
    return [e for e in entries if LEVEL_ORDER.get(e["level"].upper(), 0) >= floor]
