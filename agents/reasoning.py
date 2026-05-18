"""Reasoning agent.

Takes structured findings from the telemetry agent and produces a hypothesis
about root cause. This is the one agent in the pipeline that calls an LLM —
because the work it does (causal reasoning across heterogeneous signals)
is the hardest part to encode in rules.

The reasoning agent's confidence score is reported, not trusted. The Action
agent decides what to do with it.
"""
from __future__ import annotations

from agents.llm import get_backend, parse_hypothesis
from agents.state import AgentStep, Hypothesis, InvestigationState


def _build_prompt(state: InvestigationState) -> str:
    trigger = state["trigger"]
    findings = state.get("telemetry_findings", [])
    findings_block = "\n".join(
        f"  [{i}] ({f.source}) {f.description} [severity={f.severity}]"
        for i, f in enumerate(findings)
    ) or "  (no findings)"

    return f"""You are a site-reliability engineer analyzing an alert.

ALERT:
  service: {trigger.service}
  metric:  {trigger.metric}
  value:   {trigger.value} (threshold {trigger.threshold})
  type:    {trigger.classification}

FINDINGS:
{findings_block}

Produce a structured hypothesis. Respond in this exact format:
HYPOTHESIS: <one-sentence root-cause hypothesis>
CONFIDENCE: <float between 0 and 1>
RATIONALE: <one-sentence reason>
"""


def reasoning_step(state: InvestigationState) -> InvestigationState:
    backend = get_backend()
    prompt = _build_prompt(state)
    raw = backend.complete(prompt)
    summary, confidence, rationale = parse_hypothesis(raw)

    findings = state.get("telemetry_findings", [])
    supporting_ids = [i for i, f in enumerate(findings) if f.severity != "info"]

    hypothesis = Hypothesis(
        summary=summary,
        confidence=confidence,
        supporting_finding_ids=supporting_ids,
        references=[rationale] if rationale else [],
    )

    state["causal_hypothesis"] = hypothesis
    state["confidence_score"] = confidence
    state["audit_trail"].append(AgentStep(
        agent="reasoning",
        description=f"hypothesis (conf={confidence:.2f}): {summary}",
    ))
    return state
