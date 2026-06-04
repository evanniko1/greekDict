"""Tests for trend significance (#45). Run: pytest tests/ -q

`explore_trends` used an OLS slope t-test (assumes i.i.d. years). We replaced it with:
  · `_theil_sen_slope(years, vals)` — robust slope (median of pairwise slopes), ranking.
  · `_mann_kendall_p(vals)` — non-parametric Mann–Kendall trend test; returns (p, S).
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines", "ingest"))

from main import _theil_sen_slope, _mann_kendall_p  # noqa: E402

YEARS = list(range(2011, 2025))  # 14 years, like the news axis


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
    p, s = _mann_kendall_p(vals)
    assert s == len(YEARS) * (len(YEARS) - 1) // 2  # every pair concordant
    assert p < 0.01


def test_mk_flat_is_not_significant():
    p, s = _mann_kendall_p([5.0] * len(YEARS))
    assert s == 0
    assert p == 1.0


def test_mk_decreasing_negative_S():
    vals = [float(i) for i in range(len(YEARS))][::-1]
    p, s = _mann_kendall_p(vals)
    assert s < 0
    assert p < 0.01


def test_mk_short_series_guarded():
    # Below 4 points the test abstains (p=1) rather than emit a spurious flag.
    assert _mann_kendall_p([1.0, 2.0, 3.0])[0] == 1.0


def test_mk_noisy_series_not_significant():
    # A non-monotone wobble around a flat mean should not register as a trend.
    vals = [5.0, 5.2, 4.9, 5.1, 5.0, 4.8, 5.2, 5.0, 4.9, 5.1, 5.0, 5.05, 4.95, 5.0]
    p, _s = _mann_kendall_p(vals)
    assert p > 0.05
