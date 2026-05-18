"""Shared investigation state.

All agents read from and write to a single typed state object. This is what
makes the audit trail useful — every observation, every inference, and every
recommended action is recorded with its source agent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, TypedDict, Literal


Severity = Literal["info", "warning", "critical", "page"]
TriggerType = Literal["network", "application", "infra", "unknown"]


@dataclass
class AlertTrigger:
    """The alert that started the investigation."""
    alert_id: str
    service: str
    metric: str
    value: float
    threshold: float
    classification: TriggerType
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Finding:
    """A single observation produced by the telemetry agent."""
    source: str           # e.g. "prometheus", "logs", "deploy_log"
    description: str
    severity: Severity
    raw: dict
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Hypothesis:
    """The reasoning agent's best guess at root cause."""
    summary: str
    confidence: float                     # 0.0 - 1.0
    supporting_finding_ids: list[int]     # indices into telemetry_findings
    references: list[str] = field(default_factory=list)


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
    telemetry_findings: list[Finding]
    causal_hypothesis: Optional[Hypothesis]
    recommended_actions: list[Action]
    confidence_score: float
    audit_trail: list[AgentStep]
    requires_human_approval: bool


def new_state(incident_id: str, trigger: AlertTrigger) -> InvestigationState:
    """Construct a fresh state object for a new incident."""
    return InvestigationState(
        incident_id=incident_id,
        trigger=trigger,
        routed_to=[],
        telemetry_findings=[],
        causal_hypothesis=None,
        recommended_actions=[],
        confidence_score=0.0,
        audit_trail=[
            AgentStep(agent="system", description=f"Investigation opened for alert {trigger.alert_id}"),
        ],
        requires_human_approval=True,
    )
