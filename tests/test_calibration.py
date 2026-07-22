"""Classifier calibration + abstention (methodology wave #47, audit F16/F17/F45).

Offline validation on synthetic score matrices — no embedding needed. The centrepiece:
calibration must reduce ECE on deliberately miscalibrated scores, and per-class
thresholds must hit a precision target where a single absolute gate cannot.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines", "analysis"))
from calibration import (  # noqa: E402
    expected_calibration_error, brier_score, reliability_curve, IsotonicCalibrator,
    tune_class_thresholds, decide_with_abstain, precision_coverage_report,
)


def _softmax(z):
    e = np.exp(z - z.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def _synthetic(n=1500, k=4, sharpness=1.0, seed=0):
    """n samples, k classes. `sharpness`<1 makes the model over-confident (miscalibrated):
    scores are peaked but only `accuracy` of them are actually right."""
    rng = np.random.default_rng(seed)
    y = rng.integers(0, k, size=n)
    logits = rng.normal(0, 1, size=(n, k))
    # make the true class usually (but not always) the argmax, then sharpen
    for i in range(n):
        logits[i, y[i]] += rng.normal(1.4, 1.0)
    probs = _softmax(logits / sharpness)
    return probs, y


# ── calibration diagnostics ──────────────────────────────────────────────────

def test_ece_zero_for_perfect_calibration():
    # confidence == accuracy in every bin
    conf = np.array([0.9] * 100 + [0.5] * 100)
    correct = np.array([1] * 90 + [0] * 10 + [1] * 50 + [0] * 50)
    assert expected_calibration_error(conf, correct, n_bins=10) < 0.02


def test_ece_flags_overconfidence():
    # claims 0.95 confidence but only 60% correct → large ECE
    conf = np.full(200, 0.95)
    correct = np.array([1] * 120 + [0] * 80)
    assert expected_calibration_error(conf, correct) > 0.3


def test_brier_rewards_the_truth():
    classes = ["a", "b"]
    good = brier_score([[0.9, 0.1]], ["a"], classes)
    bad = brier_score([[0.1, 0.9]], ["a"], classes)
    assert good < bad


# ── isotonic calibration ─────────────────────────────────────────────────────

def test_isotonic_calibration_reduces_ece():
    """The core of #47: an over-confident model's ECE must drop after calibration."""
    probs, y = _synthetic(n=2000, k=5, sharpness=0.45, seed=1)  # over-confident
    classes = list(range(5))

    def ece_of(P, yy):
        conf = P.max(axis=1)
        correct = (P.argmax(axis=1) == yy).astype(float)
        return expected_calibration_error(conf, correct, n_bins=15)

    # fit on first half, evaluate on second (no leakage)
    h = len(y) // 2
    cal = IsotonicCalibrator().fit(probs[:h], y[:h], classes)
    before = ece_of(probs[h:], y[h:])
    after = ece_of(cal.transform(probs[h:]), y[h:])
    assert after < before, f"calibration did not reduce ECE ({before:.3f} → {after:.3f})"


def test_calibrated_rows_are_distributions():
    probs, y = _synthetic(seed=2)
    cal = IsotonicCalibrator().fit(probs, y, list(range(probs.shape[1])))
    out = cal.transform(probs)
    assert np.allclose(out.sum(axis=1), 1.0, atol=1e-6)


# ── per-class thresholds + abstention ────────────────────────────────────────

def test_per_class_thresholds_achieve_target_precision():
    """The F17 fix: tuned per-class thresholds hit the precision target on held-out data,
    where a single absolute gate cannot because posteriors differ by class."""
    probs, y = _synthetic(n=3000, k=4, sharpness=0.8, seed=3)
    classes = list(range(4))
    h = len(y) // 2
    thr = tune_class_thresholds(probs[:h], y[:h], classes, target_precision=0.85)
    rep = precision_coverage_report(probs[h:], y[h:], classes, thr, margin=0.0)
    # overall precision on labeled should be at/above target (allow modest MC slack)
    assert rep["precision_on_labeled"] >= 0.80
    assert 0.0 < rep["coverage"] < 1.0  # it abstains on some, labels others


def test_higher_precision_target_lowers_coverage():
    """The precision/coverage trade-off must hold: demanding more precision labels less."""
    probs, y = _synthetic(n=3000, k=4, sharpness=0.8, seed=4)
    classes = list(range(4))
    h = len(y) // 2
    lo = precision_coverage_report(
        probs[h:], y[h:], classes,
        tune_class_thresholds(probs[:h], y[:h], classes, target_precision=0.60), margin=0.0)
    hi = precision_coverage_report(
        probs[h:], y[h:], classes,
        tune_class_thresholds(probs[:h], y[:h], classes, target_precision=0.95), margin=0.0)
    assert hi["coverage"] <= lo["coverage"]


def test_abstain_on_thin_margin():
    classes = ["a", "b", "c"]
    thr = {"a": 0.3, "b": 0.3, "c": 0.3}
    # confident + clear winner → label
    assert decide_with_abstain([0.7, 0.2, 0.1], classes, thr, margin=0.1) == "a"
    # two near-tied top classes → abstain despite clearing the threshold
    assert decide_with_abstain([0.45, 0.44, 0.11], classes, thr, margin=0.1) is None


def test_abstain_below_class_threshold():
    classes = ["a", "b"]
    thr = {"a": 0.8, "b": 0.3}
    # 0.6 clears a naive 0.5 gate but not class a's tuned 0.8 → abstain
    assert decide_with_abstain([0.6, 0.4], classes, thr, margin=0.0) is None
    # same margin, class b's lower threshold → labeled
    assert decide_with_abstain([0.4, 0.6], classes, thr, margin=0.0) == "b"


def test_report_matches_the_deployed_rule():
    """precision_coverage_report is computed under decide_with_abstain, so the reported
    number is the deployed one (F45), not a different split model's."""
    classes = ["a", "b"]
    probs = [[0.9, 0.1], [0.85, 0.15], [0.55, 0.45], [0.2, 0.8]]
    y = ["a", "a", "b", "b"]
    thr = {"a": 0.8, "b": 0.5}
    rep = precision_coverage_report(probs, y, classes, thr, margin=0.1)
    # row 3 (0.55/0.45) abstains: below margin AND below a's threshold; row 2 labels a (correct)
    assert rep["abstained"] == 1
    assert rep["per_field"]["a"]["precision"] == 1.0
