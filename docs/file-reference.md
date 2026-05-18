# File reference

What every file in the repository does, what it depends on, and how it's used.

---

## Root files

### `README.md`
The repo's front page. Explains why the project exists, gives a quick-start, and points to the docs. First file a visitor reads.

### `LICENSE`
MIT license. Required for any open-source repo. Signals to users that the code can be used freely with attribution.

### `pyproject.toml`
Python package metadata and build configuration. Lists dependencies (`pydantic`, `typing-extensions`), optional extras (`langgraph`, `openai`, `anthropic`, `dev`), and pytest configuration. `pip install -e .` reads this file.

### `.gitignore`
Standard Python gitignore. Keeps build artifacts, virtual environments, and editor scratch files out of git.

### `docker-compose.yml`
Optional observability stack: Prometheus, Grafana, Loki. Not required to run the agents — the mock tools work standalone. Useful if you want to point the agents at a real local backend.

### `infra/prometheus.yml`
Prometheus scrape config for the docker-compose stack. Minimal — just scrapes Prometheus itself. Real deployments would scrape application targets.

---

## `agents/` — the four-role implementation

### `agents/__init__.py`
Re-exports the public API (`InvestigationState`, `Finding`, `Hypothesis`, `Action`, `AgentStep`, `build_investigation_graph`, `run_investigation`). External code should import from `agents`, not from individual submodules.

### `agents/state.py`
**The single most important file in the repo.**

Defines the data model that flows through the pipeline:

| Type | Purpose |
|------|---------|
| `AlertTrigger` | The alert that started the investigation (alert_id, service, metric, value, threshold, classification). |
| `Finding` | One observation produced by the telemetry agent (source, description, severity, raw payload). |
| `Hypothesis` | The reasoning agent's best guess at root cause (summary, confidence, supporting_finding_ids, references). |
| `Action` | A recommended remediation (description, risk_level, requires_approval, rationale). |
| `AgentStep` | One audit-trail entry (agent name, description, timestamp). |
| `InvestigationState` | The TypedDict that holds all of the above plus the audit_trail and approval flag. |

Also provides `new_state(incident_id, trigger)` — the constructor for a fresh state object.

Used by every agent and every test. Get the schema wrong here and the rest of the codebase has to follow.

### `agents/supervisor.py`
The supervisor agent. Receives the raw alert, looks up the classification in `ROUTING_TABLE`, writes the routing decision to state.

Dependencies: `agents/state.py` (for `AgentStep`, `InvestigationState`).

Notable: **does not call an LLM.** Routing is a small finite mapping — code is faster, deterministic, and testable.

### `agents/telemetry.py`
The telemetry investigator. Given a trigger, runs queries against the mock tools (`prometheus_mock`, `logs_mock`, `deploy_log_mock`), wraps results as `Finding` objects, appends to state.

Dependencies: `agents/state.py`, `tools/prometheus_mock.py`, `tools/logs_mock.py`, `tools/deploy_log_mock.py`.

Notable: the agent runs a fixed sequence of queries. It does not let the LLM choose which tools to call. This eliminates an entire class of "hallucinated tool" failures.

### `agents/reasoning.py`
The reasoning agent. Builds a structured prompt from `state["telemetry_findings"]`, calls the LLM backend, parses the response into a `Hypothesis`, writes to state.

Dependencies: `agents/state.py`, `agents/llm.py`.

Notable: this is the **only** agent in the pipeline that calls an LLM. Keeping LLM calls minimal keeps the pipeline cheap, fast, and predictable.

### `agents/action.py`
The action agent. Matches the hypothesis summary against `REMEDIATION_PATTERNS`, selects a recommended `Action`, applies the autonomous-action gate (default: closed), writes to state.

Dependencies: `agents/state.py`.

Notable: `ENABLE_AUTONOMOUS_LOW_RISK = False` by default. Even a 0.99-confidence low-risk action requires human approval. This is the most important safety decision in the repo.

### `agents/graph.py`
Orchestration. Wires the four agents in pipeline order. Builds a LangGraph `StateGraph` when `langgraph` is installed; otherwise falls back to `_SimplePipeline`, a synchronous loop. Both expose `.invoke(state)`.

Dependencies: all four agent modules. Optionally `langgraph` (graceful fallback if missing).

Notable: the fallback exists so the demo runs in any environment. Tests use the fallback to stay fast.

### `agents/llm.py`
Pluggable LLM backend. Defines a `ChatBackend` protocol and three implementations:

| Backend | When used |
|---------|-----------|
| `DeterministicFake` | Default. Returns canned responses keyed by substring match. Makes the demo reproducible. |
| `OpenAIBackend` | `MAO_MODEL_BACKEND=openai`. Requires `openai` extra + `OPENAI_API_KEY`. |
| `AnthropicBackend` | `MAO_MODEL_BACKEND=anthropic`. Requires `anthropic` extra. |

`get_backend()` reads the env var and returns the right one. `parse_hypothesis(text)` extracts the `HYPOTHESIS:` / `CONFIDENCE:` / `RATIONALE:` fields from the model's response.

---

## `tools/` — mock telemetry sources

These are the integration points. To wire the agents to a real observability stack, replace the contents of these files with real client code; the agent layer is unchanged.

### `tools/__init__.py`
Empty package marker.

### `tools/prometheus_mock.py`
Mock Prometheus client. `query_metric(service, metric, window_minutes)` returns a `MetricResult` TypedDict. Lookup is by (service, metric) pair against the `_SCENARIOS` dict. Unknown series return a benign "no data" result so unknown services don't crash the pipeline.

To replace with a real client: swap `_SCENARIOS` for an HTTP call to a Prometheus API endpoint. The TypedDict shape stays the same.

### `tools/logs_mock.py`
Mock log search. `search_logs(service, window_minutes, level_at_least)` returns a list of log entries from `_LOG_FIXTURES`. Filters by log level using `LEVEL_ORDER`.

To replace: point at Loki, Elasticsearch, Splunk, or whatever your log stack is.

### `tools/deploy_log_mock.py`
Mock deploy log. `recent_deploys(service, window_minutes)` returns deploys from `_DEPLOYS`.

To replace: point at ArgoCD, Spinnaker, Jenkins, GitHub Actions, or wherever deploy events are recorded.

---

## `examples/` — runnable demos

### `examples/__init__.py`
Empty package marker.

### `examples/run_synthetic_incident.py`
End-to-end runnable example. Constructs an alert, calls `run_investigation(state)`, prints the final state in a readable format. This is what you run to see the system work.

Usage: `python -m examples.run_synthetic_incident`

---

## `tests/` — pytest suite

All tests use only the deterministic fake backend (no API keys required, fast, reproducible).

### `tests/__init__.py`
Empty package marker.

### `tests/test_state.py`
Tests for `new_state()` initialization and `AgentStep` timestamps. Verifies the state object is well-formed at construction time.

### `tests/test_supervisor.py`
Tests routing decisions for each `TriggerType`. Verifies the supervisor appends an audit step.

### `tests/test_telemetry.py`
Tests that telemetry collects findings from all four mock sources for a known scenario. Tests that an unknown service doesn't crash the pipeline.

### `tests/test_reasoning.py`
Tests that the reasoning agent produces a Hypothesis from a known set of findings. Tests that confidence falls back appropriately when there's no signal.

### `tests/test_action.py`
Tests that the action agent recommends the right remediation for known hypothesis patterns. Tests that the human-approval gate is always closed by default, even at 0.99 confidence.

### `tests/test_end_to_end.py`
Tests that the full pipeline runs and that all four agents appear in the audit trail. Tests that human approval is required at the end.

---

## `docs/` — documentation

### `docs/architecture.md`
Higher-level architecture overview. Explains the four roles, the shared state, and why LangGraph fits.

### `docs/code-walkthrough.md`
Step-by-step trace of what happens when `run_synthetic_incident.py` runs. Useful for understanding the flow without reading every source file.

### `docs/design.md`
The "why" document. Explains the design decisions (multi-agent vs single, typed state vs free-form messages, LLM-only-for-reasoning, human gate always-closed) and the tradeoffs accepted.

### `docs/failure-modes.md`
Honest list of what breaks. Confidence-score calibration, context bloat, mock-tool gaps, agent observability. The list to read before deploying any of this.

### `docs/file-reference.md`
This file.

---

## `.github/workflows/`

### `.github/workflows/ci.yml`
GitHub Actions CI. On every push or PR, installs the package + dev extras, runs `ruff check`, runs `pytest --cov`, and runs the end-to-end example. Green CI = repo is in a working state.
