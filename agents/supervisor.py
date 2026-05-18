"""Supervisor agent.

Receives the raw alert. Does NOT investigate. Classifies the incident,
identifies which specialist agents to invoke, and writes the routing
decision back to shared state.

This is intentionally a small, deterministic function. Routing decisions
are easier to debug when they're code, not prompt-driven.
"""
from __future__ import annotations

from agents.state import AgentStep, InvestigationState


# Routing table: trigger classification -> ordered list of specialist agents
ROUTING_TABLE: dict[str, list[str]] = {
    "network":     ["telemetry", "reasoning", "action"],
    "application": ["telemetry", "logs", "reasoning", "action"],
    "infra":       ["telemetry", "logs", "deploy", "reasoning", "action"],
    "unknown":     ["telemetry", "logs", "deploy", "reasoning", "action"],
}


def supervisor_step(state: InvestigationState) -> InvestigationState:
    """Decide which specialists to invoke for this incident."""
    trigger = state["trigger"]
    classification = trigger.classification or "unknown"
    routed = ROUTING_TABLE.get(classification, ROUTING_TABLE["unknown"])

    state["routed_to"] = routed
    state["audit_trail"].append(AgentStep(
        agent="supervisor",
        description=f"Classified as '{classification}'; routing to {routed}",
    ))
    return state
