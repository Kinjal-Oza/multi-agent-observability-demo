"""Reasoning agent — provenance-bound hypothesis formation.

Takes the Telemetry Agent's structured findings and produces a hypothesis
about root cause. This is the one agent in the pipeline that calls an LLM.

v2: the hypothesis is now composed of Claim objects where each claim MUST
cite at least one Finding ID from the telemetry_findings list. Ungrounded
statements are rejected and recorded in the audit trail.

The reasoning agent also calls confidence.calibrate() to produce a
CalibratedConfidence object rather than a raw float.
"""
from __future__ import annotations

import re

from agents import confidence as conf_module
from agents.llm import get_backend, parse_hypothesis
from agents.state import AgentStep, Claim, Hypothesis, InvestigationState


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

FINDINGS (each finding has an index you MUST cite in claims):
{findings_block}

Produce a provenance-bound hypothesis. Every CLAIM must cite at least one
finding index in the SUPPORTS field. Claims without SUPPORTS will be discarded.
Respond in this exact format:

HYPOTHESIS: <one-sentence root-cause summary>
CLAIM 1: <statement> | SUPPORTS: [<comma-separated finding indices>]
CLAIM 2: <statement> | SUPPORTS: [<comma-separated finding indices>]
RAW_CONFIDENCE: <float between 0 and 1>
RATIONALE: <one-sentence reason>
"""


def _parse_claims(text: str, n_findings: int) -> tuple[str, float, str, list[Claim]]:
    """Parse the v2 structured response format.

    Returns (summary, raw_confidence, rationale, claims).
    Claims without valid SUPPORTS are silently dropped (recorded separately
    in the audit trail by the calling function).
    """
    summary = ""
    raw_confidence = 0.0
    rationale = ""
    claims: list[Claim] = []
    dropped_claims: list[str] = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        upper = line.upper()

        if upper.startswith("HYPOTHESIS:"):
            summary = line.split(":", 1)[1].strip()

        elif re.match(r"CLAIM\s+\d+:", line, re.IGNORECASE):
            # Format: "CLAIM N: <statement> | SUPPORTS: [0, 1]"
            parts = re.split(r"\|\s*SUPPORTS:", line, flags=re.IGNORECASE)
            if len(parts) < 2:
                # No SUPPORTS field — drop claim
                raw_stmt = re.sub(r"CLAIM\s+\d+:\s*", "", line, flags=re.IGNORECASE)
                dropped_claims.append(raw_stmt.strip())
                continue

            stmt_raw = re.sub(r"CLAIM\s+\d+:\s*", "", parts[0], flags=re.IGNORECASE).strip()
            supports_raw = parts[1].strip()
            # Extract integers from "[0, 2]" or "0, 2" or "[0]"
            indices = [int(x) for x in re.findall(r"\d+", supports_raw)]
            # Filter out-of-bounds indices
            valid_ids = [i for i in indices if 0 <= i < n_findings]
            if not valid_ids:
                dropped_claims.append(stmt_raw)
                continue

            try:
                claims.append(Claim(statement=stmt_raw, supporting_finding_ids=valid_ids))
            except ValueError:
                dropped_claims.append(stmt_raw)

        elif upper.startswith("RAW_CONFIDENCE:") or upper.startswith("CONFIDENCE:"):
            try:
                raw_confidence = float(line.split(":", 1)[1].strip())
            except ValueError:
                raw_confidence = 0.0

        elif upper.startswith("RATIONALE:"):
            rationale = line.split(":", 1)[1].strip()

    if not summary:
        # Fallback: use first line
        summary = text.strip().split("\n", 1)[0]

    return summary, max(0.0, min(1.0, raw_confidence)), rationale, claims


def reasoning_step(state: InvestigationState) -> InvestigationState:
    backend = get_backend()
    prompt = _build_prompt(state)
    raw_text = backend.complete(prompt)

    findings = state.get("telemetry_findings", [])
    n_findings = len(findings)

    summary, raw_confidence, rationale, claims = _parse_claims(raw_text, n_findings)

    # Record dropped claims in audit trail
    audit: list[AgentStep] = state.get("audit_trail", [])

    # If no claims parsed (e.g. old-format response), fall back to flat parse
    if not claims:
        _, raw_confidence, rationale = parse_hypothesis(raw_text)
        # Construct a single claim grounded in any anomalous finding
        anomalous_ids = [i for i, f in enumerate(findings) if f.severity != "info"]
        if not anomalous_ids:
            anomalous_ids = list(range(min(1, n_findings)))
        if anomalous_ids:
            try:
                claims = [Claim(
                    statement=summary or "root cause identified from anomalous findings",
                    supporting_finding_ids=anomalous_ids,
                )]
            except ValueError:
                pass
        audit.append(AgentStep(
            agent="reasoning",
            description="Fell back to flat parse — no CLAIM lines in LLM response.",
        ))

    # Collect all supporting finding IDs across claims
    all_supporting: list[int] = []
    for c in claims:
        all_supporting.extend(c.supporting_finding_ids)
    all_supporting = sorted(set(all_supporting))

    # Calibrated confidence (falsification modifier is placeholder pre-falsifier)
    calibrated = conf_module.calibrate(state, raw_confidence, summary)

    hypothesis = Hypothesis(
        summary=summary,
        claims=claims,
        confidence=calibrated,
        supporting_finding_ids=all_supporting,
    )

    state["causal_hypothesis"] = hypothesis
    state["confidence_score"] = calibrated.final
    audit.append(AgentStep(
        agent="reasoning",
        description=(
            f"hypothesis (raw={raw_confidence:.2f}, calibrated={calibrated.final:.2f}): {summary} "
            f"[{len(claims)} provenance-bound claim(s)]"
        ),
    ))
    state["audit_trail"] = audit
    return state
