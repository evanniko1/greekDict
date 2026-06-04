"""Tests for anchored/iterative Procrustes alignment (#48). Run: pytest tests/ -q

`_align(base_wv, other_wv)` rotates one slice's embedding into another's frame. The
fix: fit the rotation on stable anchor words and iteratively prune the ones that
drifted, instead of letting the whole shared vocabulary vote — otherwise the drifted
words pull the frame and contaminate every measured drift.

We build two toy embeddings related by a known orthogonal rotation Q, then inject a
handful of "drifted" words whose other-slice vectors are unrelated. A correct anchored
fit should recover Q on the stable words and leave their residual near zero, clearly
better than a naive fit that includes the drifters.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines", "ingest"))

KeyedVectors = pytest.importorskip("gensim.models").KeyedVectors
from scipy.linalg import orthogonal_procrustes  # noqa: E402

from ingest_diachronic import _align  # noqa: E402


def _kv(keys, mat):
    kv = KeyedVectors(mat.shape[1])
    kv.add_vectors(keys, mat)
    return kv


def _build(n_stable=80, n_drift=20, d=12, seed=0):
    rng = np.random.default_rng(seed)
    # random orthogonal rotation Q
    Q, _ = np.linalg.qr(rng.normal(size=(d, d)))
    stable_keys = [f"s{i}" for i in range(n_stable)]
    drift_keys = [f"d{i}" for i in range(n_drift)]
    base_stable = rng.normal(size=(n_stable, d))
    base_drift = rng.normal(size=(n_drift, d))
    base = _kv(stable_keys + drift_keys, np.vstack([base_stable, base_drift]).astype("float32"))
    # other slice: stable words = base rotated by Q; drift words = unrelated vectors
    other_stable = base_stable @ Q
    other_drift = rng.normal(size=(n_drift, d))  # moved arbitrarily
    other = _kv(stable_keys + drift_keys, np.vstack([other_stable, other_drift]).astype("float32"))
    return base, other, stable_keys, drift_keys, Q


def _mean_stable_residual(base, aligned, key_index, stable_keys):
    res = [np.linalg.norm(aligned[key_index[w]] - base[w]) for w in stable_keys]
    return float(np.mean(res))


def test_anchored_recovers_stable_words():
    base, other, stable_keys, _drift, _Q = _build()
    aligned, key_index = _align(base, other)
    assert aligned is not None
    # Stable words should align almost perfectly (drifters pruned out of the fit).
    assert _mean_stable_residual(base, aligned, key_index, stable_keys) < 0.05


def test_anchored_beats_naive_full_fit():
    """The whole point of #48: anchored+pruned alignment must leave a smaller residual
    on the stable words than a naive fit over the full shared vocabulary."""
    base, other, stable_keys, drift_keys, _Q = _build(seed=3)

    # naive full-vocab Procrustes (the old behaviour)
    all_keys = stable_keys + drift_keys
    A = np.vstack([other[w] for w in all_keys])
    B = np.vstack([base[w] for w in all_keys])
    R_naive, _ = orthogonal_procrustes(A, B)
    naive_res = float(np.mean([
        np.linalg.norm(other[w] @ R_naive - base[w]) for w in stable_keys]))

    aligned, key_index = _align(base, other)
    anchored_res = _mean_stable_residual(base, aligned, key_index, stable_keys)
    assert anchored_res < naive_res
    assert anchored_res < 0.5 * naive_res  # and substantially so


def test_align_too_sparse_returns_none():
    base = _kv(["a", "b", "c"], np.eye(3, dtype="float32"))
    other = _kv(["x", "y", "z"], np.eye(3, dtype="float32"))  # no shared keys
    aligned, key_index = _align(base, other)
    assert aligned is None and key_index is None
