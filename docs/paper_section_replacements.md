> **Superseded.** This was a drafting aid from before the paper was reconstructed as a
> full `.tex` document. The actual, final text is in `NetOpsAgent_CNSM2026_revision.tex`
> — this file is kept only for provenance of the drafting process.

# Ready-to-paste replacement text for NetOpsAgent (CNSM 2026 revision)

Only the sections below change. Sections I (parts), III, IV-A through IV-D, IV-F stay
as submitted — the architecture description was never in question.

---

## Abstract — replace the results sentences

**Delete:**
> We evaluate on 200 incident traces derived from the AIOps Challenge 2020 KPI dataset
> and structured synthetic scenarios. NetOpsAgent achieves 78.5% exact-or-partial root
> cause hypothesis match, a statistically significant 11.0 percentage-point improvement
> over a single-agent GPT-4o baseline (McNemar's χ² = 9.19, p = 0.002). We characterize
> four LLM failure modes with mitigations and analyze per-agent latency and cost.

**Replace with:**
> We evaluate on two independent, real fault-injection benchmarks: the AIOps Challenge
> 2020 KPI dataset (N=75 usable incidents) and RCAEval RE1 (N=75 independent
> microservice fault scenarios). Across six architectural configurations — including a
> raw-context fix, retrieval-augmented generation with and without relevance gating, and
> a test specifically designed to isolate the benefit of multi-agent decomposition — we
> find no statistically significant advantage of the multi-agent architecture over a
> single-agent baseline on either dataset (McNemar p > 0.05 throughout), and a
> rule-based baseline remains competitive with both. We report this result in full,
> characterize why self-reported LLM confidence fails to support safe autonomous action
> in this setting, and identify the likely mechanism (blind metric selection under
> multi-agent decomposition) behind the architecture's underperformance.

---

## Introduction — contribution #2, replace

**Delete:** "(2) an empirical evaluation on 200 incident traces demonstrating
statistically significant accuracy improvement over a single-agent baseline;"

**Replace with:** "(2) a controlled empirical evaluation across two independent real
datasets and six architectural configurations, showing that multi-agent decomposition
and retrieval augmentation do not produce a significant improvement over a single-agent
baseline for this task — including under a test designed specifically to favor the
multi-agent hypothesis;"

---

## Related Work — add a subsection after II-F (Multi-Agent Coordination Frameworks)

Insert the content of `related_work_differentiation.md` verbatim as a new subsection,
e.g. "G. Positioning Relative to Recent RCA Multi-Agent Systems." It directly answers
reviewers' Flow-of-Action / MA-RCA novelty concern.

---

## Section III-E — delete the unsupported RAG claim

**Delete this sentence entirely** (no replacement — not measured for real, and the
real RAG ablation now lives in Section V):
> The RAG retrieval step is critical for hypothesis quality on incidents with historical
> precedent. In the evaluation, traces for which the RAG index contained a similar
> postmortem showed a 14 pp higher exact-match rate than traces with no relevant RAG
> context (84% vs. 70%). This confirms that index coverage is a deployment-time
> dependency: organizations with richer postmortem corpora will see higher reasoning
> accuracy.

---

## Section IV-A — replace the latency claim

**Delete:** "Mean invocation latency in prototype evaluation is 43 seconds."

**Replace with:** "Per-agent latency and cost are reported in Section V; the figures
depend heavily on whether the Telemetry Agent's tool-calling loop is implemented against
live or mocked observability APIs, so are deferred to the evaluation section rather than
stated here."

---

## Section V — full replacement

Replace Sections V-A through V-H entirely with the following structure (numbers pulled
directly from the supplementary package; cite it as your reproducibility artifact):

**V-A. Dataset Construction.** Two independent real datasets, not one dataset plus
synthetic scenarios:
- AIOps Challenge 2020: 81 ground-truth incidents; 75 usable after requiring a valid
  pre-incident baseline window (6 excluded). All ground truth from the dataset's
  published fault-injection labels — no author-assigned labels, no synthetic traces.
- RCAEval RE1 (Zenodo, CC-BY-4.0): 75 independent fault-injection scenarios across
  three real deployed microservice systems (Online Boutique, Sock Shop, Train Ticket) —
  one run per unique service×fault-type combination, out of 6 repeated runs each, to
  avoid pseudoreplication.

**V-B. Baselines.** Single-agent GPT-4o (same tool schema/task description, no
multi-agent decomposition) and a fixed-heuristic rule-based classifier, both as in the
original submission.

**V-C. Architectural configurations evaluated.** Six, run once each, pre-registered
before execution:
1. Baseline multi-agent (mini-summary → reasoning).
2. Sort-order bug fix (rank findings by relative deviation, not raw magnitude).
3. Raw-context fix (Reasoning Agent sees raw signal data, not just the summary).
4. + RAG (real embeddings, 21-chunk generic operational-knowledge corpus, top-5).
5. + RAG with relevance gating (cosine similarity ≥ 0.45).
6. Fair context-pollution test: single-agent gets a true unranked/unfiltered raw
   telemetry dump; multi-agent's Telemetry Agent does real iterative, blind
   metric-name-based selection before inspecting values.

**V-D. Results.**

*Table II replacement — AIOps Challenge 2020 (N=75), exact match:*

| Configuration | Single-agent | Multi-agent |
|---|---|---|
| Baseline | 24.0% | 17.3% |
| Sort-fix | 20.0% | 18.7% |
| Raw-context fix | 22.7% | 22.7% |
| + RAG | 24.0% | 24.0% |
| + RAG, gated | 22.7% | 25.3% |
| Raw dump vs. iterative (fair test) | 25.3% | 4.0% |
| Rule-based | — | 76.0%* |

*rule-based scored on fault-type match only (its task is narrower by design).

*Table III replacement — RCAEval RE1 (N=75), exact match:*

| Configuration | Single-agent | Multi-agent |
|---|---|---|
| Baseline | 41.3% | 40.0% |
| Raw-context fix | 33.3% | 37.3% |
| + RAG | 29.3% | 34.7% |
| + RAG, gated | 29.3% | 30.7% |
| Rule-based | 36.0% | — |

McNemar's test (single vs. multi, exact match) returns p > 0.05 for every
configuration on both datasets except the fair context-pollution test (p=0.064,
favoring single-agent). **No configuration shows a significant multi-agent advantage.**

**V-E. Confidence calibration.** Replace original Table III (mean 0.82/0.67/0.54,
described as well-separated) with the real finding: self-reported confidence does not
discriminate correct from incorrect (mean 0.85–0.90 regardless of correctness); 96–100%
of incorrect hypotheses pass the paper's proposed 0.75 autonomy gate. A self-consistency
fix (5 resamples, majority vote) was tried and also failed to discriminate (0.98 vs.
0.93), because the model is frequently consistently wrong rather than stochastically
uncertain. State this as a finding about the limits of LLM confidence gating for this
task class, not as a solved problem.

**V-F. Latency and cost.** Report the measured 15-incident sample (single-agent
0.75s/$0.0013, multi-agent 3.53s/$0.0010) with an explicit caveat that this measures
the summary-based evaluation harness, not a full iterative tool-calling implementation
against live observability APIs — the two are not directly comparable, and the paper
should not imply otherwise.

**V-G. Threshold sensitivity.** Rule-based CPU threshold swept 50–95%: exact-or-partial
ranges 73.3–81.3%, not strongly sensitive to the specific cutoff chosen.

**V-H. Limitations (expand the existing Section VI-B with):** point estimates above are
from single runs at temperature 0.2–0.7; re-running an *unchanged* prompt moved its own
score by 8 points from sampling noise alone (RCAEval single-agent, 41.3%→33.3%) — larger
than most of the effects reported above. A repeated-run protocol (3–5 runs/condition)
was not performed; treat the point estimates as indicative, not precise.

**Remove entirely** (no real data supports them): original Tables IV, V, VI, and the
"Illustrative Trace Walkthrough" (Section IV-H / old V-H).

---

## Conclusion — replace

**Delete:**
> On 200 evaluation traces from the AIOps Challenge 2020 KPI dataset and structured
> synthetic scenarios, NetOpsAgent achieves 78.5% exact-or-partial root cause hypothesis
> match — a statistically significant 11.0 pp improvement over a single-agent GPT-4o
> baseline (McNemar's p = 0.002).

**Replace with:**
> On two independent real fault-injection benchmarks (AIOps Challenge 2020 and RCAEval
> RE1, N=75 each), across six architectural configurations, NetOpsAgent's multi-agent
> decomposition did not produce a statistically significant improvement over a
> single-agent baseline, including under a configuration specifically designed to test
> the architecture's own context-hygiene hypothesis. We report this as an honest,
> triangulated empirical finding rather than a negative result to explain away: it
> suggests the benefit of multi-agent LLM decomposition for infrastructure incident
> triage is more setup-dependent than prior work in this space (e.g. Flow-of-Action,
> MA-RCA) has reported, and we encourage the community to test this on further real
> benchmarks.
