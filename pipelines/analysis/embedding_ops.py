"""Corrected embedding alignment + pooling for the diachronic layer.

Methodology waves #48/#49/#51 (audit F14/F15). Like `estimators.py`, these land the
CORRECTED operations as pure, testable functions — validated offline before they are
wired into `ingest_diachronic` and the Tier B rebuild runs them.

  #48 (F14) — `procrustes_align`. The shipped `_align` fits the rotation on raw,
       unnormalized word2vec vectors (Hamilton et al. 2016 §3.1 L2-normalize first) and
       prunes anchors by the ABSOLUTE Euclidean residual ‖A·R − B‖, which scales with
       vector norm — so it evicts the highest-frequency, best-estimated words
       (corr(residual, norm) = 0.996 in the audit sim), the opposite of the stated "keep
       stable high-frequency anchors." Fix: L2-normalize before Procrustes and prune by a
       SCALE-FREE cosine residual, so pruning tracks angular drift, not magnitude.

  #49 (F15) — `balanced_pool_budget` + `size_weighted_mean_year` + `member_sets_identical`.
       Pooled slices are built by uniform sampling over concatenated member files, so the
       mixture is weighted by each year's raw line count; with the news 300k→1M jump at
       2019, the slice labelled 2018 is 69% 2019–2020 text (+1.05 yr label error), and two
       news slices (2011, 2013 — 2012 absent) train on one identical population. Fix:
       sample equal lines per member year so the label is the content centroid, record the
       size-weighted mean year, and refuse to emit two slices with identical member sets.

  #51 — `is_reliable` / `reliability_gate`. Rare-word vectors are noise even within one
       model; a per-era frequency floor decides when a lemma's neighbour list / drift is
       trustworthy vs suppressed as low-evidence. The floor is calibrated against the D3
       no-change noise measurement (see the harness `--freq-probe`).
"""

from __future__ import annotations

import math


# ─────────────────────────────────────────────────────────────────────────────
# #48 — Hamilton-compliant anchored Procrustes with a scale-free prune residual
# ─────────────────────────────────────────────────────────────────────────────

def _unit_rows(M):
    """L2-normalize each row (Hamilton 2016 §3.1). Zero rows stay zero."""
    import numpy as np
    n = np.linalg.norm(M, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return M / n


def _procrustes(A, B):
    from scipy.linalg import orthogonal_procrustes
    R, _ = orthogonal_procrustes(A, B)
    return R


def _cosine_residual(P, Q):
    """Per-row cosine distance between rows of P and Q — scale-free, unlike ‖P−Q‖."""
    import numpy as np
    pn = _unit_rows(P)
    qn = _unit_rows(Q)
    return 1.0 - np.sum(pn * qn, axis=1)


def procrustes_align(X, Y, anchor_idx, prune_iters: int = 2, prune_frac: float = 0.25,
                     normalize: bool = True):
    """Rotate X into Y's frame via orthogonal Procrustes fit on `anchor_idx` rows.

    X, Y are (n, d) matrices whose rows are the SAME vocabulary in the SAME order.
    Hamilton-compliant when normalize=True: rows are L2-normalized before fitting, and
    the iterative anchor pruning drops the highest COSINE-residual (most drifted) anchors
    — not the highest-norm ones (F14). Returns (X_aligned, R, kept_anchor_idx).
    X_aligned is X's rows (normalized iff normalize) rotated into Y's frame."""
    import numpy as np

    Xn = _unit_rows(X) if normalize else np.asarray(X, dtype=float)
    Yn = _unit_rows(Y) if normalize else np.asarray(Y, dtype=float)

    kept = list(anchor_idx)
    A, B = Xn[kept], Yn[kept]
    R = _procrustes(A, B)
    for _ in range(max(0, prune_iters)):
        if len(kept) < 20:
            break
        resid = _cosine_residual(A @ R, B)          # scale-free (was ‖A·R − B‖)
        thresh = float(np.quantile(resid, 1.0 - prune_frac))
        keep = resid <= thresh
        if keep.all() or int(keep.sum()) < 10:
            break
        kept = [kept[i] for i in range(len(kept)) if keep[i]]
        A, B = Xn[kept], Yn[kept]
        R = _procrustes(A, B)

    return Xn @ R, R, kept


def alignment_residuals(X, Y, anchor_idx, normalize: bool = True):
    """Diagnostic: per-anchor residual after a single Procrustes fit — cosine when
    normalize=True (scale-free), Euclidean otherwise (the buggy, norm-correlated one).
    Used to demonstrate that the corrected residual is uncorrelated with vector norm."""
    import numpy as np
    Xn = _unit_rows(X) if normalize else np.asarray(X, dtype=float)
    Yn = _unit_rows(Y) if normalize else np.asarray(Y, dtype=float)
    A, B = Xn[list(anchor_idx)], Yn[list(anchor_idx)]
    R = _procrustes(A, B)
    if normalize:
        return _cosine_residual(A @ R, B)
    return np.linalg.norm(A @ R - B, axis=1)


# ─────────────────────────────────────────────────────────────────────────────
# #49 — balanced pooling (equal contribution per member year)
# ─────────────────────────────────────────────────────────────────────────────

def balanced_pool_budget(line_counts: dict[int, int], target_total: int) -> dict[int, int]:
    """Lines to draw from each member year so contributions are EQUAL (F15), capped by
    availability, redistributing any shortfall to years that still have lines.

    `line_counts` maps member year → available lines. Equal shares mean the pooled
    slice's content centroid is the label (centre) year, instead of being dragged toward
    whichever neighbour happens to be a larger corpus. Returns year → lines to draw
    (sum ≤ target_total, and ≤ each year's availability)."""
    years = sorted(line_counts)
    if not years:
        return {}
    budget = {y: 0 for y in years}
    remaining = dict(line_counts)
    pool = target_total
    active = [y for y in years if remaining[y] > 0]
    while pool > 0 and active:
        share = pool // len(active)
        if share == 0:
            # distribute the final remainder one line at a time to the years with room
            for y in active:
                if pool <= 0:
                    break
                budget[y] += 1
                remaining[y] -= 1
                pool -= 1
            active = [y for y in active if remaining[y] > 0]
            continue
        progressed = False
        for y in list(active):
            take = min(share, remaining[y])
            if take > 0:
                budget[y] += take
                remaining[y] -= take
                pool -= take
                progressed = True
        active = [y for y in active if remaining[y] > 0]
        if not progressed:
            break
    return {y: n for y, n in budget.items() if n > 0}


def size_weighted_mean_year(draw: dict[int, int]) -> float:
    """Content centroid of a pooled slice: Σ year·lines / Σ lines. Records the label
    error F15 flags (a slice labelled 2018 whose centroid is 2018.72)."""
    total = sum(draw.values())
    if total == 0:
        return float("nan")
    return sum(y * n for y, n in draw.items()) / total


def member_sets_identical(a, b) -> bool:
    """True if two slices' member-year sets are identical — such slices are drawn from
    one population and must NOT be emitted as two independent time points (F15: news
    2011 and 2013 both pool to {2011, 2013} because 2012 is absent)."""
    return set(a) == set(b)


# ─────────────────────────────────────────────────────────────────────────────
# #51 — per-era reliability floor for neighbour lists / drift
# ─────────────────────────────────────────────────────────────────────────────

def is_reliable(count: int | None, floor: int) -> bool:
    """Whether a lemma's per-era vector is trustworthy enough to publish neighbours /
    drift for. Below `floor` occurrences in that era the vector is dominated by
    estimation noise (its drift is indistinguishable from the no-change control), so
    the neighbour list is suppressed or flagged low-evidence rather than shown as fact."""
    return count is not None and count >= floor


def reliability_gate(counts: dict[str, int], floor: int) -> dict[str, bool]:
    """Vectorised `is_reliable` over {lemma: era_count}."""
    return {w: is_reliable(c, floor) for w, c in counts.items()}
