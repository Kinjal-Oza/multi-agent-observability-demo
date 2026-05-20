"""Benchmark metrics for the multi-agent pipeline.

Implements metrics from scratch (no sklearn dependency):

- brier_score: mean squared error of calibrated confidence vs binary outcome
- expected_calibration_error: measures reliability curve alignment
- falsifier_precision: when falsifier says "confirmed", how often was it right?
- falsifier_recall: how many truly-confirmed cases did the falsifier correctly identify?
- action_precision: fraction of recommended actions that matched ground truth
- hypothesis_accuracy: fraction of hypotheses whose cause matched ground truth

All functions accept lists of plain floats/strings.
"""
from __future__ import annotations



def brier_score(confidences: list[float], outcomes: list[int]) -> float:
    """Mean squared error between predicted confidence and binary outcome.

    Perfect calibration → 0.0. Random guessing on balanced data → 0.25.
    Lower is better.
    """
    if not confidences:
        return 0.0
    n = len(confidences)
    return sum((p - y) ** 2 for p, y in zip(confidences, outcomes)) / n


def expected_calibration_error(
    confidences: list[float],
    outcomes: list[int],
    n_bins: int = 10,
) -> float:
    """Expected calibration error (ECE).

    Partitions predictions into confidence bins and measures the weighted
    average gap between mean confidence and mean accuracy per bin.
    Lower is better. Perfect calibration → 0.0.
    """
    if not confidences:
        return 0.0

    bins: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for p, y in zip(confidences, outcomes):
        idx = min(int(p * n_bins), n_bins - 1)
        bins[idx].append((p, y))

    ece = 0.0
    n = len(confidences)
    for b in bins:
        if not b:
            continue
        avg_conf = sum(p for p, _ in b) / len(b)
        avg_acc = sum(y for _, y in b) / len(b)
        ece += (len(b) / n) * abs(avg_conf - avg_acc)
    return ece


def falsifier_precision(
    predicted_verdicts: list[str],
    true_verdicts: list[str],
    positive_label: str = "confirmed",
) -> float:
    """Precision: when the falsifier says 'confirmed', how often is it right?"""
    tp = sum(1 for p, t in zip(predicted_verdicts, true_verdicts)
             if p == positive_label and t == positive_label)
    predicted_pos = sum(1 for p in predicted_verdicts if p == positive_label)
    return tp / predicted_pos if predicted_pos > 0 else 0.0


def falsifier_recall(
    predicted_verdicts: list[str],
    true_verdicts: list[str],
    positive_label: str = "confirmed",
) -> float:
    """Recall: of all truly-confirmed cases, how many did the falsifier identify?"""
    tp = sum(1 for p, t in zip(predicted_verdicts, true_verdicts)
             if p == positive_label and t == positive_label)
    actual_pos = sum(1 for t in true_verdicts if t == positive_label)
    return tp / actual_pos if actual_pos > 0 else 0.0


def action_precision(
    recommended_actions: list[str],
    ground_truth_actions: list[str],
) -> float:
    """Fraction of recommended actions matching the ground truth action."""
    if not recommended_actions:
        return 0.0
    correct = sum(
        1 for rec, gt in zip(recommended_actions, ground_truth_actions)
        if _action_matches(rec, gt)
    )
    return correct / len(recommended_actions)


def hypothesis_accuracy(
    hypothesis_summaries: list[str],
    true_cause_patterns: list[str],
) -> float:
    """Fraction of hypotheses that correctly identify the true cause pattern."""
    if not hypothesis_summaries:
        return 0.0
    correct = sum(
        1 for h, c in zip(hypothesis_summaries, true_cause_patterns)
        if any(kw in h.lower() for kw in c.lower().split())
    )
    return correct / len(hypothesis_summaries)


def _action_matches(recommended: str, ground_truth: str) -> bool:
    gt_keywords = {
        "rollback_deploy":       ["roll back", "rollback", "revert"],
        "drain_and_ticket":      ["drain", "ticket", "thermal"],
        "flush_dns_cache":       ["flush", "dns", "cache"],
        "rotate_certificate":    ["certificate", "rotate", "cert"],
        "expand_volume":         ["disk", "volume", "expand"],
        "restart_service":       ["restart", "memory", "oom"],
        "isolate_dependency":    ["escalate", "isolate", "dependency"],
    }
    kws = gt_keywords.get(ground_truth, [ground_truth])
    rec_lower = recommended.lower()
    return any(kw in rec_lower for kw in kws)
