# Failure modes

A truthful list of things that go wrong with this pattern, and what we do about them in the demo. If you're considering taking this to production, read this first.

## 1. Reasoning agent produces confident-wrong hypotheses

The model returns a `CONFIDENCE: 0.87` for a hypothesis that turns out to be completely wrong. The signal in the score is weak — it correlates with how plausible the model finds its own answer, not with how likely the answer is to be correct.

**What we do about it:**
- The action agent does NOT auto-execute based on confidence in this demo (`ENABLE_AUTONOMOUS_LOW_RISK = False`).
- Even at 0.99 confidence, the human approval gate is closed by default.
- For real deployments, calibrate the threshold against historical incidents before relaxing the gate.

**What's left for you to do:**
- Build a calibration dataset of past incidents with known root causes.
- Run the reasoning agent against it offline. Measure precision at various confidence cutoffs.
- Only relax `AUTONOMOUS_CONFIDENCE_FLOOR` based on measured precision, not intuition.

## 2. Context bloat during long investigations

Five services involved, 15 tool calls of accumulated data — and the reasoning agent starts dropping things. The earlier findings get summarized or pushed out of context, and the model loses the thread.

**Mitigations in this demo:**
- The telemetry agent collects everything into structured `Finding` objects in shared state, not raw text in the prompt.
- The reasoning prompt is constructed from `state["telemetry_findings"]` at call time, not accumulated across previous turns.

**What's left for you:**
- For genuinely large investigations, add a summarization pass that compresses earlier findings before handoff to reasoning.
- Be aware: summarization is lossy. The information lost is sometimes the relevant one.

## 3. Mock tool hallucinations don't generalize

The mocks always return well-formed `MetricResult` objects. A real Prometheus client can fail in dozens of ways — connection refused, query timeout, partial response, malformed PromQL. The telemetry agent in this demo doesn't handle those.

**What to add for production:**
- Wrap every tool call in a retry policy.
- Distinguish "tool returned no data" from "tool errored" — different downstream behavior.
- Log every tool failure into the audit trail so post-incident review can spot patterns.

## 4. Agent observability — monitoring the monitor

You're building a system that monitors infrastructure, and now you have to monitor the system. The most common debugging scenario is "the agent took a strange path" with the root cause buried 12 tool calls deep.

**What helps:**
- The `audit_trail` in `InvestigationState` is the first level. Read it.
- LangSmith (or any agent tracing tool) is the second level. Wire it in for production.
- A simple metric on each agent's latency and failure rate is the third level. Don't skip it.

## 5. Hypothesis-to-action pattern matching is fragile

The current `REMEDIATION_PATTERNS` in `agents/action.py` are simple substring matches. The model can produce a hypothesis that mentions "connection pool" in a context where the right action isn't a rollback — and the pattern match will fire anyway.

**Mitigations:**
- Keep the pattern set small.
- Require a confidence floor before any pattern-driven action.
- For production, replace the substring match with a structured taxonomy and a second model call that maps hypothesis to action.

## 6. The supervisor's routing table goes stale

`ROUTING_TABLE` is a hand-coded mapping. New incident types and new specialist agents will need it updated. Forgetting to update it means new incident types fall through to `unknown` routing, which is the slowest path.

**What to add:**
- A test that fails when a new `TriggerType` is added but no routing entry exists.
- An admin command to inspect current routing and validate it against known incident classifications.

## 7. The "we deployed this and it works" narrative trap

The most dangerous failure mode isn't technical — it's how multi-agent results get reported. A pipeline that catches one real anomaly and 50 false positives can be presented as a success if you only show the catch.

**What to do:**
- Track precision and recall on incident triage outcomes the same way you'd track any production metric.
- Report false positives transparently. False positives are the cost the team pays for the catches.
- Treat any agent deployment as an experiment, not a deliverable, until you have at least one quarter of measured precision/recall data.
