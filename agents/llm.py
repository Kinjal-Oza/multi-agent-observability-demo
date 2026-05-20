"""Pluggable LLM backend.

The demo is reproducible and CI-friendly because the default backend is a
deterministic fake that returns canned responses keyed by prompt content.

To run against a real model:

    export MAO_MODEL_BACKEND=openai
    export OPENAI_API_KEY=...

v2: canned responses updated with CLAIM/SUPPORTS/CONTRADICTION lines to
support the provenance-bound reasoning and adversarial falsifier agents.
"""
from __future__ import annotations

import os
import re
from typing import Protocol


class ChatBackend(Protocol):
    def complete(self, prompt: str) -> str: ...


class DeterministicFake:
    """Returns canned responses based on substring matches.

    This is intentionally dumb. Its purpose is to make the demo runnable
    without API keys and to keep CI deterministic. Tests assert against
    this backend's output. Real reasoning quality is evaluated separately
    with a real model.

    v2: responses include CLAIM/SUPPORTS lines (for reasoning agent) and
    CONTRADICTION/FALSIFICATION lines (for falsifier agent).
    """

    # Reasoning responses — provenance-bound format
    REASONING_RESPONSES = [
        (r"connection pool", (
            "HYPOTHESIS: connection pool exhaustion in recently deployed service.\n"
            "CLAIM 1: db-proxy connection pool utilization reached 0.97, far above baseline. | SUPPORTS: [0, 1]\n"
            "CLAIM 2: the anomaly window aligns with the db-proxy deploy 18 minutes ago. | SUPPORTS: [1, 2]\n"
            "RAW_CONFIDENCE: 0.72\n"
            "RATIONALE: metric anomaly tightly correlated with recent deploy timestamp."
        )),
        (r"deploy.*recent|recent.*deploy", (
            "HYPOTHESIS: regression introduced by recent deployment.\n"
            "CLAIM 1: primary metric elevated immediately after deploy event. | SUPPORTS: [0, 2]\n"
            "CLAIM 2: no upstream dependency anomalies reduce other explanations. | SUPPORTS: [0]\n"
            "RAW_CONFIDENCE: 0.65\n"
            "RATIONALE: anomaly window aligns with deploy timestamp, dependencies normal."
        )),
        (r"thermal", (
            "HYPOTHESIS: thermal throttling on subset of hosts.\n"
            "CLAIM 1: cpu_throttle_ratio elevated on rack nodes during anomaly window. | SUPPORTS: [0, 1]\n"
            "RAW_CONFIDENCE: 0.55\n"
            "RATIONALE: heat-related signals correlated with throughput drop."
        )),
        (r"dns|resolution failure", (
            "HYPOTHESIS: dns resolution failure causing connection timeouts.\n"
            "CLAIM 1: repeated NXDOMAIN errors appear in service logs. | SUPPORTS: [0, 1]\n"
            "CLAIM 2: latency spike began before any deploy events. | SUPPORTS: [0]\n"
            "RAW_CONFIDENCE: 0.60\n"
            "RATIONALE: DNS error pattern precedes all other signals."
        )),
        (r"memory|oom", (
            "HYPOTHESIS: memory pressure causing OOM events and service restarts.\n"
            "CLAIM 1: memory utilization at 0.94, OOM events observed in last 5 minutes. | SUPPORTS: [0, 1]\n"
            "RAW_CONFIDENCE: 0.68\n"
            "RATIONALE: OOM events directly explain service instability pattern."
        )),
        (r"certificate|cert|expir", (
            "HYPOTHESIS: certificate expiry causing TLS handshake failures across services.\n"
            "CLAIM 1: TLS errors correlated with certificate expiry window in current findings. | SUPPORTS: [0]\n"
            "CLAIM 2: no deploy events rule out regression as primary cause. | SUPPORTS: [0]\n"
            "RAW_CONFIDENCE: 0.70\n"
            "RATIONALE: expiry-pattern errors align with observed anomaly window."
        )),
        (r"disk|io_wait|disk pressure", (
            "HYPOTHESIS: disk pressure causing elevated I/O wait and service degradation.\n"
            "CLAIM 1: disk_io_wait elevated beyond normal operating range. | SUPPORTS: [0, 1]\n"
            "RAW_CONFIDENCE: 0.65\n"
            "RATIONALE: I/O wait elevation directly explains request latency increase."
        )),
        (r"dependency|cascade|downstream", (
            "HYPOTHESIS: dependency cascade propagating failures from upstream service.\n"
            "CLAIM 1: upstream dependency anomaly precedes local service degradation. | SUPPORTS: [0]\n"
            "CLAIM 2: primary metric degradation began after upstream error spike. | SUPPORTS: [0, 1]\n"
            "RAW_CONFIDENCE: 0.62\n"
            "RATIONALE: cascade pattern — local metrics follow upstream timing."
        )),
    ]
    REASONING_FALLBACK = (
        "HYPOTHESIS: unable to confidently classify with available evidence.\n"
        "CLAIM 1: multiple signals present but no dominant pattern identified. | SUPPORTS: [0]\n"
        "RAW_CONFIDENCE: 0.30\n"
        "RATIONALE: insufficient telemetry overlap to form high-confidence hypothesis."
    )

    # Falsifier responses — keyed by hypothesis substring
    FALSIFIER_RESPONSES = [
        (r"connection pool", (
            "VERDICT: confirmed\n"
            "CONTRADICTION 1: none — db-proxy utilization finding directly supports pool exhaustion.\n"
            "UNFALSIFIABLE: CLAIM 1 — no contradicting evidence in findings.\n"
            "UNFALSIFIABLE: CLAIM 2 — deploy timestamp aligns; no evidence of prior instability.\n"
            "FALSIFICATION_SCORE: 0.08\n"
        )),
        (r"thermal throttling", (
            "VERDICT: confirmed\n"
            "CONTRADICTION 1: none — thermal signals consistent across affected nodes.\n"
            "UNFALSIFIABLE: CLAIM 1 — rack-level pattern supports throttling diagnosis.\n"
            "FALSIFICATION_SCORE: 0.10\n"
        )),
        (r"dns resolution", (
            "VERDICT: contested\n"
            "CONTRADICTION 1: deploy_log shows a deploy 18 minutes before DNS errors — deploy regression "
            "cannot be ruled out as a competing cause. | FINDING: 2\n"
            "UNFALSIFIABLE: CLAIM 1 — NXDOMAIN errors are real but could be downstream effect.\n"
            "FALSIFICATION_SCORE: 0.42\n"
        )),
        (r"regression|recent deployment", (
            "VERDICT: confirmed\n"
            "CONTRADICTION 1: none — metric anomaly window is tightly correlated with deploy.\n"
            "FALSIFICATION_SCORE: 0.12\n"
        )),
        (r"memory pressure|oom", (
            "VERDICT: confirmed\n"
            "CONTRADICTION 1: none — OOM events directly confirmed by prometheus and logs.\n"
            "FALSIFICATION_SCORE: 0.05\n"
        )),
        (r"certificate|cert|expir", (
            "VERDICT: confirmed\n"
            "CONTRADICTION 1: none — TLS error pattern matches certificate expiry window.\n"
            "FALSIFICATION_SCORE: 0.09\n"
        )),
        (r"disk|io_wait", (
            "VERDICT: confirmed\n"
            "CONTRADICTION 1: none — disk I/O wait elevation is directly measured.\n"
            "FALSIFICATION_SCORE: 0.07\n"
        )),
        (r"dependency|cascade", (
            "VERDICT: contested\n"
            "CONTRADICTION 1: local deployment 12 minutes ago — could be regression, not cascade. | FINDING: 1\n"
            "FALSIFICATION_SCORE: 0.38\n"
        )),
    ]
    FALSIFIER_FALLBACK = (
        "VERDICT: contested\n"
        "CONTRADICTION 1: insufficient findings to fully confirm or refute hypothesis.\n"
        "FALSIFICATION_SCORE: 0.45\n"
    )

    # Counterfactual responses — keyed by hypothesis substring
    COUNTERFACTUAL_RESPONSES = [
        (r"connection pool", (
            "PREDICTION: rolling back the db-proxy deploy will resolve pool exhaustion.\n"
            "DELTA 1: payments-service p99_latency_ms | change: drops 60-80% from current elevated value | "
            "lower: 0.60 | upper: 0.80\n"
            "DELTA 2: db-proxy utilization | change: recovers to baseline ~0.45 | lower: 0.55 | upper: 0.75\n"
            "DELTA 3: auth-service utilization | change: no expected change | lower: -0.05 | upper: 0.05\n"
            "PREDICTION_CONFIDENCE: 0.78\n"
            "METHOD: rule_based\n"
        )),
        (r"thermal throttling", (
            "PREDICTION: draining affected hosts will stop throttling-related throughput loss.\n"
            "DELTA 1: cpu_throttle_ratio | change: drops to 0 on drained hosts | lower: 0.80 | upper: 0.95\n"
            "DELTA 2: request_throughput | change: recovers after traffic rebalances | lower: 0.60 | upper: 0.85\n"
            "PREDICTION_CONFIDENCE: 0.70\n"
            "METHOD: rule_based\n"
        )),
        (r"dns|resolution", (
            "PREDICTION: flushing DNS cache will reduce NXDOMAIN errors, but root cause may persist.\n"
            "DELTA 1: dns_latency_ms | change: drops 30-50% if misconfig is transient | lower: 0.30 | upper: 0.50\n"
            "DELTA 2: service error_rate | change: uncertain — depends on whether upstream is also affected | "
            "lower: 0.10 | upper: 0.60\n"
            "PREDICTION_CONFIDENCE: 0.48\n"
            "METHOD: rule_based\n"
        )),
        (r"regression|deploy", (
            "PREDICTION: rolling back will restore pre-deploy performance baseline.\n"
            "DELTA 1: primary metric | change: returns to pre-deploy baseline within 2-3 min | "
            "lower: 0.65 | upper: 0.85\n"
            "PREDICTION_CONFIDENCE: 0.75\n"
            "METHOD: rule_based\n"
        )),
        (r"memory|oom", (
            "PREDICTION: restarting the service will clear memory pressure temporarily.\n"
            "DELTA 1: memory_utilization | change: drops to ~0.40 immediately post-restart | "
            "lower: 0.55 | upper: 0.80\n"
            "DELTA 2: OOM event rate | change: drops to 0 immediately | lower: 0.90 | upper: 1.0\n"
            "PREDICTION_CONFIDENCE: 0.72\n"
            "METHOD: rule_based\n"
        )),
        (r"certificate|cert|expir", (
            "PREDICTION: rotating certificate will immediately restore TLS handshake success.\n"
            "DELTA 1: tls_error_rate | change: drops to 0 within seconds of rotation | "
            "lower: 0.90 | upper: 1.0\n"
            "PREDICTION_CONFIDENCE: 0.85\n"
            "METHOD: rule_based\n"
        )),
        (r"disk|io_wait", (
            "PREDICTION: expanding volume removes the saturation constraint on I/O wait.\n"
            "DELTA 1: disk_io_wait | change: drops 50-70% after volume expansion completes | "
            "lower: 0.50 | upper: 0.70\n"
            "PREDICTION_CONFIDENCE: 0.68\n"
            "METHOD: rule_based\n"
        )),
        (r"dependency|cascade", (
            "PREDICTION: isolating the failing dependency will stop cascade propagation.\n"
            "DELTA 1: local_error_rate | change: drops 40-60% after dependency isolation | "
            "lower: 0.40 | upper: 0.60\n"
            "DELTA 2: upstream_dependency_errors | change: unchanged — root is in dependency | "
            "lower: 0.0 | upper: 0.1\n"
            "PREDICTION_CONFIDENCE: 0.58\n"
            "METHOD: rule_based\n"
        )),
    ]
    COUNTERFACTUAL_FALLBACK = (
        "PREDICTION: outcome uncertain — no matching causal rule for this hypothesis.\n"
        "DELTA 1: primary metric | change: unknown | lower: 0.0 | upper: 1.0\n"
        "PREDICTION_CONFIDENCE: 0.30\n"
        "METHOD: llm_assisted\n"
    )

    def complete(self, prompt: str) -> str:
        prompt_lower = prompt.lower()

        if "falsif" in prompt_lower or "disprove" in prompt_lower or "contradict" in prompt_lower:
            for pattern, response in self.FALSIFIER_RESPONSES:
                if re.search(pattern, prompt_lower):
                    return response
            return self.FALSIFIER_FALLBACK

        if "counterfactual" in prompt_lower or "predict" in prompt_lower or "post-action" in prompt_lower:
            for pattern, response in self.COUNTERFACTUAL_RESPONSES:
                if re.search(pattern, prompt_lower):
                    return response
            return self.COUNTERFACTUAL_FALLBACK

        for pattern, response in self.REASONING_RESPONSES:
            if re.search(pattern, prompt_lower):
                return response
        return self.REASONING_FALLBACK


class OpenAIBackend:
    """Thin wrapper. Requires `openai` extra installed and OPENAI_API_KEY set."""

    def __init__(self, model: str = "gpt-4o-mini"):
        from openai import OpenAI  # noqa: F401 — runtime import
        self._client = OpenAI()
        self._model = model

    def complete(self, prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        return resp.choices[0].message.content or ""


class AnthropicBackend:
    """Stubbed Anthropic backend. Requires `anthropic` extra."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        import anthropic  # noqa: F401
        self._client = anthropic.Anthropic()
        self._model = model

    def complete(self, prompt: str) -> str:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text


def get_backend() -> ChatBackend:
    """Return the configured backend. Defaults to deterministic fake."""
    backend = os.environ.get("MAO_MODEL_BACKEND", "fake").lower()
    if backend == "openai":
        return OpenAIBackend()
    if backend == "anthropic":
        return AnthropicBackend()
    return DeterministicFake()


def parse_hypothesis(text: str) -> tuple[str, float, str]:
    """Parse the legacy flat response format (kept for backward compatibility).

    Returns (summary, confidence, rationale). The reasoning agent uses
    parse_hypothesis_v2() which extracts provenance-bound claims.
    """
    summary = ""
    confidence = 0.0
    rationale = ""
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("HYPOTHESIS:"):
            summary = line.split(":", 1)[1].strip()
        elif line.upper().startswith("RAW_CONFIDENCE:") or line.upper().startswith("CONFIDENCE:"):
            try:
                confidence = float(line.split(":", 1)[1].strip())
            except ValueError:
                confidence = 0.0
        elif line.upper().startswith("RATIONALE:"):
            rationale = line.split(":", 1)[1].strip()
    if not summary:
        summary = text.strip().split("\n", 1)[0]
    return summary, max(0.0, min(1.0, confidence)), rationale
