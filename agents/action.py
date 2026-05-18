"""Action agent.

Translates a hypothesis into a recommended remediation. NEVER executes
autonomously in this demo. Always drafts an action and marks the state
as requiring human approval.

For a real deployment, the threshold logic for low-risk autonomous action
would live here. This implementation keeps that gate closed deliberately.
"""
from __future__ import annotations

from agents.state import Action, AgentStep, InvestigationState


# Configurable thresholds — exposed for inspection rather than buried.
AUTONOMOUS_CONFIDENCE_FLOOR = 0.95     # Default: human-only.
ENABLE_AUTONOMOUS_LOW_RISK = False     # Default: even low-risk actions go to a human.


# Recommended remediation patterns keyed by hypothesis substring.
REMEDIATION_PATTERNS = [
    ("connection pool", Action(
        description="Roll back the most recent deploy of the affected service.",
        risk_level="medium",
        requires_approval=True,
        rationale="Connection-pool regressions are most commonly fixed by reverting to the prior known-good version.",
    )),
    ("thermal", Action(
        description="Drain affected hosts and open a hardware ticket for thermal inspection.",
        risk_level="medium",
        requires_approval=True,
        rationale="Thermal throttling is typically a hardware issue; software remediation will not resolve it.",
    )),
    ("deploy", Action(
        description="Roll back the recent deploy and re-investigate after metrics stabilize.",
        risk_level="medium",
        requires_approval=True,
        rationale="Deploy-correlated anomalies are most cheaply isolated by reverting the deploy.",
    )),
]
DEFAULT_ACTION = Action(
    description="Escalate to the on-call engineer with current investigation state.",
    risk_level="low",
    requires_approval=True,
    rationale="No high-confidence remediation pattern matched. Hand off with full context.",
)


def action_step(state: InvestigationState) -> InvestigationState:
    hypothesis = state.get("causal_hypothesis")
    actions: list[Action] = state.get("recommended_actions", [])

    selected: Action = DEFAULT_ACTION
    if hypothesis is not None:
        summary_lower = hypothesis.summary.lower()
        for pattern, action in REMEDIATION_PATTERNS:
            if pattern in summary_lower:
                selected = action
                break

    # Gate: by default ALL actions require human approval.
    confidence = state.get("confidence_score", 0.0)
    autonomous = (
        ENABLE_AUTONOMOUS_LOW_RISK
        and selected.risk_level == "low"
        and confidence >= AUTONOMOUS_CONFIDENCE_FLOOR
    )
    selected_with_gate = Action(
        description=selected.description,
        risk_level=selected.risk_level,
        requires_approval=not autonomous,
        rationale=selected.rationale,
    )

    actions.append(selected_with_gate)
    state["recommended_actions"] = actions
    state["requires_human_approval"] = selected_with_gate.requires_approval
    state["audit_trail"].append(AgentStep(
        agent="action",
        description=f"recommended: {selected_with_gate.description} (approval required: {selected_with_gate.requires_approval})",
    ))
    return state
