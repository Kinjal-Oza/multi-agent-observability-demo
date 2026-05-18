# Architecture

This document walks through the four-role pattern, the shape of the shared state, and the reasoning behind each design choice.

## The problem statement

A single LLM agent doing incident investigation hits two hard ceilings:

1. **Context window pressure.** Every tool result is appended to the agent's working context. By the time you've queried six metrics, pulled logs from two services, and looked up the recent deploy log, you've burned through enough tokens that early observations start getting truncated — exactly the ones the agent needs to make a causal claim later.

2. **Tool hallucination.** A large tool set means the agent's "next tool" decision becomes harder. Wrong tool name, wrong parameter shape, plausible-looking call against a function that doesn't exist. Single-agent systems amplify this because there's no escape valve.

Splitting work across specialized agents with bounded tool sets relieves both. Each agent owns 1–3 tools it actually understands. Each agent's context contains only what it needs. When one agent fails, it fails in a way you can isolate and debug.

## The four roles

### Supervisor

Receives the raw alert. Classifies it. Decides which downstream agents to invoke.

The supervisor is deliberately not LLM-driven. Routing is in `ROUTING_TABLE` in [`agents/supervisor.py`](../agents/supervisor.py). Code-based routing is testable, deterministic, and easy to reason about. If you want to drive routing with a model later, swap the dict for a model call — but start with rules.

### Telemetry investigator

Has tool access to the observability stack (Prometheus, Logs, Deploy log, in this demo via mocks). Given a trigger, it runs a small fixed set of queries and returns structured findings.

The telemetry agent does NOT interpret. It collects. The reason: interpretation requires the broader investigation context, which only the reasoning agent has by the time it runs. Mixing collection and interpretation here is the single biggest mistake I see in agent designs.

### Reasoning

Takes the telemetry agent's findings and produces a hypothesis about root cause. This is the one agent that calls an LLM, because the work is genuinely model-shaped — causal reasoning across heterogeneous signals.

Output is structured: `summary`, `confidence`, `rationale`. The confidence score is parsed from the model's response. It is reported, **not trusted**.

### Action

Translates the hypothesis into a recommended remediation. Never executes autonomously in this demo. Always drafts an action and marks the state as requiring human approval.

For a real deployment, the threshold logic for low-risk autonomous action would live here. This implementation keeps that gate closed deliberately because the failure mode of "autonomous action on a wrong hypothesis" is much worse than "human waits 30 seconds to approve."

## Shared state

All four agents read from and write to a single typed `InvestigationState` object (see [`agents/state.py`](../agents/state.py)).

Using a typed shared state instead of free-form message passing is what makes the system auditable. If the final recommendation looks wrong, you can trace the exact sequence of observations and inferences that produced it. Every step is recorded in `audit_trail`.

```
                  ┌─────────────────────────────┐
                  │     InvestigationState      │
                  │                             │
                  │  - incident_id              │
                  │  - trigger (AlertTrigger)   │
                  │  - routed_to                │
                  │  - telemetry_findings []    │
                  │  - causal_hypothesis        │
                  │  - recommended_actions []   │
                  │  - confidence_score         │
                  │  - audit_trail []           │
                  │  - requires_human_approval  │
                  └─────────────────────────────┘
                              ▲
                              │ reads/writes
                              │
       ┌──────────────┬───────┴───────┬──────────────┐
       │              │               │              │
  Supervisor     Telemetry        Reasoning       Action
   (route)       (collect)       (hypothesize)   (propose)
```

## LangGraph wiring

When `langgraph` is installed, `agents/graph.py` builds an explicit state graph. When it isn't, a tiny synchronous orchestrator runs the same sequence. Both produce identical final state, which makes testing cheap.

The reason for keeping both code paths: LangGraph is the production target, but the demo should be runnable without pulling in heavy dependencies. Tests run against the synchronous path by default.

## Why not just one big prompt?

This is the most common pushback. The answer is empirical:

- A single prompt for a five-step investigation has to choose tools, interpret intermediate results, decide when to stop, and produce a final action — all without losing track of earlier observations. The bookkeeping load is what kills it.
- Splitting the work means each model call has a narrower job. Narrower jobs produce more consistent outputs and fail in more predictable ways.
- The shared state object survives across agents. The prompt context for each agent doesn't have to.

## What's intentionally missing

- **Streaming / partial outputs.** This demo runs synchronously to keep the trace readable. Production deployments often need streaming.
- **Retry logic on agent failures.** Real systems should wrap each agent in a retry policy. Omitted here for clarity.
- **Persistent state.** The state lives in memory and is printed at the end. Production should persist it (DB or KV store) so investigations can be resumed.
- **Real tool calls.** The mock tools are the integration point. Swap them with real Prometheus/Loki clients and the pipeline works unchanged.
