# Code walkthrough

Step-by-step trace of what happens when the system processes an alert. Read this with `examples/run_synthetic_incident.py` open in another tab.

---

## Setup: building the alert

```python
trigger = AlertTrigger(
    alert_id="alert-001",
    service="payments-service",
    metric="p99_latency_ms",
    value=820.0,
    threshold=500.0,
    classification="application",
)
state = new_state(incident_id="inc-2026-0001", trigger=trigger)
```

`AlertTrigger` (in `agents/state.py`) is a dataclass holding everything we know about the incoming alert. `new_state(...)` constructs a fresh `InvestigationState` dict with the trigger embedded, empty findings/actions/audit-trail lists, and a single audit-trail entry recording that the investigation was opened.

At this point the state looks like:

```python
{
  "incident_id": "inc-2026-0001",
  "trigger": AlertTrigger(...),
  "routed_to": [],
  "telemetry_findings": [],
  "causal_hypothesis": None,
  "recommended_actions": [],
  "confidence_score": 0.0,
  "audit_trail": [AgentStep(agent="system", description="Investigation opened ...")],
  "requires_human_approval": True,
}
```

---

## Step 1: graph construction

```python
graph = build_investigation_graph()
```

`build_investigation_graph()` (in `agents/graph.py`) checks if `langgraph` is installed.

**If yes:** builds a `StateGraph(InvestigationState)`, adds each agent as a node, wires the edges in pipeline order, sets the entry point to `supervisor`, and compiles. Returns the compiled graph.

**If no:** returns a `_SimplePipeline()` instance — a tiny class that just loops through `_PIPELINE` synchronously. Both return objects with the same `.invoke(state)` interface.

The fallback exists so the demo runs in any environment. Tests use the fallback to stay fast and deterministic.

---

## Step 2: supervisor runs

```python
state = supervisor_step(state)
```

The supervisor (`agents/supervisor.py`) does exactly two things:

1. Looks up `state["trigger"].classification` in `ROUTING_TABLE`. Our trigger is classified as `"application"`, which maps to `["telemetry", "logs", "reasoning", "action"]`.
2. Writes `state["routed_to"] = [...]` and appends an `AgentStep` to `audit_trail`.

After this step, the state has:

```python
{
  ...
  "routed_to": ["telemetry", "logs", "reasoning", "action"],
  "audit_trail": [
    AgentStep(agent="system", ...),
    AgentStep(agent="supervisor", description="Classified as 'application'; routing to [...]"),
  ],
}
```

**Notable:** the supervisor is deterministic code, not an LLM. The reason is in `docs/design.md` — routing is finite mapping, code is faster and testable.

---

## Step 3: telemetry collects findings

```python
state = telemetry_step(state)
```

The telemetry agent (`agents/telemetry.py`) is the data-gathering specialist. It runs four queries in sequence:

### 3a. Primary metric

```python
metric_result = query_metric(
    service="payments-service",
    metric="p99_latency_ms",
    window_minutes=15,
)
```

`query_metric` (in `tools/prometheus_mock.py`) looks up the (service, metric) pair in `_SCENARIOS`. The mock returns:

```python
{
  "summary": "p99 elevated to ~820ms vs baseline 220ms over last 5 min",
  "anomaly": True,
  "dependencies": ["db-proxy", "auth-service"],
  "raw_samples": [220, 225, 410, 720, 820, 815],
}
```

The agent wraps this in a `Finding` and appends to `state["telemetry_findings"]`.

### 3b. Dependency metrics

Because the primary metric flagged `anomaly: True` and listed dependencies, the agent fans out:

```python
for dep in metric_result["dependencies"]:
    dep_result = query_metric(service=dep, metric="utilization", window_minutes=15)
```

This produces two more findings — one for `db-proxy` (anomalous: connection pool at 0.97) and one for `auth-service` (normal: 0.32 utilization).

### 3c. Recent deploys

```python
deploys = recent_deploys(service="payments-service", window_minutes=60)
```

`recent_deploys` (in `tools/deploy_log_mock.py`) returns deploys keyed by service. The mock has one entry for `payments-service` (version 1.42.0 from 3 hours ago).

### 3d. Error logs

```python
log_hits = search_logs(service="payments-service", window_minutes=15, level_at_least="ERROR")
```

`search_logs` (in `tools/logs_mock.py`) filters by service and log level. For `payments-service` it returns two `ERROR` entries about connection pool exhaustion and request timeouts.

After this step, `state["telemetry_findings"]` has five entries: 1 primary metric, 2 dependency metrics, 1 deploy entry, 1 log signal.

**Notable:** the telemetry agent never interprets. It collects. Interpretation is the reasoning agent's job.

---

## Step 4: reasoning forms a hypothesis

```python
state = reasoning_step(state)
```

The reasoning agent (`agents/reasoning.py`) is the only agent in the pipeline that calls an LLM. The flow:

### 4a. Build the prompt

```python
prompt = _build_prompt(state)
```

`_build_prompt` constructs a structured prompt that includes the alert details and a numbered list of all findings collected so far. The prompt asks for output in a specific format:

```
HYPOTHESIS: <one-sentence root-cause hypothesis>
CONFIDENCE: <float between 0 and 1>
RATIONALE: <one-sentence reason>
```

### 4b. Call the model

```python
backend = get_backend()
raw = backend.complete(prompt)
```

`get_backend()` (in `agents/llm.py`) reads the `MAO_MODEL_BACKEND` env var. By default it returns `DeterministicFake()`, which matches the prompt against substring patterns and returns canned responses. With `MAO_MODEL_BACKEND=openai`, it returns a real OpenAI client.

For our test prompt (which mentions "connection pool" in the findings), the deterministic fake returns:

```
HYPOTHESIS: connection pool exhaustion in recently deployed service.
CONFIDENCE: 0.72
RATIONALE: telemetry shows elevated pool utilization correlated with recent deploy.
```

### 4c. Parse the response

```python
summary, confidence, rationale = parse_hypothesis(raw)
```

`parse_hypothesis` (in `agents/llm.py`) does a simple line-by-line parse. If the model returns malformed output, it falls back to taking the first line as the summary and a confidence of 0.0. The parsed values are clamped to [0, 1] for safety.

### 4d. Build the Hypothesis and write to state

```python
hypothesis = Hypothesis(
    summary=summary,
    confidence=confidence,
    supporting_finding_ids=[i for i, f in enumerate(findings) if f.severity != "info"],
    references=[rationale],
)
state["causal_hypothesis"] = hypothesis
state["confidence_score"] = confidence
```

`supporting_finding_ids` lists which findings in `state["telemetry_findings"]` actually drove the hypothesis. For our example it's `[0, 1, 4]` — the anomalous primary metric, the db-proxy utilization, and the error logs.

---

## Step 5: action proposes a remediation

```python
state = action_step(state)
```

The action agent (`agents/action.py`) does pattern matching against the hypothesis summary, then enforces the human-approval gate.

### 5a. Match the hypothesis to a remediation pattern

```python
for pattern, action in REMEDIATION_PATTERNS:
    if pattern in summary_lower:
        selected = action
        break
```

`REMEDIATION_PATTERNS` is a list of `(substring, Action)` tuples. The first match wins. For "connection pool exhaustion in recently deployed service", the `"connection pool"` pattern matches and selects:

```python
Action(
    description="Roll back the most recent deploy of the affected service.",
    risk_level="medium",
    requires_approval=True,
    rationale="Connection-pool regressions are most commonly fixed by reverting to the prior known-good version.",
)
```

If no pattern matches, `DEFAULT_ACTION` is used — a generic "escalate to human with current state."

### 5b. Apply the autonomous-action gate

```python
autonomous = (
    ENABLE_AUTONOMOUS_LOW_RISK
    and selected.risk_level == "low"
    and confidence >= AUTONOMOUS_CONFIDENCE_FLOOR
)
```

Default config: `ENABLE_AUTONOMOUS_LOW_RISK = False`. So `autonomous` is always False, regardless of confidence or risk level. The selected action gets `requires_approval=True` overwritten if the gate is closed.

### 5c. Write to state

```python
state["recommended_actions"].append(selected_with_gate)
state["requires_human_approval"] = selected_with_gate.requires_approval
state["audit_trail"].append(AgentStep(agent="action", description="recommended: ..."))
```

---

## Step 6: final state

The pipeline is now complete. The final state contains:

- 5 findings in `telemetry_findings`
- 1 hypothesis in `causal_hypothesis` (confidence 0.72)
- 1 action in `recommended_actions` (rollback, requires approval)
- 5 entries in `audit_trail` (system + supervisor + telemetry + reasoning + action)
- `requires_human_approval: True`

The `examples/run_synthetic_incident.py` script prints this state in a human-readable form. In a real deployment, the state would be:

1. Persisted to a database (for replay and audit).
2. Sent to the on-call engineer's tool of choice (Slack, PagerDuty, Opsgenie).
3. Made queryable via a UI so the engineer can inspect the reasoning before approving.

---

## What the audit trail looks like

The single most useful artifact for debugging:

```
[2026-05-17T10:00:01Z] system       Investigation opened for alert alert-001
[2026-05-17T10:00:01Z] supervisor   Classified as 'application'; routing to [telemetry, logs, reasoning, action]
[2026-05-17T10:00:02Z] telemetry    Collected 5 findings from 3 anomalous sources
[2026-05-17T10:00:03Z] reasoning    hypothesis (conf=0.72): connection pool exhaustion in recently deployed service
[2026-05-17T10:00:03Z] action       recommended: Roll back the most recent deploy of the affected service (approval required: True)
```

When something goes wrong, this is where to look first. Every agent records what it did. Every transition is timestamped. The full trail plus the structured `InvestigationState` is the audit record.
