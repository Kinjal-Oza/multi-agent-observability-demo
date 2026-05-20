"""Shared investigation state.

All agents read from and write to a single typed state object. This is what
makes the audit trail useful — every observation, every inference, and every
recommended action is recorded with its source agent.

Novel types added in v2:
- Claim          — provenance-bound causal claim (must cite >= 1 Finding ID)
- CalibratedConfidence — weighted ensemble of LLM, prior, and falsification
- FalsificationResult  — verdict from the adversarial Falsifier agent
- CounterfactualPrediction — predicted post-action state from the simulator
- InvestigationBudget — depth budget assigned by the Supervisor
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, TypedDict, Literal


Severity = Literal["info", "warning", "critical", "page"]
TriggerType = Literal["network", "application", "infra", "unknown"]
FalsificationVerdict = Literal["confirmed", "contested", "refuted"]
SimulatorMethod = Literal["rule_based", "llm_assisted"]


@dataclass
class AlertTrigger:
    """The alert that started the investigation."""
    alert_id: str
    service: str
    metric: str
    value: float
    threshold: float
    classification: TriggerType
    severity: Severity = "warning"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Finding:
    """A single observation produced by the telemetry agent."""
    source: str           # e.g. "prometheus", "logs", "deploy_log"
    description: str
    severity: Severity
    raw: dict
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# --- Provenance-Bound Causal Claims ---

@dataclass
class Claim:
    """A single causal statement that MUST cite at least one Finding ID.

    This is the core provenance guarantee. The system rejects any Claim
    whose supporting_finding_ids list is empty — ungrounded statements
    cannot be constructed.
    """
    statement: str
    supporting_finding_ids: list[int]

    def __post_init__(self) -> None:
        if not self.supporting_finding_ids:
            raise ValueError(
                f"Claim '{self.statement[:60]}...' has no supporting finding IDs. "
                "Every claim must cite at least one Finding. This is a system invariant."
            )


# --- Calibrated Confidence via Learned Prior ---

@dataclass
class CalibratedConfidence:
    """Explicit breakdown of how the final confidence is computed.

    final = clip(0.4*raw_llm + 0.4*prior + 0.2*(1 - falsification_score))

    This is a deliberate design choice: few shipping observability tools report calibrated
    confidence that incorporates historical priors and adversarial penalty.
    """
    raw_llm: float            # direct LLM self-report (0-1, known to be miscalibrated)
    prior: float              # P(cause | classification) from incident corpus
    falsification_modifier: float  # 1 - falsification_score (from Falsifier)
    final: float              # the composite, clipped to [0, 1]
    components: dict          # for audit trail transparency


# --- Adversarial Falsification Result ---

@dataclass
class FalsificationResult:
    """Output of the adversarial Falsifier agent.

    verdict: "confirmed"  — no contradicting evidence found
             "contested"  — contradictions exist only against info-severity findings
             "refuted"    — at least one claim has a warning/critical contradicting finding

    A "refuted" verdict blocks autonomous action (see agents/action.py).
    """
    verdict: FalsificationVerdict
    contradictions: list[str]
    falsification_score: float    # 0=nothing contradicts, 1=fully contradicted
    contested_claim_indices: list[int] = field(default_factory=list)


# --- Counterfactual Outcome Simulation ---

@dataclass
class PredictedDelta:
    """A single predicted change in a service metric after the action."""
    target: str        # e.g. "payments-service"
    metric: str        # e.g. "p99_latency_ms"
    expected_change: str   # human-readable, e.g. "drops 60-80% from current"
    lower_bound: float     # e.g. 0.60  (fractional change)
    upper_bound: float     # e.g. 0.80


@dataclass
class CounterfactualPrediction:
    """Pre-execution forecast of the post-remediation system state.

    The human approver sees this alongside the proposed action so they know
    not just *what* the system recommends but *what it predicts will happen*
    if they approve.
    """
    action_description: str
    predicted_deltas: list[PredictedDelta]
    prediction_confidence: float    # how sure the simulator is (0-1)
    simulator_method: SimulatorMethod


# --- Adaptive Investigation Budget ---

@dataclass
class InvestigationBudget:
    """Depth budget assigned by the Supervisor based on alert severity.

    The Falsifier can request budget extensions (up to a hard cap) if it
    cannot disprove the hypothesis with current evidence.
    """
    initial_depth: int
    remaining: int
    extensions_granted: int = 0

    MAX_EXTENSIONS: int = field(default=2, init=False, repr=False)


@dataclass
class Hypothesis:
    """The reasoning agent's best guess at root cause.

    In v2, the hypothesis is composed of provenance-bound Claims rather than
    a flat text summary. Confidence is a CalibratedConfidence object.
    """
    summary: str
    claims: list[Claim]
    confidence: CalibratedConfidence
    supporting_finding_ids: list[int]   # union across all claims, kept for compat


@dataclass
class Action:
    """A recommended remediation step. Never executed without human approval."""
    description: str
    risk_level: Literal["low", "medium", "high"]
    requires_approval: bool
    rationale: str


@dataclass
class AgentStep:
    """One step in the investigation trail."""
    agent: str
    description: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class InvestigationState(TypedDict, total=False):
    """The shared state that flows through the graph.

    Using TypedDict (vs dataclass) keeps it compatible with LangGraph's
    state-graph API while still being statically checkable. Keys are
    optional because not every agent populates every field.
    """
    incident_id: str
    trigger: AlertTrigger
    routed_to: list[str]
    budget: InvestigationBudget
    telemetry_findings: list[Finding]
    causal_hypothesis: Optional[Hypothesis]
    falsification: Optional[FalsificationResult]
    counterfactual: Optional[CounterfactualPrediction]
    recommended_actions: list[Action]
    confidence_score: float            # kept for compat; mirrors hypothesis.confidence.final
    audit_trail: list[AgentStep]
    requires_human_approval: bool


def new_state(incident_id: str, trigger: AlertTrigger) -> InvestigationState:
    """Construct a fresh state object for a new incident."""
    severity = trigger.severity if hasattr(trigger, "severity") else "warning"
    depth_map = {"page": 5, "critical": 5, "warning": 3, "info": 2}
    depth = depth_map.get(severity, 3)
    return InvestigationState(
        incident_id=incident_id,
        trigger=trigger,
        routed_to=[],
        budget=InvestigationBudget(initial_depth=depth, remaining=depth),
        telemetry_findings=[],
        causal_hypothesis=None,
        falsification=None,
        counterfactual=None,
        recommended_actions=[],
        confidence_score=0.0,
        audit_trail=[
            AgentStep(agent="system", description=f"Investigation opened for alert {trigger.alert_id}"),
        ],
        requires_human_approval=True,
    )
