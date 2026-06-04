"""Tests for autocorrelation-robust trend significance (#45). Run: pytest tests/ -q

`explore_trends` used to score trend significance with an OLS slope t-test that
assumed the yearly points were i.i.d. Frequency series are serially correlated, so
that p was anti-conservative (it flagged too many trends). We replaced it with:

  · `_theil_sen_slope(years, vals)` — the robust slope (median of pairwise slopes),
    used for ranking/display; a single outlier year can't swing it like it swings OLS.
  · `_mann_kendall_p(years, vals)` — non-parametric Mann–Kendall trend test with the
    Hamed–Rao (1998) autocorrelation correction to Var(S); returns (p_two_sided, S).
"""

import math
import os
import sys

import numpy as np
from scipy.stats import norm, rankdata

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines", "ingest"))

from main import _theil_sen_slope, _mann_kendall_p  # noqa: E402

YEARS = list(range(2011, 2025))  # 14 years, like the news axis


def _naive_mk_p(vals):
    """Uncorrected Mann–Kendall p (no Hamed–Rao) — baseline for the correction test."""
    x = np.asarray(vals, float)
    n = len(x)
    s = sum(int(np.sign(x[k + 1:] - x[k]).sum()) for k in range(n - 1))
    _, c = np.unique(x, return_counts=True)
    var = (n * (n - 1) * (2 * n + 5) - float(np.sum(c * (c - 1) * (2 * c + 5)))) / 18.0
    z = (s - 1) / math.sqrt(var) if s > 0 else ((s + 1) / math.sqrt(var) if s < 0 else 0.0)
    return min(2 * norm.sf(abs(z)), 1.0)


# ── Theil–Sen slope ──────────────────────────────────────────────────────────

def test_sen_slope_monotone():
    vals = [float(i) for i in range(len(YEARS))]
    assert abs(_theil_sen_slope(YEARS, vals) - 1.0) < 1e-9


def test_sen_slope_flat_is_zero():
    assert _theil_sen_slope(YEARS, [5.0] * len(YEARS)) == 0.0


def test_sen_slope_sign_flips_for_decreasing():
    vals = [float(i) for i in range(len(YEARS))][::-1]
    assert abs(_theil_sen_slope(YEARS, vals) + 1.0) < 1e-9


def test_sen_slope_robust_to_single_outlier():
    """One freak year must not move the slope — the whole reason to use Sen over OLS."""
    clean = [float(i) for i in range(len(YEARS))]
    spiked = list(clean)
    spiked[7] += 50.0
    assert abs(_theil_sen_slope(YEARS, spiked) - 1.0) < 1e-9  # unchanged
    # OLS slope on the same data is visibly pulled up (sanity that the spike matters):
    ols = np.polyfit(YEARS, spiked, 1)[0]
    assert ols > 1.05  # OLS is dragged off the true slope of 1.0; Sen is not


def test_sen_slope_empty_or_singleton():
    assert _theil_sen_slope([], []) == 0.0
    assert _theil_sen_slope([2020], [3.0]) == 0.0


# ── Mann–Kendall (Hamed–Rao) ─────────────────────────────────────────────────

def test_mk_monotone_increasing_is_significant():
    vals = [float(i) for i in range(len(YEARS))]
    p, s = _mann_kendall_p(YEARS, vals)
    assert s == len(YEARS) * (len(YEARS) - 1) // 2  # every pair concordant
    assert p < 0.01


def test_mk_flat_is_not_significant():
    p, s = _mann_kendall_p(YEARS, [5.0] * len(YEARS))
    assert s == 0
    assert p == 1.0


def test_mk_decreasing_negative_S():
    vals = [float(i) for i in range(len(YEARS))][::-1]
    p, s = _mann_kendall_p(YEARS, vals)
    assert s < 0
    assert p < 0.01


def test_mk_short_series_guarded():
    # Below 4 points the test abstains (p=1) rather than emit a spurious flag.
    assert _mann_kendall_p([2020, 2021, 2022], [1.0, 2.0, 3.0])[0] == 1.0


def test_hamed_rao_correction_inflates_p_on_autocorrelated_series():
    """The core of #45: on a serially-correlated series the autocorrelation-corrected
    p must be >= the naive MK p (the correction can only widen, never narrow)."""
    np.random.seed(3)
    e = np.random.normal(0, 1, len(YEARS))
    v = [0.0]
    for i in range(1, len(YEARS)):
        v.append(0.9 * v[-1] + 0.25 * i + e[i])  # AR(1) + weak trend
    p_naive = _naive_mk_p(v)
    p_hr, _ = _mann_kendall_p(YEARS, v)
    assert p_hr >= p_naive
