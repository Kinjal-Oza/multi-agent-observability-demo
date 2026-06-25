# Contributing to multi-agent-observability-demo

Thanks for your interest. This repo is a reference implementation — contributions that improve clarity, add realistic scenarios, or extend the agent architecture are welcome.

## Getting started

```bash
git clone https://github.com/Kinjal-Oza/multi-agent-observability-demo.git
cd multi-agent-observability-demo
pip install -e ".[dev]"
pytest
```

Requires Python 3.10+.

## Running the examples

```bash
# Network latency incident (default scenario)
python -m examples.run_synthetic_incident

# Thermal throttling scenario
python -m examples.run_thermal_incident
```

## Project structure

```
agents/         Core agent implementations (supervisor, telemetry, reasoning, etc.)
tools/          Mock observability backends (replace with real clients for production)
examples/       Runnable end-to-end scenarios
tests/          Unit and integration tests
docs/           Architecture and design documentation
```

## Adding a new incident scenario

1. Create `examples/run_<scenario_name>.py` following the pattern in `run_synthetic_incident.py`
2. Define an `AlertTrigger` with a realistic metric and threshold
3. Add a corresponding test in `tests/test_end_to_end.py`
4. Document what the scenario tests in a docstring

## Adding a new mock tool

1. Add a module under `tools/`
2. Use typed function signatures — no unstructured `**kwargs`
3. Return a `dict` with consistent keys that the telemetry agent can parse
4. Add at least one unit test

## Running tests

```bash
# All tests
pytest

# With coverage
pytest --cov=agents --cov=tools --cov-report=term-missing

# Single module
pytest tests/test_reasoning.py -v
```

## Code style

- Type annotations on all public functions
- Docstrings on all modules and classes
- No external LLM calls in tests — use the deterministic fake backend (`agents/llm.py`)

## What this repo is not

This is a reference architecture for learning and prototyping. It is not:
- A production incident response system
- A replacement for your existing observability stack
- A claim that LLM agents can autonomously manage infrastructure without human oversight

The human-approval gate in `agents/action.py` is closed by default for a reason.

## License

MIT. See [LICENSE](LICENSE).
