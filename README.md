# NetOpsAgent — CNSM 2026 Revision Evidence Package

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23170063.svg)](https://doi.org/10.5281/zenodo.23170063)

> **How to cite.** If you use this code, data or results, please cite:
> K. Vaishnav, "NetOpsAgent: A Hierarchical Multi-Agent LLM Framework for Autonomous Cloud Infrastructure Incident Management," in *Proc. 22nd International Conference on Network and Service Management (CNSM 2026)*, Alcalá de Henares, Spain, 2026.
> Artifacts: https://doi.org/10.5281/zenodo.23170063. GitHub's "Cite this repository" button gives BibTeX (from `CITATION.cff`).

This package replaces the original submission's evaluation section (200 traces,
78.5% exact-or-partial), which could not be reproduced from code or data, with a fully
reproducible evaluation on two independent public datasets.
Everything here was run live against the OpenAI API, once per configuration, and
reported as-is.

## Contents

- `paper/NetOpsAgent_CNSM2026_revision.tex` and `.pdf` — the actual, final submitted paper.
- `scripts/` — every extraction and evaluation script, in the order they were run.
- `data/` — extracted incident/scenario JSON (inputs to the eval scripts).
- `results/` — raw per-incident model outputs (inputs to any stats you want to recompute).

## Datasets

1. **AIOps Challenge 2020** — public KPI/trace dataset. 81 ground-truth incidents;
   75 usable (valid baseline window). `extract_incidents_v3.py` →
   `extract_trace_features_v3.py` → `data/incidents_with_trace_v3.json`.
2. **RCAEval RE1** (Zenodo, CC-BY-4.0) — real fault-injection on Online Boutique / Sock
   Shop / Train Ticket. 75 independent scenarios (1 run per unique service×fault-type
   combo, out of 6 repeated runs each, to avoid pseudoreplication).
   `extract_rcaeval.py` → `data/rcaeval_incidents.json`.

## Evaluation history (AIOps, N=75, exact-or-partial match)

| version | what changed | single-agent | multi-agent |
|---|---|---|---|
| v3 (`run_eval_v3.py`) | first full N=75 run | 26.7% | 22.7% |
| v4 (`run_eval_v4.py`) | fixed finding-summary sort bug (ranked by raw magnitude, not relative deviation) | 28.0% | 22.7% |
| v5 (`run_eval_v5.py`) | architecture fix: Reasoning agent gets raw signal data, not just the mini-agent's summary | 30.7% | 22.7% |
| v6 (`run_eval_v6_rag.py`) | adds RAG (real embeddings, 21-chunk generic SOP corpus) to both agents | 30.7% | 26.7% |

Every fix here was disclosed, pre-registered before its run, and reported regardless of
which direction it moved the number. None closed the gap between single- and
multi-agent, and none reached anywhere near the original 78.5% claim.

## Evaluation history (RCAEval RE1, N=75, exact match — the metric that doesn't saturate)

| version | what changed | single-agent | multi-agent |
|---|---|---|---|
| v1 (`rcaeval_eval.py`) | first run | 41.3% | 40.0% |
| v2 (`rcaeval_eval_v2.py`) | raw-context architecture fix (multi-agent path only) | 33.3% | 37.3% |
| v3 (`rcaeval_eval_v3_rag.py`) | adds RAG (same corpus as AIOps v6) | 29.3% | 34.7% |

All percentages above use the same normalized (case/whitespace-insensitive) service-name
scorer; see the scoring function in `scripts/rcaeval_eval_v2.py` for the exact logic.

**Important caveat — single-run noise.** The single-agent prompt/logic is *identical*
between v1 and v2 (only the multi-agent reasoning step changed), yet single-agent's own
score moved from 41.3% to 33.3% just from re-running at temperature=0.2. That 8-point
swing is larger than most of the "effects" attributed to the architecture fix or RAG
elsewhere in this package. **None of the single-run comparisons here should be read as
causally significant on their own** — they're consistent with the McNemar tests (which
mostly return p > 0.3), but a proper claim would need repeated runs per condition
(e.g. 3–5 runs, report mean ± spread) to separate real effects from sampling noise.
That repeat-run pass has not been done and should be flagged as a limitation, not
silently smoothed over.

## Bottom line

No configuration — architecture fix, RAG, or their combination — produced a
statistically significant multi-agent advantage over single-agent on either real
dataset (all McNemar p-values > 0.05). A simple rule-based baseline is competitive with
or beats both LLM architectures on AIOps. The one real positive result in this whole
package is the Falsifier extension's AIOps gain, and even that is driven by the
verification *capability*, not multi-agent decomposition (control test above, p=1.0).
This is consistent with concurrent 2026 literature cited in the paper (Section II-G):
homogeneous multi-agent workflows are matched by a well-tuned single agent, and
decomposition's advantage shrinks for interdependent tasks like whole-incident RCA.
This is the real, current state of the evidence.

## Falsifier extension (Section V-H of the paper)

Beyond the six base configurations above (none of which gave multi-agent a capability a
single agent couldn't also have), we tested a genuinely new capability: a Falsifier
agent that adversarially checks a hypothesis against the full telemetry pool.
Pre-registered, run once per dataset, reported regardless of direction.

| script | condition | single-agent | +Falsifier | McNemar p |
|---|---|---|---|---|
| `falsifier_test_aiops.py` → `results_v9_falsifier.json` | AIOps, multi-agent+Falsifier | 21.3% | 33.3% | 0.023 |
| `falsifier_test_aiops_singleagent_control.py` → `results_v10_falsifier_singleagent_control.json` | AIOps, single-agent+Falsifier (control) | 21.3% | 32.0% | 0.077 |
| `falsifier_test_rcaeval.py` → `rcaeval_results_v5_falsifier.json` | RCAEval, multi-agent+Falsifier | 42.7% | 24.0% | <0.001 |
| `falsifier_test_rcaeval_v2_topology.py` → `rcaeval_results_v6_falsifier_topo.json` | RCAEval, topology-aware | 42.7% | 40.0% | 0.50 |

Two implementation bugs were found and fixed during a pre-run smoke test, before any
accuracy number was computed (disclosed in the script docstrings, not silently
applied): a negation-scoring bug (free-text alternatives could say "Low CPU Usage" and
get misread as a CPU-fault match — fixed via closed vocabulary) and an
over-refutation bug (the adversarial prompt initially refuted nearly every hypothesis,
including correct ones — fixed by defaulting to "confirmed" absent concrete
contradicting evidence).

**Result:** the Falsifier significantly helps on single-entity incidents (AIOps) and
significantly hurts on multi-service ones (RCAEval), because without
service-dependency-graph awareness it mistakes a downstream propagated symptom for an
independent root cause. `service_topology.py` provides the real, documented service
graph for Online Boutique and Sock Shop (verified against project docs) and a
naming-convention proxy for Train Ticket's 64 services (partial-scope, disclosed). The
topology-aware retest eliminates the RCAEval regression (p=0.50, was p<0.001) but adds
no gain — zero overrides in either direction.

**Control test — isolating capability from architecture.** The AIOps result above
pairs the Falsifier with the *multi-agent* Reasoning agent's hypothesis. To check
whether the gain needs multi-agent decomposition at all, we ran the identical Falsifier
directly on the (reused, unchanged) single-agent hypothesis. Result: statistically
indistinguishable from the multi-agent version (p=1.0 head-to-head; 21 incidents right
under both, 47 wrong under both, 4 vs. 3 splitting the rest). **The verification
capability drives the AIOps gain, not the multi-agent decomposition it was attached
to** — this is now the paper's central empirical claim (Section V-H, Section II-G).

## RAG corpus

`scripts/sop_corpus.py` — 21 chunks of generic SRE operational knowledge, authored
before any evaluation ran, with zero incident-specific content (no service names,
timestamps, or dataset-derived text). Independence from the evaluation traces is true
by construction and directly inspectable. `scripts/rag_retrieval.py` embeds this corpus
with `text-embedding-3-small` and does real cosine-similarity top-5 retrieval — not a
keyword stand-in. Also includes `retrieve_gated()`, a relevance-thresholded variant
(see below).

## Four more real ablations (reviewer-requested + hypothesis-testing)

1. **RAG relevance gating** (`run_eval_v7_rag_gated.py`, `rcaeval_eval_v4_rag_gated.py`):
   only inject retrieved chunks above cosine similarity 0.45 (fixed from a pre-run
   diagnostic, not tuned to outcome). Reduced the CPU/disk over-retrieval bias (67/75 →
   59/75 biased guesses) and modestly improved AIOps (30.7%→33.3% single, 26.7%→33.3%
   multi). Roughly a wash on RCAEval.
2. **GPT-4o vs. GPT-4o-mini, single-agent role** (`model_choice_ablation.py`): comparable
   on AIOps (22.7% both), mini worse on RCAEval (26.7% vs 33.3%), ~17x cheaper per token.
3. **Self-consistency confidence** (`confidence_selfconsistency.py`, N=30 sample, 5
   resamples/incident at temp=0.7): still doesn't discriminate correct from incorrect
   (mean 0.98 vs 0.93). The model is often *consistently* wrong, not stochastically
   uncertain — resampling can't fix a systematic bias. See rebuttal §4b for the full
   confidence-calibration finding, which also replaces the original Table III.
4. **Fair context-pollution test** (`context_pollution_fair_test.py`) — the one
   experiment in this whole package specifically designed to be most favorable to the
   paper's own architectural hypothesis. Single-agent got a true raw, unranked,
   unfiltered telemetry dump (real "context pollution"); multi-agent's Telemetry Agent
   did real iterative metric selection (real "context hygiene via decomposition").
   Result: single-agent 25.3% exact vs. multi-agent 4.0% exact, nearly significant in
   single-agent's favor (McNemar p=0.064). Even the most charitable test design does not
   support the paper's core claim.

Real per-agent latency/cost measured on a 15-incident sample (`latency_cost_sample.json`):
single-agent 0.75s/$0.0013, multi-agent 3.53s/$0.0010 — far below the original Table IV's
claimed 43.2s/$0.40. This measures the summary-based harness used throughout this
package, not a full iterative ReAct/tool-calling implementation, so it doesn't drop
straight into Table IV; say so explicitly if it's used at all.

## What's still open

- Repeated-run protocol (3–5 runs/condition) to separate real effects from single-run
  sampling noise — disclosed as a limitation in the paper (Section VI-B), not yet done.
- Sharpening the topology-aware Falsifier's override decision to recover a genuine gain
  (currently zero overrides in either direction) — listed as future work.
- Train Ticket's full call graph is only naming-convention-verified, not fully
  hand-verified like Online Boutique/Sock Shop — disclosed scope limit.

Resolved since the last version of this package: references (37/37 now cited), Figure
1 (redrawn as a vector diagram), GPT-4o/GPT-4o-mini rationale (now stated explicitly in
Section IV-A), and this package's own staleness (it previously did not contain the
Falsifier/topology/control scripts and results above).

## Follow-up results (September 2026, preliminary)

**Status:** preliminary. One run per configuration, not peer reviewed, being written up
as a follow-up paper. Same prompts, scoring and agent roles as the paper; only the
models change (called via OpenRouter). Code and raw per-incident outputs:
[`followup/`](followup/).

### 1. The paper's GPT-4o results reproduce
A fresh re-run of every configuration matched each headline result within 3 points,
with 92–100% of per-incident verdicts identical.

### 2. On newer models, the multi-agent result changes
AIOps 2020, exact match, N = 75, McNemar p.

| Model pair (reasoner / telemetry) | Team | Single agent | p |
|---|---|---|---|
| GPT-4o / GPT-4o-mini (paper) | 22.7% | 22.7% | 1.00 |
| GPT-4o / GPT-4o-mini (re-run) | 25.3% | 21.3% | 0.38 |
| Claude Sonnet 5.5 / Haiku 4.5 | 44.0% | 33.3% | 0.008 |
| Claude Opus 5.5 / Haiku 4.5 | 38.7% | 29.3% | 0.14 |
| GPT-5.6 Sol / GPT-5.6 Luna | 38.7% | 26.7% | 0.004 |
| Gemini 3.8 Flash / 3.5 Flash-Lite | 24.0% | 25.3% | 1.00 |
| Llama 3.3 70B / 3.1 8B | 8.0% | 18.7% | 0.077 |
| Llama 4 Maverick (both roles) | 6.7% | 20.0% | 0.021 |

### 3. The handoff test
Reasoner fixed as GPT-4o; only the telemetry/summarizer model changes.
Fair context-pollution test, team vs single agent:

| Summarizer | Team | Single agent |
|---|---|---|
| GPT-4o-mini (paper) | 4.0% | 25.3% |
| Claude Haiku 4.5 | 14.7% | 25.3% |
| GPT-5.6 Luna | 24.0% | 24.0% |

A stronger summarizer removes the team's loss, but no summarizer alone made the
GPT-4o team win. That happened only when both models were strong.

### 4. What held across models
- Without service topology, the Falsifier hurt on multi-service incidents (RCAEval)
  for every model whose Falsifier actually overrode (GPT-4o, Sonnet 5.5, Opus 5.5,
  Llama 4).
- Self-reported confidence did not separate correct from incorrect answers on 6 of 7
  models (Opus 5.5 partially).

### Notes on the paper's numbers (checked against the raw outputs)
None of these changes the paper's conclusions.
- **Run-to-run swing (Section VI-B):** in `results/rcaeval_results_v2.json`, 11
  single-agent calls failed with API rate-limit errors (HTTP 429) and were scored as
  incorrect. On the 64 incidents that ran cleanly in both runs, the single agent scored
  25 correct both times. The true run-to-run swing is at most ~3 points. On the 60
  incidents where both calls succeeded, Table I's RCAEval raw-context row is 24 vs 23
  correct.
- **Table II, RCAEval:** the percentages compare against the single agent (42.7%);
  the "0 corrected, 12 broken" counts compare the team before vs after the Falsifier
  (40.0% → 24.0%).
- **Topology-aware Falsifier:** the team stays at 40.0% before and after; there was one
  override (a wrong answer replaced by another wrong one).
- **Control test split:** the raw outputs give 20 / 46 / 5 / 4 (the paper reports
  21 / 47 / 4 / 3); p = 1.0 either way.
