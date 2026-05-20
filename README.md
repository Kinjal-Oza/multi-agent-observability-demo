# multi-agent-observability-demo

A runnable reference implementation of verifiable multi-agent incident reasoning with adversarial hypothesis falsification and counterfactual outcome simulation.

This repo accompanies the article "Why One AI Agent Is Never Enough: A Multi-Agent Architecture for Infrastructure Observability." It exists so the mechanisms described in the article can be inspected, measured, and modified — not just read about.

> **Scope:** This is a pattern reference, not a production system. All telemetry sources are mocked. The model layer runs against any chat-completion endpoint or a deterministic fake.

## Visual walkthrough

Open [`docs/walkthrough.html`](docs/walkthrough.html) for an animated walkthrough of the six-stage architecture and a playable end-to-end incident scenario.

## What's different here

Most observability AI tools run a confirmation cascade: findings → hypothesis → action. Every agent in the pipeline is working to confirm the first guess, not to challenge it.

This demo adds four mechanisms that are rarely combined in one pipeline:

| Mechanism | What it does |
|-----------|-------------|
| **Provenance-bound hypotheses** | Every causal claim must cite a Finding ID. Ungrounded statements cannot be constructed. |
| **Adversarial Falsifier** | A dedicated agent that tries to disprove the leading hypothesis before action is taken. Confirmation cascades become falsification chains. |
| **Counterfactual outcome simulation** | Predicts the post-remediation system state (with confidence bounds) *before* the human approves. The approver sees not just "what to do" but "what will happen if I approve." |
| **Calibrated confidence** | Final confidence = weighted ensemble of raw LLM score, historical prior from incident corpus, and falsification penalty. Brier score and ECE are reported. |

## Six-stage pipeline

```
Alert → Supervisor → Telemetry → Reasoning → Falsifier → Counterfactual → Action
                                    ↑              ↑              ↑
                               provenance-    adversarial    pre-execution
                               bound claims   falsification  prediction
```

## Quick start

```bash
git clone https://github.com/Kinjal-Oza/multi-agent-observability-demo
cd multi-agent-observability-demo

pip install -e ".[dev]"

# Run the end-to-end example showing all six stages
python -m examples.run_synthetic_incident

# Run the test suite (64 tests)
pytest -v

# Run the benchmark against 100 synthetic incidents
python -m bench.run_benchmark
```

## Benchmark results (DeterministicFake backend)

```
Scenarios:           100
Hypothesis accuracy: 0.78
Brier score:         0.199
ECE:                 0.337
Falsifier precision: 1.00
Falsifier recall:    0.89
Action precision:    0.64
```

Metrics computed on a synthetic corpus. With a real LLM backend, accuracy
and calibration improve substantially. See `docs/methodology.md`.

## Running with a real LLM

```bash
export OPENAI_API_KEY=...
export MAO_MODEL_BACKEND=openai
python -m examples.run_synthetic_incident
```

Backends: `fake` (default), `openai`, `anthropic`.

## Layout

```
multi-agent-observability-demo/
├── agents/                  # Six-stage implementation
│   ├── state.py             # InvestigationState + all v2 types
│   ├── supervisor.py        # Routes + assigns investigation budget
│   ├── telemetry.py         # Queries mock observability stack
│   ├── reasoning.py         # Provenance-bound hypothesis formation
│   ├── falsifier.py         # Adversarial falsification
│   ├── counterfactual.py    # Outcome simulation
│   ├── action.py            # Falsifier-aware remediation
│   ├── confidence.py        # Calibrated confidence
│   ├── graph.py             # LangGraph wiring (six-stage)
│   └── llm.py               # Pluggable LLM backend
├── corpus/                  # Synthetic incident corpus (100 scenarios)
│   ├── incidents.jsonl      # Ground-truth labeled incidents
│   ├── causal_prior.py      # P(cause | classification) frequency table
│   └── generate.py          # Corpus generator (seed-based, reproducible)
├── bench/                   # Benchmark harness
│   ├── scenarios.py         # Corpus loader
│   ├── metrics.py           # Brier, ECE, falsifier precision, action precision
│   └── run_benchmark.py     # CLI entry point
├── tools/                   # Mock telemetry sources
├── examples/
│   └── run_synthetic_incident.py
├── tests/                   # pytest suite (64 tests)
├── docs/
│   ├── walkthrough.html     # Interactive walkthrough
│   ├── architecture.md
│   ├── design.md
│   ├── implementation-map.md  # Mechanisms mapped to code
│   ├── methodology.md       # Benchmark methodology
│   └── failure-modes.md
├── docker-compose.yml
├── pyproject.toml
└── LICENSE  (MIT)
```

## Author

Built by Kinjal Vaishnav as a reference implementation accompanying the article. Site Reliability Engineer at Oracle Cloud Infrastructure.

- LinkedIn: [linkedin.com/in/kinjalozavaishnav](https://www.linkedin.com/in/kinjalozavaishnav)
- GitHub: [github.com/Kinjal-Oza](https://github.com/Kinjal-Oza)

## License

MIT — see [`LICENSE`](LICENSE).
