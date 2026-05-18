# Design document

## Purpose

This document explains **why** the system is shaped the way it is. The README explains what's in the repo. The architecture doc explains how the pieces fit together. This document explains the design decisions, the alternatives considered, and the tradeoffs accepted.

---

## Problem definition

Build a software system that can take a production-style infrastructure alert, investigate it across multiple observability sources, form a hypothesis about the root cause, and propose a remediation — while remaining auditable, debuggable, and safe enough that a human reviewer would let it touch production after enough iteration.

Out of scope for this implementation:
- Real production telemetry (mocks only)
- Autonomous action execution (always behind a human gate)
- Multi-tenant isolation (single-tenant only)
- Streaming output (synchronous only)

In scope:
- A defensible architectural pattern
- Working code that demonstrates the pattern end-to-end
- Tests that prove the pattern's invariants
- Documentation that explains the design choices honestly

---

## The fundamental choice: single agent vs multi-agent

The first decision was whether to use one large agent with all tools, or multiple specialized agents.

### Option A: Single agent

A single LLM is given access to all observability tools (Prometheus, logs, deploy log) and a system prompt that says "investigate this alert."

**Pros:**
- Simpler code: one prompt, one tool list, one model call.
- Fewer moving parts at the orchestration layer.
- No state-passing complexity.

**Cons:**
- Every tool result accumulates in the agent's context. By the time you've made 10–15 tool calls, the prompt has hundreds of tokens of partial data. The agent's effective reasoning capacity drops as context fills.
- The probability of a hallucinated tool call grows with the number of available tools.
- A single agent that "loses track" mid-investigation has no fallback path. Either the run completes or it doesn't.
- The audit trail is just the message history. Hard to inspect, hard to reason about.

### Option B: Multi-agent (chosen)

Multiple specialized agents with bounded responsibilities, communicating through a shared typed state.

**Pros:**
- Each agent's context is small and focused.
- Each agent's tool set is small enough that tool hallucination becomes rare.
- Failures are bounded — if reasoning fails, you still have telemetry findings to fall back on.
- The shared state is the audit trail; it's structured and inspectable.
- Easy to swap one agent's implementation without touching others.

**Cons:**
- More moving parts. More code.
- State-passing requires discipline. Get the schema wrong and you have a tangled mess.
- Latency: every agent transition is a step. If you naïvely sequence four agents, you wait for four LLM calls in series.

The cons are real. They are also tractable through engineering — careful schema design, parallel agent execution where dependencies allow, and good observability into the agent pipeline itself. The cons of the single-agent design (context bloat, hallucinated tools) are not tractable; they're fundamental to the architecture.

We picked multi-agent.

---

## The shared state choice: typed vs free-form

Once we committed to multi-agent, the next decision was how agents communicate.

### Option A: Message passing (free-form text)

Each agent produces a natural-language summary of what it did. The next agent reads the summary and adds its own.

This is the "LangChain agent chain" default. It's seductive because it's easy.

**Why we rejected it:**
- The next agent has to *parse* the previous agent's prose to extract structured information. Parsing prose is brittle.
- Important details get lost in summarization.
- The "audit trail" is a transcript, not a structured record. Hard to query, hard to assert against in tests.

### Option B: Typed shared state (chosen)

A `TypedDict` with explicit fields. Every agent reads and writes structured data. Finding objects have a `source`, `description`, `severity`, and `raw` payload. Hypotheses have a `confidence` float. Actions have a `risk_level` enum.

**Why we picked it:**
- Downstream agents can query exactly the field they care about. No parsing.
- The state itself is the audit trail. You can dump it to JSON, query it, diff it across runs.
- Tests can assert against state shape directly.
- New agent types can be added without changing existing agents — they just add new fields.

The schema is in `agents/state.py`. It is the single most important file in the repo. Get the schema right and everything else falls into place. Get it wrong and you'll be refactoring forever.

---

## Why the reasoning agent is the only LLM-driven agent

It's tempting to LLM-ify every agent. We deliberately don't.

| Agent | Implementation | Why |
|-------|---------------|-----|
| Supervisor | Code (dict lookup) | Routing is a small finite mapping. Code is faster, deterministic, and testable. |
| Telemetry  | Code (tool calls) | Tool invocation is deterministic; an LLM doesn't add value over typed function calls. |
| Reasoning  | LLM call          | Causal reasoning over heterogeneous signals is genuinely model-shaped work. |
| Action     | Code (pattern match) | Action selection is a finite mapping from hypothesis class to remediation. Code is auditable. |

The general rule: **use an LLM only when the work is genuinely model-shaped**. Routing, tool invocation, and action selection are not model-shaped. Reasoning over fuzzy text-heavy signals is.

This keeps the system cheap, fast, and predictable. LLM calls are the slowest and most variable part of the pipeline. Minimizing them minimizes the surface area for unpredictability.

---

## Why the action agent never executes autonomously

This is the most important safety decision in the repo.

The action agent COULD be wired to call APIs that restart pods, roll back deploys, or update load balancer configs. We deliberately don't.

**Reasoning:**
- A high-confidence wrong hypothesis is a real possibility. We have not yet characterized the failure rate of the reasoning agent in any way that justifies autonomous action.
- The cost of "human approves a correct action 30 seconds later" is small. The cost of "agent executes an incorrect remediation that makes the incident worse" is large and difficult to recover from.
- The asymmetry of cost makes the human gate a clear win for any first deployment.

The threshold parameters (`AUTONOMOUS_CONFIDENCE_FLOOR`, `ENABLE_AUTONOMOUS_LOW_RISK`) are exposed so a future deployment can relax the gate after measuring real precision/recall. But the default position is closed.

This is the kind of decision that's easy to undo (flip a flag) but hard to recover from (autonomous bad action). Default to the safer side.

---

## Why LangGraph (not LangChain, not raw orchestration)

We considered three orchestration approaches:

### Raw orchestration (chosen as fallback)

Just sequence the agent functions in `_PIPELINE`. Loop through them. Pass state.

**When it's fine:** small pipelines, no branching, no retries.
**When it breaks down:** anything with conditional routing, retries, or human-in-loop pauses.

### LangChain (rejected)

LangChain's agent abstractions are designed for single-agent loops, not multi-agent state graphs. We'd be fighting the framework.

### LangGraph (primary target)

Built specifically for stateful, multi-step agent workflows. The state-graph model maps directly onto our pattern.

**Why LangGraph:**
- Explicit state graph, declarative routing.
- Built-in support for conditional edges, retry policies, human-approval pauses.
- Production deployments at scale already exist; not a research project.
- The state graph is *code*, which means it's versionable and testable.

The repo supports both modes (LangGraph when installed, raw orchestration when not) so the demo can run anywhere. Production users will use LangGraph.

---

## What we did NOT build (and why)

These were deliberately omitted because they would obscure the pattern.

| Omitted | Why |
|---------|-----|
| Streaming output | Synchronous output makes the audit trail readable in a single pass. Streaming is a production concern, not a pattern concern. |
| Persistent state storage | The pattern works with any storage. Adding a specific DB choice would imply a recommendation we don't want to make. |
| Multi-tenant agent pools | Single-tenant is enough to demonstrate the pattern. Multi-tenant is an orthogonal concern. |
| Real Prometheus/Loki integration | Mocks make the demo reproducible. Integration is a 50-line client wrapper away. |
| Cost tracking | Real deployments need it. The pattern doesn't depend on it. |
| Distributed tracing across agents | LangSmith / OpenTelemetry handles this. Adding our own would duplicate. |

If you're using this code as a starting point for a production system, all of the above need to be added. The architecture pattern doesn't change.

---

## Performance and cost considerations

Approximate per-investigation costs in the current shape:

| Component | Cost |
|-----------|------|
| Supervisor | 0 (code-only) |
| Telemetry  | N tool calls (free, mocked) |
| Reasoning  | 1 LLM call (~500 input tokens, ~100 output) |
| Action     | 0 (code-only) |

**Total LLM cost per investigation: 1 call.**

This is intentional. Most multi-agent systems make 5–10 LLM calls per investigation. We make 1. The reason: most of the "thinking" work in incident triage isn't actually model-shaped — it's tool invocation and pattern matching, which are cheaper and more reliable as code.

Real production deployments may want a second LLM call for action selection (mapping hypothesis to remediation when the static pattern table isn't expressive enough). That's the natural next iteration.

---

## What would change in a production version

Honest list of what we'd add if this were going into production:

1. **Real tool clients** — Prometheus, Loki, Tempo, Argo, Datadog clients with retries, timeouts, circuit breakers.
2. **Persistent state** — Postgres or DynamoDB for `InvestigationState`. Resumption support.
3. **Multi-model fallback** — Use a cheaper model first, escalate to a stronger one if confidence is low.
4. **Calibration dataset** — Run the reasoning agent against historical incidents to measure precision/recall.
5. **Cost budgets per investigation** — Hard cap on LLM spend.
6. **Streaming partial findings to the on-call engineer** — Don't wait for the full investigation before showing context.
7. **Feedback loop** — When the human approver rejects an action, feed that signal back into the reasoning agent.
8. **A11y and accessibility for the human approver UI** — Out of scope for this code, but real for production.

None of these change the underlying pattern. They're all engineering work on top of it.
