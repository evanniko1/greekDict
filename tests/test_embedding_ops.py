"""Corrected embedding alignment + pooling (methodology waves #48/#49/#51).

Offline unit validations that must pass before these operations are wired into
ingest_diachronic and the Tier B rebuild runs them. The centrepiece is the F14
reproduction: the corrected residual must be uncorrelated with vector norm, where the
shipped one had corr 0.996.
"""

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines", "analysis"))
from embedding_ops import (  # noqa: E402
    procrustes_align, alignment_residuals, balanced_pool_budget,
    size_weighted_mean_year, member_sets_identical, is_reliable, reliability_gate,
)


def _random_orthogonal(d, seed):
    rng = np.random.default_rng(seed)
    q, r = np.linalg.qr(rng.normal(size=(d, d)))
    # fix signs so it's a proper rotation-ish orthogonal matrix
    q *= np.sign(np.diag(r))
    return q


# ── #48 alignment ────────────────────────────────────────────────────────────

def test_rotation_is_recovered_exactly():
    """A pure rotation with no drift must align back to ≈0 residual for every word."""
    rng = np.random.default_rng(1)
    n, d = 500, 50
    Y = rng.normal(size=(n, d))
    Q = _random_orthogonal(d, 2)
    X = Y @ Q                       # X is Y in a rotated frame, no drift
    anchors = list(range(200))
    X_aligned, R, kept = procrustes_align(X, Y, anchors, prune_iters=0)
    # after alignment, unit-normalized rows should coincide → cosine distance ≈ 0
    resid = 1.0 - np.sum(
        (X_aligned / np.linalg.norm(X_aligned, axis=1, keepdims=True)) *
        (Y / np.linalg.norm(Y, axis=1, keepdims=True)), axis=1)
    assert float(np.median(resid)) < 1e-6


def test_corrected_residual_is_uncorrelated_with_vector_norm():
    """The F14 reproduction. Give words heterogeneous norms and an IDENTICAL angular
    perturbation (so no word drifts more than another), then compare residual-vs-norm
    correlation: the buggy Euclidean residual tracks norm (~1.0); the corrected cosine
    residual must not."""
    rng = np.random.default_rng(3)
    n, d = 2000, 100
    directions = rng.normal(size=(n, d))
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    norms = np.exp(rng.normal(0, 0.6, size=(n, 1)))         # lognormal, heterogeneous
    base = directions * norms

    # identical angular perturbation of every word: rotate all unit directions by the
    # same small orthogonal Q_pert, then restore each word's original norm.
    Q_pert = _random_orthogonal(d, 4)
    perturbed_dirs = directions @ Q_pert
    other = perturbed_dirs * norms                          # same norm, same angular drift
    Q_frame = _random_orthogonal(d, 5)
    other = other @ Q_frame                                 # plus a global frame rotation

    anchors = list(range(n))
    norm_flat = norms.ravel()

    r_cos = alignment_residuals(other, base, anchors, normalize=True)
    r_euc = alignment_residuals(other, base, anchors, normalize=False)

    corr_cos = abs(float(np.corrcoef(r_cos, norm_flat)[0, 1]))
    corr_euc = abs(float(np.corrcoef(r_euc, norm_flat)[0, 1]))

    assert corr_euc > 0.8, f"expected the buggy Euclidean residual to track norm, got {corr_euc:.3f}"
    assert corr_cos < 0.2, f"corrected cosine residual should be ~norm-free, got {corr_cos:.3f}"


def test_pruning_does_not_norm_select_the_kept_anchors():
    """With the corrected residual, the surviving anchor set after pruning must not be
    biased toward low-norm words (the shipped version kept only the 0th–58th norm pct)."""
    rng = np.random.default_rng(6)
    n, d = 1500, 80
    directions = rng.normal(size=(n, d))
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    norms = np.exp(rng.normal(0, 0.6, size=(n, 1)))
    base = directions * norms
    Q = _random_orthogonal(d, 7)
    other = (directions @ Q) * norms                       # uniform angular drift
    anchors = list(range(n))
    _, _, kept = procrustes_align(other, base, anchors, prune_iters=2, prune_frac=0.25)
    kept_norms = norms.ravel()[kept]
    all_median = float(np.median(norms))
    kept_median = float(np.median(kept_norms))
    # kept set's median norm should be close to the full set's, not truncated low
    assert 0.7 * all_median < kept_median < 1.4 * all_median


# ── #49 pooling ──────────────────────────────────────────────────────────────

def test_balanced_pool_equalizes_a_swamped_configuration():
    """The F15 case: pooling ±2 around 2018 with the news size jump. Equal shares, not
    69% from the 1M-line neighbours."""
    counts = {2016: 300_000, 2017: 300_000, 2018: 300_000, 2019: 1_000_000, 2020: 1_000_000}
    draw = balanced_pool_budget(counts, target_total=500_000)
    # 5 members, 500k target → 100k each; the dense 2019/2020 are NOT over-represented
    assert all(draw[y] == 100_000 for y in counts)
    centroid = size_weighted_mean_year(draw)
    assert centroid == pytest.approx(2018.0)               # label = content centroid


def test_balanced_pool_redistributes_shortfall():
    """A member with fewer lines than its equal share gives them up; the rest absorb it."""
    counts = {2010: 5_000, 2011: 300_000, 2012: 300_000}
    draw = balanced_pool_budget(counts, target_total=300_000)
    assert draw[2010] == 5_000                              # capped at availability
    assert sum(draw.values()) == 300_000                   # shortfall redistributed
    assert draw[2011] > 100_000 and draw[2012] > 100_000


def test_balanced_pool_never_exceeds_availability_or_target():
    counts = {2018: 40_000, 2019: 40_000}
    draw = balanced_pool_budget(counts, target_total=500_000)
    assert draw[2018] == 40_000 and draw[2019] == 40_000   # target > available → take all
    assert sum(draw.values()) == 80_000


def test_size_weighted_mean_year_flags_a_dragged_label():
    """The uncorrected (raw-count) pool would have this centroid — the +1.05 yr error."""
    raw = {2016: 300_000, 2017: 300_000, 2018: 300_000, 2019: 1_000_000, 2020: 1_000_000}
    assert size_weighted_mean_year(raw) == pytest.approx(2018.72, abs=0.01)


def test_identical_member_sets_are_detected():
    assert member_sets_identical([2011, 2013], [2013, 2011]) is True
    assert member_sets_identical([2011, 2013], [2011, 2012, 2013]) is False


# ── #51 reliability floor ────────────────────────────────────────────────────

def test_reliability_floor_gates_rare_words():
    assert is_reliable(200, floor=50) is True
    assert is_reliable(20, floor=50) is False
    assert is_reliable(None, floor=50) is False
    assert is_reliable(50, floor=50) is True               # at the floor, inclusive


def test_reliability_gate_is_vectorised():
    counts = {"νερό": 5000, "σπάνιο": 12, "λέξη": 80}
    gate = reliability_gate(counts, floor=50)
    assert gate == {"νερό": True, "σπάνιο": False, "λέξη": True}
