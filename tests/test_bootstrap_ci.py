"""Tests for the percentile bootstrap CI (#43). Run: pytest tests/ -q

`_percentile_ci(replicates)` returns the (2.5, 97.5) percentile interval of the
bootstrap drift samples. We keep it plain percentile (not faux-BCa): the interval is
only as smooth as the resample count K, honestly coarse below K≈100.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines", "ingest"))

from bootstrap_drift import _percentile_ci  # noqa: E402


def test_matches_numpy_percentiles():
    rng = np.random.default_rng(0)
    reps = list(rng.normal(0.30, 0.05, 400))
    lo, hi = _percentile_ci(reps)
    assert abs(lo - np.percentile(reps, 2.5)) < 1e-3
    assert abs(hi - np.percentile(reps, 97.5)) < 1e-3


def test_interval_ordered_and_brackets_mean():
    rng = np.random.default_rng(1)
    reps = list(rng.normal(0.4, 0.04, 300))
    lo, hi = _percentile_ci(reps)
    assert lo < hi
    assert lo < float(np.mean(reps)) < hi


def test_wider_for_noisier_samples():
    rng = np.random.default_rng(2)
    tight = list(rng.normal(0.3, 0.01, 300))
    loose = list(rng.normal(0.3, 0.10, 300))
    lo_t, hi_t = _percentile_ci(tight)
    lo_l, hi_l = _percentile_ci(loose)
    assert (hi_l - lo_l) > (hi_t - lo_t)


def test_too_few_replicates_returns_none():
    assert _percentile_ci([0.3]) is None
    assert _percentile_ci([]) is None
