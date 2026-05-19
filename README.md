# multi-agent-observability-demo

A runnable reference implementation of a multi-agent architecture for infrastructure incident investigation.

This repo accompanies the article "Why One AI Agent Is Never Enough: A Multi-Agent Architecture for Infrastructure Observability." It exists so the patterns described in the article can be inspected, run, and modified — not just read about.

> **Scope:** This is a pattern reference, not a production system. The architecture, code, and failure-mode discussion are intended for engineers evaluating multi-agent designs for observability work. The telemetry sources are mocked; the model layer can run against any chat-completion endpoint or a deterministic fake.

## Why this exists

Single-agent designs for incident investigation hit a reliability ceiling. The two constraints that show up first:

1. **Context window pressure.** Every tool call result accumulates in the agent's context. For complex investigations spanning multiple services and 10–20 tool calls, the context fills up and early observations are dropped.
2. **Tool hallucination.** The more tools a single agent has, the more frequently it generates plausible-looking but invalid tool calls — typos in metric names, parameters in the wrong order.

Splitting work across specialized agents with bounded tool sets relieves both pressures. This repo implements the four-role pattern: **supervisor**, **telemetry investigator**, **reasoning**, and **action**.

## Architecture

```
┌──────────────┐
│  Alert In    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Supervisor  │  Classifies + routes
└──────┬───────┘
       │
       ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│  Telemetry   │ ───▶ │  Reasoning   │ ───▶ │   Action     │
│  (queries)   │      │  (hypothesis)│      │  (proposes)  │
└──────────────┘      └──────────────┘      └──────────────┘
       │                     │                     │
       └─── shared state ────┴─────────────────────┘
              (InvestigationState)
```

All agents read from and write to a single typed `InvestigationState`. No agent starts from scratch — each picks up where the last one left off. The state is the audit trail.

Detailed architecture write-up: [`docs/architecture.md`](docs/architecture.md)

Known failure modes the system runs into: [`docs/failure-modes.md`](docs/failure-modes.md)

## Quick start

```bash
# clone and enter
git clone https://github.com/Kinjal-Oza/multi-agent-observability-demo
cd multi-agent-observability-demo

# install
pip install -e .

# run the end-to-end example against the deterministic fake LLM
python -m examples.run_synthetic_incident

# run the test suite
pytest -v
```

## Running with a real LLM

By default the agents use a deterministic fake model so the demo is reproducible and CI-friendly. To run against a real chat-completion endpoint:

```bash
export OPENAI_API_KEY=...
export MAO_MODEL_BACKEND=openai
python -m examples.run_synthetic_incident
```

Other backends (`anthropic`, `local_ollama`) are stubbed in `agents/llm.py`; swap in your client of choice.

## Layout

```
multi-agent-observability-demo/
├── agents/                  # Four-agent implementation
│   ├── state.py             # InvestigationState (typed)
│   ├── supervisor.py        # Routes alerts to specialists
│   ├── telemetry.py         # Queries mock observability stack
│   ├── reasoning.py         # Forms hypothesis from findings
│   ├── action.py            # Drafts remediation; requires approval
│   ├── graph.py             # LangGraph state-graph wiring
│   └── llm.py               # Pluggable LLM backend + deterministic fake
├── tools/                   # Mock telemetry sources
│   ├── prometheus_mock.py   # Metric queries against synthetic data
│   ├── logs_mock.py         # Log search over a scenario corpus
│   └── deploy_log_mock.py   # "Recent deploys" feed
├── examples/
│   └── run_synthetic_incident.py
├── tests/                   # pytest suite
├── docs/
│   ├── architecture.md
│   └── failure-modes.md
├── docker-compose.yml       # Optional observability stack
├── pyproject.toml
└── LICENSE                  # MIT
```

## Design choices worth flagging

- **Typed shared state, not free-form messages.** `InvestigationState` is a `TypedDict`. Every read/write is structured. This is what makes the audit trail useful when something goes wrong.
- **Tools are schema-validated.** Mock tools use Pydantic models for input. Hallucinated tool calls fail loudly instead of silently producing garbage.
- **Human gate on action.** The `Action` agent never executes. It drafts a remediation with the supporting state, and `examples.run_synthetic_incident` shows what the human approver would see. This is non-negotiable for any real deployment.
- **Confidence is reported, not trusted.** Reasoning outputs a confidence score, but the threshold logic for autonomous action is parameterised. Don't blindly trust a model's self-reported confidence.

## How to read this repo

If you're trying to understand the pattern from the code: start at `agents/state.py`, read the docstring, then `agents/graph.py` to see how the state graph is wired. The agent files themselves are short and intentionally readable.

If you want to extend it to your own observability stack, the swap-points are `tools/*_mock.py` — replace the mock with a real client and the agents work unchanged.

## Author

Built by Kinjal Vaishnav as a reference implementation accompanying the article. Site Reliability Engineer focused on AI infrastructure and observability.

- LinkedIn: [linkedin.com/in/kinjalozavaishnav](https://www.linkedin.com/in/kinjalozavaishnav)

## License

MIT — see [`LICENSE`](LICENSE).
