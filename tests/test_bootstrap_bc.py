"""Tests for the bias-corrected bootstrap interval (#43). Run: pytest tests/ -q

`_bc_interval(replicates, theta_hat)` is the bias-correction half of BCa: it shifts
the percentile cut-points by z0 = Φ⁻¹(#{θ*<θ̂}/B) so the interval re-centres on the
point estimate. The previous plain-percentile CI ignored θ̂, which is why the
displayed drift_score could fall outside its own interval. (Acceleration is omitted —
it needs a data-level jackknife incompatible with per-slice word2vec; see the docstring.)
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines", "ingest"))

from bootstrap_drift import _bc_interval  # noqa: E402


def test_symmetric_centered_matches_percentile():
    """When θ̂ equals the bootstrap median, z0≈0 and BC ≈ the plain percentile CI."""
    rng = np.random.default_rng(0)
    reps = list(rng.normal(0.30, 0.05, 400))
    theta = float(np.median(reps))
    lo, hi = _bc_interval(reps, theta)
    plo, phi = np.percentile(reps, 2.5), np.percentile(reps, 97.5)
    assert abs(lo - plo) < 0.01
    assert abs(hi - phi) < 0.01
    assert lo < theta < hi


def test_bias_correction_shifts_toward_point_estimate():
    """If most replicates sit ABOVE θ̂ (positive median-bias, our real failure mode),
    BC must pull the interval DOWN relative to the naive percentile CI."""
    rng = np.random.default_rng(1)
    reps = list(rng.normal(0.40, 0.04, 400))
    theta = 0.30  # point estimate below the replicate cloud
    lo, hi = _bc_interval(reps, theta)
    plo, phi = np.percentile(reps, 2.5), np.percentile(reps, 97.5)
    assert lo < plo  # lower bound moved down
    assert hi < phi  # upper bound moved down


def test_point_estimate_outside_cloud_falls_back():
    """θ̂ entirely outside the replicate range → z0 undefined → percentile fallback."""
    reps = [0.20, 0.22, 0.24, 0.26, 0.28]
    lo, hi = _bc_interval(reps, theta_hat=0.99)  # above every replicate
    assert lo <= hi
    assert lo >= 0.20 - 1e-9


def test_too_few_replicates_returns_none():
    assert _bc_interval([0.3], 0.3) is None
    assert _bc_interval([], 0.3) is None


def test_interval_is_ordered_and_finite():
    rng = np.random.default_rng(2)
    reps = list(rng.normal(0.1, 0.2, 200))
    lo, hi = _bc_interval(reps, 0.1)
    assert np.isfinite(lo) and np.isfinite(hi)
    assert lo <= hi
