# Benchmark Methodology

This document describes how the benchmark numbers in the README and the article
were produced, what they measure, and their known limitations.

---

## Corpus

**File:** `corpus/incidents.jsonl`
**Size:** 100 incidents
**Generation:** `python -m corpus.generate` (seed=42, fully reproducible)

Each incident contains:
- Alert trigger (service, metric, value, threshold, classification, severity)
- Pre-built findings (3–5 per incident, cause-specific)
- Ground truth: `true_cause_pattern`, `ground_truth_action`, `expected_falsifier_verdict`

**Cause distribution:**
The corpus covers 8 cause patterns distributed across 4 classification types.
Cause patterns: connection pool exhaustion, deploy regression, thermal throttling,
dns resolution failure, certificate expiry, disk pressure, memory pressure, dependency cascade.

---

## Benchmark Procedure

**Command:** `python -m bench.run_benchmark`

The benchmark:
1. Loads all 100 corpus scenarios.
2. Injects pre-built findings directly into the state (bypasses telemetry mock, which only covers 2 specific service/metric pairs).
3. Runs the pipeline: `supervisor → reasoning → falsifier → action → counterfactual`.
4. Compares outputs against ground truth labels.

**Backend:** DeterministicFake (default). No API keys required. Runtime < 1 second.

**Why inject findings rather than run telemetry?**
The telemetry mock (`tools/prometheus_mock.py`) contains synthetic scenarios keyed by
specific service/metric pairs. Most corpus scenarios use randomized services, so running
telemetry would return benign "no data" for most incidents. The benchmark is designed to
measure reasoning, falsification, and action quality — not mock coverage. Injecting
corpus findings separates these concerns.

---

## Metrics Definitions

### Hypothesis accuracy

`correct / n` where `correct` = 1 if any word from `true_cause_pattern` appears in the hypothesis summary (case-insensitive).

Limitation: word-overlap metric is approximate. "connection" matches "connection pool exhaustion" but also "network connection." A real production benchmark would use semantic similarity.

### Brier score

`mean((confidence - outcome)^2)` where `outcome ∈ {0, 1}` based on hypothesis accuracy.

Perfect calibration → 0.0. Random guessing on balanced binary → 0.25. Lower is better.

### Expected Calibration Error (ECE)

Partitions predictions into 10 confidence bins. For each bin: `|mean_confidence - mean_accuracy|`. ECE = weighted average across bins (weights = bin fraction).

Lower is better. Perfect calibration → 0.0.

**Why ECE is high (0.337) with DeterministicFake:**
The DeterministicFake returns fixed confidence values (0.72, 0.65, etc.) that don't correlate tightly with accuracy across diverse scenarios. With a real LLM that adapts its confidence to the specific scenario, ECE would be lower. This is the expected behavior and is intentionally disclosed in the article.

### Falsifier precision

`true_positives / predicted_positives` for the "confirmed" verdict.

When the falsifier says "confirmed," how often is the hypothesis actually correct?

### Falsifier recall

`true_positives / actual_positives` for the "confirmed" verdict.

Of all truly-correct hypotheses, how many did the falsifier correctly confirm?

### Action precision

`correct_recommendations / n` where `correct` = 1 if the recommended action description contains keywords matching the ground truth action type (e.g., "roll back" matches `rollback_deploy`).

---

## Known Limitations

1. **DeterministicFake has a finite vocabulary.** It covers 8 cause patterns with hardcoded responses. A real LLM would generalize better across novel patterns.

2. **Word-overlap hypothesis accuracy is approximate.** It can both over-count (partial keyword matches) and under-count (synonyms).

3. **Corpus is synthetic.** Real incident data would include richer signal, noise, and long-tail failure modes not covered here. Production benchmarking would require a historical incident dataset with ground-truth post-mortems.

4. **Single-run metrics, not confidence intervals.** With N=100 and no repetition, results have measurement variance. A production benchmark would run N=1000+ or use cross-validation.

5. **Action precision uses keyword matching.** This may miss semantically correct but differently-worded recommendations.

These limitations are acknowledged upfront in the article. The purpose of the benchmark is to demonstrate that these metrics *can* be measured — not to claim production-grade calibration from a toy dataset.
