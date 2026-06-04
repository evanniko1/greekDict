"""Tests for keyness statistics (#46): Dunning G² + Hardie Log Ratio with CI.
Run: pytest tests/ -q

Replaces the old `log2((pm_p+0.1)/(pm_n+0.1))` (an unmodelled ratio with an arbitrary
smoother) with a proper separation of effect size (`_hardie_log_ratio` + 95% CI) from
significance (`_log_likelihood_g2`, ~χ²₁).
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api", "app"))

from main import _log_likelihood_g2, _hardie_log_ratio  # noqa: E402


# ── Dunning G² ───────────────────────────────────────────────────────────────

def test_g2_zero_when_rates_equal():
    # a/c == b/d → no evidence of register preference → G² ≈ 0
    assert _log_likelihood_g2(100, 100, 1_000_000, 1_000_000) < 1e-6


def test_g2_large_when_lopsided():
    # common in corpus 1, absent-ish in corpus 2 → big G²
    g2 = _log_likelihood_g2(500, 5, 1_000_000, 1_000_000)
    assert g2 > 100  # far past the p<0.001 bar (10.83)


def test_g2_symmetric_in_swap():
    a, b, c, d = 300, 40, 800_000, 1_200_000
    assert abs(_log_likelihood_g2(a, b, c, d) - _log_likelihood_g2(b, a, d, c)) < 1e-9


def test_g2_nonnegative():
    for a, b in [(1, 1), (1, 100), (100, 1), (50, 50)]:
        assert _log_likelihood_g2(a, b, 1_000_000, 1_000_000) >= 0.0


# ── Hardie Log Ratio + CI ─────────────────────────────────────────────────────

def test_log_ratio_one_means_twice_as_frequent():
    # a/c = 2·(b/d) → log2 ratio = 1
    lr, lo, hi = _hardie_log_ratio(200, 100, 1_000_000, 1_000_000)
    assert abs(lr - 1.0) < 1e-9
    assert lo < lr < hi


def test_log_ratio_sign_flips_with_direction():
    lr_p, *_ = _hardie_log_ratio(300, 30, 1_000_000, 1_000_000)   # leans corpus 1
    lr_n, *_ = _hardie_log_ratio(30, 300, 1_000_000, 1_000_000)   # leans corpus 2
    assert lr_p > 0 > lr_n
    assert abs(lr_p + lr_n) < 1e-9  # equal magnitude, opposite sign


def test_ci_narrows_with_more_data():
    # Same ratio, 10× the counts → tighter interval (less sampling uncertainty).
    _, lo_small, hi_small = _hardie_log_ratio(50, 25, 1_000_000, 1_000_000)
    _, lo_big, hi_big = _hardie_log_ratio(500, 250, 1_000_000, 1_000_000)
    assert (hi_big - lo_big) < (hi_small - lo_small)


def test_ci_brackets_point_estimate():
    lr, lo, hi = _hardie_log_ratio(123, 77, 900_000, 1_100_000)
    assert lo < lr < hi
    assert math.isfinite(lo) and math.isfinite(hi)
