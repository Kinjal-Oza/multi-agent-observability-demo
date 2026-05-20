"""Graph wiring — six-stage pipeline.

Supervisor → Telemetry → Reasoning → Falsifier → Counterfactual → Action

The Falsifier and Counterfactual Simulator
are now first-class stages between Reasoning and Action, making falsification
and outcome prediction mandatory before any remediation is recommended.

When `langgraph` is installed, the graph is built with its API for parity
with production deployments. When it isn't, the same sequence runs
synchronously through a tiny pure-Python orchestrator — so the demo is
runnable in environments where pulling in heavy deps is undesirable.
"""
from __future__ import annotations

from typing import Callable

from agents.action import action_step
from agents.counterfactual import counterfactual_step
from agents.falsifier import falsifier_step
from agents.reasoning import reasoning_step
from agents.state import InvestigationState
from agents.supervisor import supervisor_step
from agents.telemetry import telemetry_step


_PIPELINE: list[tuple[str, Callable[[InvestigationState], InvestigationState]]] = [
    ("supervisor",     supervisor_step),
    ("telemetry",      telemetry_step),
    ("reasoning",      reasoning_step),
    ("falsifier",      falsifier_step),
    ("counterfactual", counterfactual_step),
    ("action",         action_step),
]


def build_investigation_graph():
    """Build a LangGraph state graph if available; otherwise return a callable.

    The returned object always exposes a ``.invoke(state)`` method that
    runs the full investigation and returns the final state.
    """
    try:
        from langgraph.graph import END, StateGraph  # type: ignore
    except ImportError:
        return _SimplePipeline()

    builder = StateGraph(InvestigationState)
    for name, step in _PIPELINE:
        builder.add_node(name, step)

    builder.set_entry_point("supervisor")
    for (a, _), (b, _) in zip(_PIPELINE, _PIPELINE[1:]):
        builder.add_edge(a, b)
    builder.add_edge(_PIPELINE[-1][0], END)
    return builder.compile()


class _SimplePipeline:
    """Fallback orchestrator used when langgraph isn't installed."""

    def invoke(self, state: InvestigationState) -> InvestigationState:
        for _, step in _PIPELINE:
            state = step(state)
        return state


def run_investigation(state: InvestigationState) -> InvestigationState:
    """Convenience helper: build the graph and run it once."""
    graph = build_investigation_graph()
    return graph.invoke(state)
