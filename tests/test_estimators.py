"""Corrected diachronic/keyness estimators (methodology waves #43–#46).

These are the offline unit validations that must pass before the estimators are wired
into the pipeline and the Tier B rebuild repopulates any panel. Each test targets the
specific audit defect the wave fixes.
"""

import math
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines", "analysis"))
from estimators import (  # noqa: E402
    change_point, mann_kendall, theil_sen, dunning_g2, g2_p_value,
    hardie_log_ratio, bh_fdr, bca_interval,
)


# ── #44 change-point (Pettitt) ───────────────────────────────────────────────

def _series(vals):
    return list(enumerate(vals))


# NOTE Pettitt has little power on very short series: even a perfect 4+4 step at n=8
# gives p≈0.14. That is honest — the news axis (11 slices) can only detect strong,
# sustained shifts. The "should detect" tests therefore use ~16-point series.

def test_flat_series_has_no_change_point():
    """A no-change series must not yield a significant change point (the whole point
    of adding a null — the old argmax always returned some year)."""
    vals = [0.30, 0.31, 0.29, 0.30, 0.31, 0.30, 0.29, 0.31, 0.30, 0.31, 0.29, 0.30]
    cp = change_point(_series(vals))
    assert cp.significant is False
    assert cp.label is None


def test_clean_step_is_detected_at_the_step():
    """A genuine level shift is found at the right place, and flagged significant."""
    vals = [0.10, 0.11, 0.09, 0.10, 0.11, 0.09, 0.10, 0.11,
            0.40, 0.41, 0.39, 0.40, 0.41, 0.39, 0.40, 0.41]  # step after index 7
    cp = change_point(_series(vals))
    assert cp.significant is True
    assert cp.index in (6, 7, 8)


def test_single_spike_does_not_masquerade_as_a_change_point():
    """The audit's F5/F9 failure mode: one artefactual spike (a corpus gap) made the
    old argmax detector fire. A location test must NOT be fooled by a lone spike — and
    this series is long enough that a real step WOULD be detected (see the test above),
    so 'not significant' is a genuine negative, not a power artefact."""
    vals = [0.10, 0.11, 0.10, 0.11, 0.10, 0.11, 0.10, 0.95,  # one outlier at idx 7
            0.11, 0.10, 0.11, 0.10, 0.12, 0.10, 0.11, 0.10]
    cp = change_point(_series(vals))
    assert cp.significant is False, "a single spike must not be a sustained change point"


def test_permutation_null_agrees_with_asymptotic_on_a_clear_step():
    vals = [0.1] * 8 + [0.5] * 8
    cp_asym = change_point(_series(vals))
    cp_perm = change_point(_series(vals), n_perm=500, seed=1)
    assert cp_asym.significant and cp_perm.significant
    assert cp_perm.index == cp_asym.index


def test_permutation_null_rejects_noise():
    rng = random.Random(0)
    noise = [(y, 0.3 + rng.gauss(0, 0.02)) for y in range(12)]
    cp = change_point(noise, n_perm=500, seed=2)
    assert cp.significant is False


def test_change_point_needs_enough_points():
    assert change_point(_series([0.1, 0.5, 0.9])).significant is False


def test_change_point_reports_the_year_label():
    vals = [0.1] * 8 + [0.6] * 8
    series = list(zip(range(2005, 2021), vals))
    cp = change_point(series)
    assert cp.significant and cp.label in (2012, 2013)


# ── #45 trend (Mann–Kendall + Hamed–Rao) ─────────────────────────────────────

def test_theil_sen_exact_on_a_line():
    ys = list(range(10))
    vals = [3.0 + 2.0 * y for y in ys]
    assert theil_sen(ys, vals) == pytest.approx(2.0)


def test_theil_sen_is_robust_to_one_outlier():
    ys = list(range(10))
    vals = [2.0 * y for y in ys]
    vals[5] = 999.0  # wild outlier
    assert theil_sen(ys, vals) == pytest.approx(2.0)  # median slope unmoved


def test_mann_kendall_detects_a_monotone_trend():
    vals = [float(y) for y in range(12)]
    t = mann_kendall(vals)
    assert t.tau == pytest.approx(1.0)
    assert t.p_value < 0.05


def test_mann_kendall_flat_is_not_significant():
    vals = [0.3, 0.31, 0.29, 0.30, 0.30, 0.31, 0.29, 0.30, 0.30, 0.31]
    assert mann_kendall(vals).p_value > 0.05


def test_hamed_rao_is_more_conservative_under_positive_autocorrelation():
    """The core of #45: a positively autocorrelated series inflates var(S), so the
    corrected p must be >= the naive p (naive is anti-conservative, F10/F39)."""
    rng = random.Random(3)
    # AR(1) with strong positive autocorrelation, no real trend
    x, out = 0.0, []
    for _ in range(30):
        x = 0.8 * x + rng.gauss(0, 1)
        out.append(x)
    t = mann_kendall(out, hamed_rao=True)
    assert t.variance_inflation > 1.0
    assert t.p_value >= t.p_naive


def test_hamed_rao_leaves_iid_series_roughly_unchanged():
    rng = random.Random(4)
    iid = [rng.gauss(0, 1) for _ in range(30)]
    t = mann_kendall(iid, hamed_rao=True)
    # no systematic autocorrelation → inflation near 1
    assert 0.6 < t.variance_inflation < 1.6


# ── #46 keyness (Dunning G², Hardie LR, BH-FDR) ──────────────────────────────

def test_g2_zero_when_proportions_equal():
    assert dunning_g2(10, 10, 1000, 1000) == pytest.approx(0.0, abs=1e-9)


def test_g2_positive_and_grows_with_disparity():
    small = dunning_g2(20, 10, 1000, 1000)
    big = dunning_g2(200, 10, 1000, 1000)
    assert 0 < small < big


def test_g2_p_value_matches_chi2_threshold():
    # G² of 10.83 is the classic p≈0.001 threshold for 1 df
    assert g2_p_value(10.83) == pytest.approx(0.001, abs=2e-4)


def test_hardie_log_ratio_direction_and_symmetry():
    lr, lo, hi = hardie_log_ratio(200, 100, 1000, 1000)
    assert lr == pytest.approx(1.0)  # twice as common → log2 = 1
    assert lo < lr < hi
    lr2, _, _ = hardie_log_ratio(100, 200, 1000, 1000)
    assert lr2 == pytest.approx(-1.0)  # reversed → −1


def test_bh_fdr_monotone_and_controls_discoveries():
    pvals = {i: p for i, p in enumerate([0.001, 0.008, 0.02, 0.04, 0.2, 0.5, 0.9])}
    q, reject = bh_fdr(pvals, alpha=0.05)
    # q monotone in p
    qs = [q[i] for i in sorted(pvals, key=lambda k: pvals[k])]
    assert all(qs[i] <= qs[i + 1] + 1e-12 for i in range(len(qs) - 1))
    # the largest p is never rejected
    assert reject[6] is False


def test_bh_fdr_all_null_rejects_few():
    rng = random.Random(5)
    pvals = {i: rng.random() for i in range(1000)}  # uniform ⇒ all null
    _, reject = bh_fdr(pvals, alpha=0.05)
    assert sum(reject.values()) <= 5  # ~0 expected under the global null


# ── #43 BCa interval ─────────────────────────────────────────────────────────

def test_bca_contains_truth_on_a_symmetric_bootstrap():
    """BCa of a symmetric bootstrap ≈ percentile interval and brackets the observed."""
    rng = random.Random(6)
    reps = [rng.gauss(0.30, 0.02) for _ in range(2000)]
    jack = [0.30 + rng.gauss(0, 0.001) for _ in range(40)]
    lo, hi = bca_interval(0.30, reps, jack, alpha=0.05)
    assert lo < 0.30 < hi
    # symmetric ⇒ close to the 2.5/97.5 percentiles
    import numpy as np
    assert lo == pytest.approx(float(np.percentile(reps, 2.5)), abs=0.01)
    assert hi == pytest.approx(float(np.percentile(reps, 97.5)), abs=0.01)


def test_bca_coverage_is_near_nominal():
    """Empirical coverage check: BCa 95% intervals for the mean of a skewed sample
    should cover the truth ~95% of the time — decisively better than the ~82% the
    K=12 percentile interval measured (F11). Uses a modest B for test speed."""
    import numpy as np
    truth = 1.0  # mean of Exponential(1)
    covered = 0
    trials = 120
    master = random.Random(7)
    for _ in range(trials):
        seed = master.random()
        rng = np.random.default_rng(int(seed * 1e9))
        sample = rng.exponential(1.0, size=40)
        obs = float(sample.mean())
        reps = [float(rng.choice(sample, size=40, replace=True).mean()) for _ in range(400)]
        jack = [float(np.delete(sample, i).mean()) for i in range(len(sample))]
        lo, hi = bca_interval(obs, reps, jack, alpha=0.05)
        if lo <= truth <= hi:
            covered += 1
    coverage = covered / trials
    # allow Monte-Carlo slack, but it must clear the ~0.82 the percentile CI got
    assert coverage >= 0.88, f"BCa coverage {coverage:.2f} too low"
