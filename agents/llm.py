"""Pluggable LLM backend.

The demo is reproducible and CI-friendly because the default backend is a
deterministic fake that returns canned responses keyed by prompt content.

To run against a real model:

    export MAO_MODEL_BACKEND=openai
    export OPENAI_API_KEY=...
"""
from __future__ import annotations

import os
import re
from typing import Protocol


class ChatBackend(Protocol):
    def complete(self, prompt: str) -> str: ...


class DeterministicFake:
    """Returns canned responses based on substring matches.

    This is intentionally dumb. Its purpose is to make the demo runnable
    without API keys and to keep CI deterministic. Tests assert against
    this backend's output. Real reasoning quality is evaluated separately
    with a real model.
    """

    DEFAULT_RESPONSES = [
        (r"connection pool", "HYPOTHESIS: connection pool exhaustion in recently deployed service.\nCONFIDENCE: 0.72\nRATIONALE: telemetry shows elevated pool utilization correlated with recent deploy."),
        (r"deploy.*recent", "HYPOTHESIS: regression introduced by recent deployment.\nCONFIDENCE: 0.65\nRATIONALE: anomaly window aligns with deploy timestamp."),
        (r"thermal", "HYPOTHESIS: thermal throttling on subset of hosts.\nCONFIDENCE: 0.55\nRATIONALE: heat-related signals correlated with throughput drop."),
    ]
    FALLBACK = "HYPOTHESIS: unable to confidently classify with available evidence.\nCONFIDENCE: 0.30\nRATIONALE: insufficient telemetry overlap."

    def complete(self, prompt: str) -> str:
        prompt_lower = prompt.lower()
        for pattern, response in self.DEFAULT_RESPONSES:
            if re.search(pattern, prompt_lower):
                return response
        return self.FALLBACK


class OpenAIBackend:
    """Thin wrapper. Requires `openai` extra installed and OPENAI_API_KEY set."""

    def __init__(self, model: str = "gpt-4o-mini"):
        from openai import OpenAI  # noqa: F401 — runtime import
        self._client = OpenAI()
        self._model = model

    def complete(self, prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        return resp.choices[0].message.content or ""


class AnthropicBackend:
    """Stubbed Anthropic backend. Requires `anthropic` extra."""

    def __init__(self, model: str = "claude-3-5-haiku-latest"):
        import anthropic  # noqa: F401
        self._client = anthropic.Anthropic()
        self._model = model

    def complete(self, prompt: str) -> str:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text


def get_backend() -> ChatBackend:
    """Return the configured backend. Defaults to deterministic fake."""
    backend = os.environ.get("MAO_MODEL_BACKEND", "fake").lower()
    if backend == "openai":
        return OpenAIBackend()
    if backend == "anthropic":
        return AnthropicBackend()
    return DeterministicFake()


def parse_hypothesis(text: str) -> tuple[str, float, str]:
    """Parse the structured response format used by the reasoning agent.

    Returns (summary, confidence, rationale). Falls back to (text, 0.0, '')
    if the response doesn't follow the expected format.
    """
    summary = ""
    confidence = 0.0
    rationale = ""
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("HYPOTHESIS:"):
            summary = line.split(":", 1)[1].strip()
        elif line.upper().startswith("CONFIDENCE:"):
            try:
                confidence = float(line.split(":", 1)[1].strip())
            except ValueError:
                confidence = 0.0
        elif line.upper().startswith("RATIONALE:"):
            rationale = line.split(":", 1)[1].strip()
    if not summary:
        summary = text.strip().split("\n", 1)[0]
    return summary, max(0.0, min(1.0, confidence)), rationale
