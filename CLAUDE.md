# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> v2: Six-stage pipeline. Falsifier and Counterfactual agents added. See `docs/implementation-map.md`.

## Commands

```bash
# Install (editable, dev deps)
pip install -e ".[dev]"

# Run all tests with coverage
pytest -v --cov=agents --cov=tools --cov=corpus --cov=bench

# Run a single test file
pytest tests/test_falsifier.py -v

# Lint
ruff check .

# Run the full six-stage pipeline end-to-end
python -m examples.run_synthetic_incident

# Run benchmark against 100 synthetic incidents
python -m bench.run_benchmark

# Regenerate incident corpus (if needed)
python -m corpus.generate
```

Optional extras for real LLM backends:
```bash
pip install -e ".[langgraph]"   # enables LangGraph state graph
pip install -e ".[openai]"      # enables OpenAI backend
pip install -e ".[anthropic]"   # enables Anthropic backend
```

## Architecture

All agents share a single `InvestigationState` TypedDict. Pipeline runs in order:

```
AlertTrigger → supervisor → telemetry → reasoning → falsifier → counterfactual → action
```

1. **Supervisor** (`agents/supervisor.py`) — classifies trigger, sets `routed_to`, assigns `InvestigationBudget`. No LLM.

2. **Telemetry** (`agents/telemetry.py`) — queries mock tool backends, appends `Finding` objects. No LLM.

3. **Reasoning** (`agents/reasoning.py`) — calls LLM. Produces provenance-bound `Hypothesis` where every `Claim` cites at least one Finding ID. Calls `confidence.calibrate()` for a `CalibratedConfidence` object.

4. **Falsifier** (`agents/falsifier.py`) — adversarial agent. Tries to disprove the hypothesis using findings. Sets `FalsificationResult` with verdict `confirmed/contested/refuted`. A `refuted` verdict blocks autonomous action. Updates calibrated confidence via `update_with_falsification()`.

5. **Counterfactual** (`agents/counterfactual.py`) — predicts post-action state deltas (confidence bands) before the action is executed. Rule-based primary path; LLM-assisted fallback.

6. **Action** (`agents/action.py`) — falsifier-aware. If verdict is `refuted`, escalates immediately. Otherwise matches hypothesis to `REMEDIATION_PATTERNS`. Records counterfactual prediction alongside recommendation.

**Graph wiring** (`agents/graph.py`): LangGraph when installed, `_SimplePipeline` fallback. Both expose `.invoke(state)`.

**LLM backend** (`agents/llm.py`): `MAO_MODEL_BACKEND` env var (`fake`/`openai`/`anthropic`). Default `DeterministicFake` covers all 8 cause patterns with canned CLAIM/SUPPORTS/CONTRADICTION responses.

**State schema** (`agents/state.py`): The key types are `Claim` (provenance-bound, raises if `supporting_finding_ids` is empty), `CalibratedConfidence`, `FalsificationResult`, `CounterfactualPrediction`, `PredictedDelta`, `InvestigationBudget`.

**Corpus** (`corpus/`): 100 synthetic incidents with ground-truth cause labels. `causal_prior.py` computes `P(cause|classification)` frequency tables used by `confidence.calibrate()`.

**Benchmark** (`bench/`): Injects corpus findings (bypasses telemetry mock), runs reasoning→falsifier→action, computes Brier score, ECE, falsifier precision/recall, action precision.

## Key design constraints

- Every `Claim` must cite at least one Finding ID — `Claim.__post_init__` raises `ValueError` otherwise.
- Falsifier verdict `refuted` is a hard veto on action; the action agent escalates immediately.
- All actions require human approval by default (autonomous gate is closed).
- Mock tools contain zero real infrastructure data. New scenarios → `_SCENARIOS` dicts.
- LLM response formats are rigid and parsed with regex; see `agents/llm.py` for exact formats.
- CI matrix: Python 3.10, 3.11, 3.12, no optional extras.
