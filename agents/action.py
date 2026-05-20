"""Action agent — Falsifier-aware remediation with counterfactual gating.

v2 changes:
  1. Reads state["falsification"]. If verdict == "refuted", overrides ALL
     other logic and escalates immediately. The Falsifier is the safety veto.
  2. Reads state["counterfactual"]. Records the prediction alongside the
     recommendation so the human approver can see predicted outcome.
  3. The autonomous-action gate now additionally requires:
     - falsification.verdict == "confirmed"
     - counterfactual.prediction_confidence >= 0.70

NEVER executes autonomously in this demo. Always drafts an action and marks
the state as requiring human approval unless the compound condition is met.
"""
from __future__ import annotations

from agents.state import Action, AgentStep, InvestigationState


# Configurable thresholds — exposed for inspection rather than buried.
AUTONOMOUS_CONFIDENCE_FLOOR = 0.95
ENABLE_AUTONOMOUS_LOW_RISK = False


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
    ("dns", Action(
        description="Flush DNS cache on affected hosts and verify upstream resolver health.",
        risk_level="low",
        requires_approval=True,
        rationale="DNS misconfigurations are frequently resolved by cache flush; verify resolver to prevent recurrence.",
    )),
    ("memory", Action(
        description="Restart the affected service pod and monitor memory trends for recurrence.",
        risk_level="low",
        requires_approval=True,
        rationale="Service restart clears memory pressure; monitoring prevents silent recurrence.",
    )),
]

DEFAULT_ACTION = Action(
    description="Escalate to the on-call engineer with current investigation state.",
    risk_level="low",
    requires_approval=True,
    rationale="No high-confidence remediation pattern matched. Hand off with full context.",
)

REFUTED_ACTION = Action(
    description=(
        "ESCALATE IMMEDIATELY — Falsifier rejected the hypothesis. "
        "Do not act on this root cause without further investigation."
    ),
    risk_level="high",
    requires_approval=True,
    rationale=(
        "The adversarial Falsifier found contradicting evidence that undermines the "
        "leading hypothesis. Acting on a refuted hypothesis risks making the incident worse."
    ),
)


def action_step(state: InvestigationState) -> InvestigationState:
    falsification = state.get("falsification")
    counterfactual = state.get("counterfactual")
    hypothesis = state.get("causal_hypothesis")
    actions: list[Action] = state.get("recommended_actions", [])

    # --- Safety override: Falsifier veto ---
    if falsification is not None and falsification.verdict == "refuted":
        actions.append(REFUTED_ACTION)
        state["recommended_actions"] = actions
        state["requires_human_approval"] = True
        state.setdefault("audit_trail", []).append(AgentStep(
            agent="action",
            description=(
                f"FALSIFIER VETO — hypothesis refuted (score={falsification.falsification_score:.2f}). "
                "Overriding pattern match. Escalating to human immediately."
            ),
        ))
        return state

    # --- Select remediation pattern ---
    selected: Action = DEFAULT_ACTION
    if hypothesis is not None:
        summary_lower = hypothesis.summary.lower()
        for pattern, action in REMEDIATION_PATTERNS:
            if pattern in summary_lower:
                selected = action
                break

    # --- Autonomous gate (default: CLOSED) ---
    confidence = state.get("confidence_score", 0.0)
    falsifier_confirmed = (
        falsification is not None and falsification.verdict == "confirmed"
    )
    counterfactual_confident = (
        counterfactual is not None and counterfactual.prediction_confidence >= 0.70
    )
    autonomous = (
        ENABLE_AUTONOMOUS_LOW_RISK
        and selected.risk_level == "low"
        and confidence >= AUTONOMOUS_CONFIDENCE_FLOOR
        and falsifier_confirmed
        and counterfactual_confident
    )

    final_action = Action(
        description=selected.description,
        risk_level=selected.risk_level,
        requires_approval=not autonomous,
        rationale=selected.rationale,
    )

    actions.append(final_action)
    state["recommended_actions"] = actions
    state["requires_human_approval"] = final_action.requires_approval

    # Build audit description
    cf_note = ""
    if counterfactual:
        cf_note = (
            " Counterfactual predicts: "
            + "; ".join(
                f"{d.target}/{d.metric} improves {d.lower_bound:.0%}–{d.upper_bound:.0%}"
                for d in counterfactual.predicted_deltas[:2]
            )
        )

    state.setdefault("audit_trail", []).append(AgentStep(
        agent="action",
        description=(
            f"recommended: {final_action.description} "
            f"(approval required: {final_action.requires_approval}, "
            f"falsifier: {falsification.verdict if falsification else 'n/a'})."
            f"{cf_note}"
        ),
    ))
    return state
