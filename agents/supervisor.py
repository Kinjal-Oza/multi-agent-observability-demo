"""Supervisor agent.

Receives the raw alert. Does NOT investigate. Classifies the incident,
identifies which specialist agents to invoke, and writes the routing
decision back to shared state.

v2: also assigns an InvestigationBudget based on alert severity.
Deterministic routing — routing decisions are code, not prompt-driven.
"""
from __future__ import annotations

from agents.state import AgentStep, InvestigationBudget, InvestigationState


# Routing table: trigger classification -> ordered list of specialist agents
ROUTING_TABLE: dict[str, list[str]] = {
    "network":     ["telemetry", "reasoning", "falsifier", "counterfactual", "action"],
    "application": ["telemetry", "logs", "reasoning", "falsifier", "counterfactual", "action"],
    "infra":       ["telemetry", "logs", "deploy", "reasoning", "falsifier", "counterfactual", "action"],
    "unknown":     ["telemetry", "logs", "deploy", "reasoning", "falsifier", "counterfactual", "action"],
}

# Depth budget by alert severity
BUDGET_MAP: dict[str, int] = {
    "page":     5,
    "critical": 5,
    "warning":  3,
    "info":     2,
}


def supervisor_step(state: InvestigationState) -> InvestigationState:
    """Classify the incident, route to specialists, and assign investigation budget."""
    trigger = state["trigger"]
    classification = trigger.classification or "unknown"
    severity = getattr(trigger, "severity", "warning")

    routed = ROUTING_TABLE.get(classification, ROUTING_TABLE["unknown"])
    depth = BUDGET_MAP.get(severity, 3)

    state["routed_to"] = routed
    state["budget"] = InvestigationBudget(initial_depth=depth, remaining=depth)
    state.setdefault("audit_trail", []).append(AgentStep(
        agent="supervisor",
        description=(
            f"Classified as '{classification}' (severity='{severity}'); "
            f"routing to {routed}; investigation budget={depth}."
        ),
    ))
    return state
