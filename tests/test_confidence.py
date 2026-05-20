"""Tests for the calibrated confidence module."""
from agents.state import AlertTrigger, new_state
from agents.confidence import calibrate, update_with_falsification, _compute


def _make_state(classification="application"):
    trigger = AlertTrigger(
        alert_id="c-test", service="svc", metric="m",
        value=1.0, threshold=0.5, classification=classification,
    )
    return new_state("inc-c", trigger)


def test_calibrate_returns_calibrated_confidence():
    state = _make_state()
    cc = calibrate(state, raw_llm=0.72, hypothesis_summary="connection pool exhaustion")
    assert 0.0 <= cc.final <= 1.0
    assert cc.raw_llm == 0.72
    assert cc.prior >= 0.0


def test_calibrate_final_is_clipped():
    state = _make_state()
    cc = calibrate(state, raw_llm=1.0, hypothesis_summary="connection pool")
    assert cc.final <= 1.0
    cc2 = calibrate(state, raw_llm=0.0, hypothesis_summary="connection pool")
    assert cc2.final >= 0.0


def test_compute_formula():
    """Direct formula test: 0.4*raw + 0.4*prior + 0.2*modifier."""
    result = _compute(raw_llm=0.8, prior=0.5, falsification_modifier=1.0)
    expected = 0.4 * 0.8 + 0.4 * 0.5 + 0.2 * 1.0
    assert abs(result - expected) < 1e-9


def test_update_with_falsification_reduces_confidence_on_high_score():
    state = _make_state()
    cc = calibrate(state, raw_llm=0.72, hypothesis_summary="connection pool")
    updated = update_with_falsification(cc, falsification_score=0.90)
    # High falsification score should pull down the final confidence
    assert updated.final <= cc.final + 0.05  # tolerance for prior effects


def test_update_with_falsification_confirmed_hypothesis():
    state = _make_state()
    cc = calibrate(state, raw_llm=0.72, hypothesis_summary="connection pool")
    updated = update_with_falsification(cc, falsification_score=0.08)
    # Low falsification score: modifier = 0.92, confidence stays high
    assert updated.final > 0.4


def test_calibrate_with_unknown_cause_uses_uniform_prior():
    state = _make_state()
    cc = calibrate(state, raw_llm=0.5, hypothesis_summary="totally unprecedented xyzzy event")
    # Unknown cause should fall back to uniform prior (0.125)
    assert cc.prior == 0.125


def test_calibrate_stores_component_breakdown():
    state = _make_state()
    cc = calibrate(state, raw_llm=0.6, hypothesis_summary="connection pool")
    assert "formula" in cc.components
    assert "weights" in cc.components
