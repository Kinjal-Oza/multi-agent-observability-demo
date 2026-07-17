# Why add a Falsifier agent

Most of the multi-agent write-ups I read while building this follow the same
shape: findings feed a hypothesis, the hypothesis feeds an action. Every step
confirms the one before it. Nothing in the pipeline is designed to disagree
with itself.

That bothered me once I started deliberately trying to break my own agent
with adversarial synthetic scenarios. A high-confidence hypothesis that's
wrong is worse than a low-confidence one, because it's the one most likely
to trigger an autonomous action. Confirmation-only pipelines have no
mechanism to catch that case — every stage is structurally incentivized to
agree with the stage before it.

The fix borrows an old idea from outside ML entirely: Popper's falsifiability
criterion. A claim that can't be tested against contradicting evidence isn't
really a testable claim. So the Falsifier agent's only job is to go looking
for findings that contradict the leading hypothesis, not findings that
support it. A "refuted" verdict forces escalation to a human regardless of
how confident the Reasoning agent was.

Concretely, this is what changed:

- The pipeline went from four stages to six (added Falsifier and
  Counterfactual).
- `agents/falsifier.py` actively searches for contradicting findings,
  producing one of `confirmed` / `contested` / `refuted`.
- A `refuted` verdict is a hard override — it escalates regardless of the
  raw confidence score. Confidence alone was never a safe enough gate on
  its own.

The measurable effect is in `docs/methodology.md` — Falsifier precision
1.00 on the synthetic corpus, which is a small, honest number on a toy
dataset, not a production claim. What it demonstrates is that the
mechanism catches what it's supposed to catch on the cases tested.

The bigger lesson for anyone building agent pipelines: if every stage in
your architecture is designed to agree with the stage before it, you don't
have a reasoning system, you have an amplifier. Build something whose job
is to disagree.
