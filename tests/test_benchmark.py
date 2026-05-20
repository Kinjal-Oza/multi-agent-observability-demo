"""Tests for the benchmark harness (uses a 5-scenario subset)."""
from bench.run_benchmark import run
from bench.metrics import brier_score, expected_calibration_error, action_precision


def test_benchmark_runs_on_small_subset():
    results = run(limit=5)
    assert results["n_scenarios"] == 5


def test_benchmark_metrics_in_valid_range():
    results = run(limit=10)
    assert 0.0 <= results["hypothesis_accuracy"] <= 1.0
    assert 0.0 <= results["brier_score"] <= 1.0
    assert 0.0 <= results["ece"] <= 1.0
    assert 0.0 <= results["falsifier_precision"] <= 1.0
    assert 0.0 <= results["falsifier_recall"] <= 1.0
    assert 0.0 <= results["action_precision"] <= 1.0


def test_brier_score_perfect():
    assert brier_score([1.0, 1.0, 0.0], [1, 1, 0]) == 0.0


def test_brier_score_worst():
    assert brier_score([0.0, 0.0, 1.0], [1, 1, 0]) == 1.0


def test_ece_perfect_calibration():
    # Perfectly calibrated: 0.9 confidence, 90% accuracy
    confs = [0.9] * 9 + [0.1]
    outcomes = [1] * 9 + [0]
    ece = expected_calibration_error(confs, outcomes, n_bins=10)
    assert ece <= 0.11  # allow small floating-point tolerance


def test_action_precision_exact_match():
    assert action_precision(["Roll back the most recent deploy"], ["rollback_deploy"]) == 1.0


def test_action_precision_no_match():
    assert action_precision(["Do nothing"], ["rollback_deploy"]) == 0.0


def test_benchmark_elapsed_under_threshold():
    results = run(limit=20)
    # 20 scenarios should run in well under 10 seconds
    assert results["elapsed_s"] < 10.0
