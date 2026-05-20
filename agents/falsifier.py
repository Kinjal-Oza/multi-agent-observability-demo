"""Adversarial Falsifier agent.

The only agent in the pipeline whose job is to DISPROVE the leading hypothesis.
Every other system in the market runs confirmation cascades: findings →
hypothesis → action. This agent breaks that pattern.

Design rationale (Popper, 1963):
  A hypothesis that cannot be tested against contradicting evidence is not
  a scientific hypothesis — it is a belief. For operational AI to be safe,
  its reasoning must be falsifiable. The Falsifier agent operationalizes this.

Verdict semantics:
  "confirmed"  — no contradicting evidence found in findings
  "contested"  — contradictions exist but only against info-severity findings
  "refuted"    — at least one claim has a contradicting warning/critical finding

A "refuted" verdict causes the Action agent to escalate to human review
regardless of the raw confidence score. This is the safety invariant.

Budget extensions:
  If the Falsifier cannot yet disprove the hypothesis (verdict != refuted) and
  the investigation budget has remaining extensions, it requests one. Real
  production deployments would use this to trigger a second telemetry pass.
"""
from __future__ import annotations

import re

from agents import confidence as conf_module
from agents.llm import get_backend
from agents.state import (
    AgentStep,
    FalsificationResult,
    InvestigationState,
)


def _build_falsifier_prompt(state: InvestigationState) -> str:
    hypothesis = state["causal_hypothesis"]
    findings = state.get("telemetry_findings", [])

    claims_block = "\n".join(
        f"  CLAIM {i+1}: {c.statement} (cites findings {c.supporting_finding_ids})"
        for i, c in enumerate(hypothesis.claims)
    ) if hypothesis.claims else "  (no structured claims)"

    findings_block = "\n".join(
        f"  [{i}] ({f.source}) {f.description} [severity={f.severity}]"
        for i, f in enumerate(findings)
    ) or "  (no findings)"

    return f"""You are an adversarial reviewer trying to DISPROVE the following hypothesis.
Your job is NOT to confirm it — it is to find the strongest contradicting evidence.

HYPOTHESIS: {hypothesis.summary}

CLAIMS TO CHALLENGE:
{claims_block}

ALL AVAILABLE FINDINGS:
{findings_block}

For each claim that has contradicting evidence, report it. For claims with no
contradicting evidence, mark them UNFALSIFIABLE.

Respond in this exact format:

VERDICT: <confirmed | contested | refuted>
CONTRADICTION 1: <description of contradicting evidence> | FINDING: <index>
UNFALSIFIABLE: <claim statement> — <why it can't be disproved>
FALSIFICATION_SCORE: <float 0.0 to 1.0 — 0=nothing contradicts, 1=fully contradicted>
"""


def _parse_falsification(text: str, findings: list) -> FalsificationResult:
    verdict: str = "contested"
    contradictions: list[str] = []
    falsification_score = 0.45
    contested_claim_indices: list[int] = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        upper = line.upper()

        if upper.startswith("VERDICT:"):
            v = line.split(":", 1)[1].strip().lower()
            if v in ("confirmed", "contested", "refuted"):
                verdict = v

        elif upper.startswith("CONTRADICTION"):
            # "CONTRADICTION N: <text> | FINDING: <idx>"
            parts = re.split(r"\|\s*FINDING:", line, flags=re.IGNORECASE)
            desc = re.sub(r"CONTRADICTION\s+\d+:\s*", "", parts[0], flags=re.IGNORECASE).strip()
            contradictions.append(desc)
            if len(parts) > 1:
                try:
                    finding_idx = int(parts[1].strip())
                    contested_claim_indices.append(finding_idx)
                except ValueError:
                    pass

        elif upper.startswith("FALSIFICATION_SCORE:"):
            try:
                falsification_score = float(line.split(":", 1)[1].strip())
                falsification_score = max(0.0, min(1.0, falsification_score))
            except ValueError:
                pass

    return FalsificationResult(
        verdict=verdict,  # type: ignore[arg-type]
        contradictions=contradictions,
        falsification_score=falsification_score,
        contested_claim_indices=contested_claim_indices,
    )


def falsifier_step(state: InvestigationState) -> InvestigationState:
    hypothesis = state.get("causal_hypothesis")
    if hypothesis is None:
        state.setdefault("audit_trail", []).append(AgentStep(
            agent="falsifier",
            description="Skipped — no hypothesis to falsify.",
        ))
        state["falsification"] = FalsificationResult(
            verdict="contested",
            contradictions=["No hypothesis provided"],
            falsification_score=0.5,
        )
        return state

    backend = get_backend()
    prompt = _build_falsifier_prompt(state)
    raw_text = backend.complete(prompt)

    findings = state.get("telemetry_findings", [])
    result = _parse_falsification(raw_text, findings)
    state["falsification"] = result

    # Update calibrated confidence retroactively with the falsification score
    updated_conf = conf_module.update_with_falsification(
        hypothesis.confidence, result.falsification_score
    )
    hypothesis.confidence = updated_conf
    state["confidence_score"] = updated_conf.final

    # Budget extension: if contested/confirmed and budget allows, record extension request
    budget = state.get("budget")
    if result.verdict != "refuted" and budget is not None:
        if budget.extensions_granted < budget.MAX_EXTENSIONS and budget.remaining > 0:
            budget.extensions_granted += 1
            # In production, this triggers another telemetry pass. Here we log it.
            state.setdefault("audit_trail", []).append(AgentStep(
                agent="falsifier",
                description=(
                    f"Budget extension #{budget.extensions_granted} requested — "
                    "hypothesis not yet refuted, more evidence could sharpen verdict."
                ),
            ))

    state.setdefault("audit_trail", []).append(AgentStep(
        agent="falsifier",
        description=(
            f"verdict={result.verdict}, score={result.falsification_score:.2f}, "
            f"{len(result.contradictions)} contradiction(s) found. "
            f"Updated confidence: {updated_conf.final:.2f}"
        ),
    ))
    return state
