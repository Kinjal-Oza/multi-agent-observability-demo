# Implementation Map

Each of the four core mechanisms in this architecture is cross-referenced to
the specific file, class, or function that implements it. This document is
maintained alongside the code so a reviewer can verify every mechanism
against a running implementation.

---

## Mechanism 1 — Provenance-Bound Causal Claims

A reasoning agent emits a hypothesis composed of one or more provenance-bound
claims. Each claim references one or more finding identifiers. The system
rejects any claim lacking at least one finding-identifier reference.

| Element | Implementation |
|---------|---------------|
| `Claim` dataclass with `supporting_finding_ids` | `agents/state.py` — `class Claim` |
| Rejection of empty `supporting_finding_ids` | `agents/state.py` — `Claim.__post_init__()` raises `ValueError` |
| Reasoning agent emitting provenance-bound claims | `agents/reasoning.py` — `_parse_claims()`, `reasoning_step()` |
| LLM prompt requiring SUPPORTS citations | `agents/llm.py` — `DeterministicFake` response format |
| Audit trail logging dropped ungrounded claims | `agents/reasoning.py` — audit step in `reasoning_step()` |

Test coverage: `tests/test_state.py::test_claim_requires_supporting_findings`,
`tests/test_reasoning.py::test_reasoning_produces_provenance_bound_claims`

---

## Mechanism 2 — Adversarial Hypothesis Falsification

A dedicated adversarial falsifier agent, given the hypothesis and the finding
set, returns a verdict from a finite set {confirmed, contested, refuted}. A
`refuted` verdict prevents downstream autonomous action.

| Element | Implementation |
|---------|---------------|
| Falsifier agent | `agents/falsifier.py` — `falsifier_step()` |
| `FalsificationResult` with `verdict` field | `agents/state.py` — `class FalsificationResult` |
| Verdict vocabulary enforcement | `agents/state.py` — `FalsificationVerdict = Literal[...]` |
| `refuted` blocking downstream action | `agents/action.py` — `action_step()` falsifier veto block |
| Budget extension on non-refuted verdict | `agents/falsifier.py` — budget extension logic |
| Confidence update after falsification | `agents/falsifier.py` — calls `confidence.update_with_falsification()` |

Test coverage: `tests/test_falsifier.py::test_falsifier_verdict_in_valid_set`,
`tests/test_action.py::test_action_falsifier_veto_overrides_recommendation`

---

## Mechanism 3 — Counterfactual Outcome Simulation

A counterfactual outcome simulator, given a proposed remediation action and a
current state, returns a set of predicted state deltas with associated
confidence bounds prior to any execution of the proposed action.

| Element | Implementation |
|---------|---------------|
| Counterfactual simulator agent | `agents/counterfactual.py` — `counterfactual_step()` |
| `CounterfactualPrediction` with `predicted_deltas` | `agents/state.py` — `class CounterfactualPrediction` |
| `PredictedDelta` with `lower_bound`, `upper_bound` | `agents/state.py` — `class PredictedDelta` |
| Deterministic causal rule table (primary path) | `agents/counterfactual.py` — `_CAUSAL_RULES` |
| LLM-driven fallback (alternative path) | `agents/counterfactual.py` — `_llm_predict()` |
| `simulator_method` field identifying path used | `agents/state.py` — `SimulatorMethod = Literal[...]` |
| Pre-execution placement in pipeline | `agents/graph.py` — counterfactual runs before action |

Test coverage: `tests/test_counterfactual.py::test_counterfactual_populates_field`,
`tests/test_counterfactual.py::test_counterfactual_deltas_have_valid_bounds`

---

## Mechanism 4 — Calibrated Confidence via Learned Prior

A calibrated confidence module computes a posterior confidence as a weighted
ensemble of (a) language-model self-reported confidence, (b) a prior
probability derived from a historical incident corpus, and (c) a
falsification-score modifier.

| Element | Implementation |
|---------|---------------|
| Calibration module | `agents/confidence.py` — `calibrate()`, `update_with_falsification()` |
| `CalibratedConfidence` dataclass | `agents/state.py` — `class CalibratedConfidence` |
| Formula: `0.4*raw_llm + 0.4*prior + 0.2*modifier` | `agents/confidence.py` — `_compute()` |
| Historical corpus prior | `corpus/causal_prior.py` — `prior_for()` |
| Corpus frequency table | `corpus/incidents.jsonl` — 100 ground-truth labeled incidents |
| Post-falsification confidence update | `agents/confidence.py` — `update_with_falsification()` |
| Component breakdown in `CalibratedConfidence.components` | `agents/confidence.py` — returned dict |

Test coverage: `tests/test_confidence.py::test_calibrate_returns_calibrated_confidence`,
`tests/test_confidence.py::test_compute_formula`

---

## Measurability

The four mechanisms are measurable, not just descriptive:

| Metric | Measured by | Value (DeterministicFake, N=100) |
|--------|-------------|----------------------------------|
| Hypothesis accuracy | `bench/metrics.py::hypothesis_accuracy` | 0.78 |
| Brier score | `bench/metrics.py::brier_score` | 0.199 |
| ECE | `bench/metrics.py::expected_calibration_error` | 0.337 |
| Falsifier precision | `bench/metrics.py::falsifier_precision` | 1.00 |
| Falsifier recall | `bench/metrics.py::falsifier_recall` | 0.89 |
| Action precision | `bench/metrics.py::action_precision` | 0.64 |

To reproduce: `python -m bench.run_benchmark`

---

## Extension Mechanisms

The following mechanisms are described in `docs/design.md` as natural
extensions of the architecture. They are not all implemented in this
reference demo:

| Mechanism | Status in demo code |
|-----------|---------------------|
| Tiered action classification (Tier 1/2/3) | Partially implemented in `agents/action.py` (`risk_level` field) |
| Compound safety gate (confidence + falsifier + counterfactual + risk) | Parameterised in `agents/action.py` |
| Kill switch via distributed key-value store | Documented in `docs/design.md`; not in demo (would require a Redis client) |
| Per-tool circuit breaker | Documented; not in demo code |
| Parallel specialist-agent fan-out | Documented; demo uses sequential execution for clarity |
| Checkpointing to durable storage | Handled by LangGraph when installed |
| State compression | Documented in `docs/design.md` |
| Slack approval integration | Documented; not in demo code |
