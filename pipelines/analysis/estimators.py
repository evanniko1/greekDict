"""Corrected statistical estimators for the diachronic + keyness layer.

Methodology waves #43–#46 (audit F5/F9/F10/F11/F20/F39/F43). These are **pure
functions** — no DB, no API, no I/O — so they are unit-testable and can be validated
in the offline harness against a null BEFORE the Tier B rebuild wires them into
ingest_diachronic / main.py. Wiring is a separate, later step; landing them here first
is the point of "validate offline before repopulating."

Each replaces a specific defect:

  #44  change-point — the shipped detector is argmax of the steepest single trajectory
       step, gated by a robust z against the other steps. It has no null distribution and
       collapses onto a single artefactual spike: 82.6% of news words got change-point
       2016, the first slice after a three-year corpus gap (F5/F9). Replaced by the
       Pettitt (1979) non-parametric change-point test, which detects a shift in LOCATION
       (not a single-step spike) and carries a real p-value, plus an exact permutation
       null option. A lone gap-induced spike does not shift the location, so it no longer
       wins.

  #45  trend — Mann–Kendall assumes independent years; annual series are serially
       correlated, which makes the naive test anti-conservative (F10/F39). Added the
       Hamed & Rao (1998) autocorrelation correction, which inflates var(S) by the
       effective-sample-size factor so p is honest on autocorrelated series.

  #46  keyness — Dunning G² and Hardie Log-Ratio+CI already exist, but keyness is tested
       across thousands of lemmas with no multiple-testing control (F20/F43). Exposed the
       same BH-FDR the trend path uses, so keyness reports q, not a raw p<0.001 claim.

  #43  drift CI — the shipped bootstrap is K=12 percentile, ~82% coverage (F11). Added the
       BCa interval (bias-correction + acceleration, Efron 1987), which is the standard
       small-sample correction; the caller still needs K≥100 replicates for it to matter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# ─────────────────────────────────────────────────────────────────────────────
# #44 — change-point: Pettitt (1979) + optional exact permutation null
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ChangePoint:
    index: int | None      # position in the series (0-based) of the change, or None
    label: object | None   # the series label (e.g. year) at that position, or None
    stat: float            # Pettitt K statistic
    p_value: float         # significance (asymptotic, or permutation if n_perm>0)
    significant: bool      # p_value <= alpha


def _pettitt_k(vals) -> tuple[int, float]:
    """(argmax index, K) for Pettitt's statistic on `vals`.

    U_t = Σ_{i≤t} Σ_{j>t} sgn(x_i − x_j);  K = max_t |U_t|;  change point = argmax_t |U_t|.
    O(n²) via the running form U_t = U_{t−1} + Σ_j sgn(x_t − x_j). n ≤ ~31 here."""
    n = len(vals)
    # v[i] = Σ_j sgn(x_i − x_j) over ALL j (the Mann–Whitney rank contribution of i)
    v = [0] * n
    for i in range(n):
        xi = vals[i]
        s = 0
        for j in range(n):
            d = xi - vals[j]
            s += (d > 0) - (d < 0)
        v[i] = s
    best_t, best_abs, u = -1, -1.0, 0
    for t in range(n - 1):          # candidate split after position t (0..n-2)
        u += v[t]
        if abs(u) > best_abs:
            best_abs, best_t = abs(u), t
    return best_t, float(best_abs)


def change_point(series: list[tuple[object, float]], alpha: float = 0.05,
                 n_perm: int = 0, seed: int = 0) -> ChangePoint:
    """Pettitt single-change-point test on a labelled series [(label, value), …].

    Returns a ChangePoint; the change is reported at the position AFTER which the
    location shifts. With n_perm=0 the p-value is Pettitt's asymptotic approximation
    p ≈ 2·exp(−6K²/(n³+n²)); with n_perm>0 it is the exact permutation p (fraction of
    label-shuffled series whose K ≥ observed), which is preferable for the short series
    here. `significant=False` ⇒ report "χωρίς σαφές σημείο καμπής"."""
    labels = [s[0] for s in series]
    vals = [float(s[1]) for s in series]
    n = len(vals)
    if n < 4:
        return ChangePoint(None, None, 0.0, 1.0, False)

    t, k = _pettitt_k(vals)

    if n_perm and n_perm > 0:
        import random as _random
        rng = _random.Random(seed)
        pool = list(vals)
        ge = 1  # +1 (include observed) — standard permutation-p smoothing
        for _ in range(n_perm):
            rng.shuffle(pool)
            if _pettitt_k(pool)[1] >= k:
                ge += 1
        p = ge / (n_perm + 1)
    else:
        p = min(1.0, 2.0 * math.exp(-6.0 * k * k / (n ** 3 + n ** 2)))

    sig = p <= alpha
    return ChangePoint(
        index=t if sig else None,
        label=labels[t] if sig else None,
        stat=k, p_value=round(float(p), 4), significant=sig,
    )


# ─────────────────────────────────────────────────────────────────────────────
# #45 — trend: Theil–Sen slope + Mann–Kendall with the Hamed–Rao correction
# ─────────────────────────────────────────────────────────────────────────────

def theil_sen(years: list[float], vals: list[float]) -> float:
    """Median of pairwise slopes — robust to a single outlier year, unlike OLS."""
    slopes: list[float] = []
    n = len(years)
    for i in range(n - 1):
        for j in range(i + 1, n):
            dt = years[j] - years[i]
            if dt:
                slopes.append((vals[j] - vals[i]) / dt)
    if not slopes:
        return 0.0
    slopes.sort()
    m = len(slopes)
    return slopes[m // 2] if m % 2 else 0.5 * (slopes[m // 2 - 1] + slopes[m // 2])


def _mk_s_and_var(x) -> tuple[int, float]:
    import numpy as np
    n = len(x)
    x = np.asarray(x, dtype=float)
    s = 0
    for k in range(n - 1):
        s += int(np.sign(x[k + 1:] - x[k]).sum())
    _, counts = np.unique(x, return_counts=True)
    var_s = (n * (n - 1) * (2 * n + 5)
             - float(np.sum(counts * (counts - 1) * (2 * counts + 5)))) / 18.0
    return s, var_s


@dataclass
class Trend:
    slope: float
    tau: float
    s: int
    p_value: float          # Hamed–Rao corrected (autocorrelation-robust)
    p_naive: float          # uncorrected MK, for comparison
    variance_inflation: float  # var_s_corrected / var_s (≥1 under positive autocorr)


def mann_kendall(vals: list[float], hamed_rao: bool = True) -> Trend:
    """Two-sided Mann–Kendall trend test with the Hamed & Rao (1998) autocorrelation
    correction. Annual lexical series are serially correlated; without the correction
    MK's variance is understated and p is anti-conservative (F10/F39). The correction
    detrends by the Theil–Sen slope, ranks the residuals, and inflates var(S) by the
    effective-sample-size factor from the rank autocorrelations."""
    import numpy as np
    from scipy.stats import norm, rankdata

    n = len(vals)
    if n < 4:
        return Trend(0.0, 0.0, 0, 1.0, 1.0, 1.0)
    x = np.asarray(vals, dtype=float)
    s, var_s = _mk_s_and_var(x)

    def _p_from_var(var):
        if var <= 0:
            return 1.0
        if s > 0:
            z = (s - 1) / math.sqrt(var)
        elif s < 0:
            z = (s + 1) / math.sqrt(var)
        else:
            z = 0.0
        return min(1.0, float(2.0 * norm.sf(abs(z))))

    p_naive = _p_from_var(var_s)

    inflation = 1.0
    if hamed_rao:
        slope = theil_sen(list(range(n)), vals)
        detrended = x - slope * np.arange(n)
        ranks = rankdata(detrended)
        rbar = ranks.mean()
        denom = float(((ranks - rbar) ** 2).sum())
        # Significance filter (Hamed & Rao 1998): only autocorrelations that are
        # themselves distinguishable from zero enter the correction. Without it, the
        # sum of ~N(0,1/n) rank-autocorrelation noise across all lags swings the factor
        # far from 1 on a single finite iid series (it deflated to 0.36 in testing).
        # Under independence acf(k) ≈ N(0, 1/n); ±1.96/√n is the ~95% two-sided bound.
        crit = 1.96 / math.sqrt(n)
        sni = 0.0
        for k in range(1, n):
            num = float(((ranks[:n - k] - rbar) * (ranks[k:] - rbar)).sum())
            rho = num / denom if denom > 0 else 0.0
            if abs(rho) <= crit:
                continue  # insignificant → excluded
            sni += (n - k) * (n - k - 1) * (n - k - 2) * rho
        # effective-sample-size correction factor (Hamed & Rao 1998, eq. for n/n_s*)
        cf = 1.0 + (2.0 / (n * (n - 1) * (n - 2))) * sni if n > 2 else 1.0
        cf = max(cf, 1e-6)
        inflation = cf
        var_s = var_s * cf

    tau = s / (0.5 * n * (n - 1)) if n > 1 else 0.0
    return Trend(
        slope=theil_sen(list(range(n)), vals),
        tau=round(float(tau), 4), s=s,
        p_value=round(_p_from_var(var_s), 4),
        p_naive=round(p_naive, 4),
        variance_inflation=round(float(inflation), 3),
    )


# ─────────────────────────────────────────────────────────────────────────────
# #46 — keyness: Dunning G², Hardie Log-Ratio + CI, and BH-FDR across tests
# ─────────────────────────────────────────────────────────────────────────────

def dunning_g2(a: int, b: int, c: int, d: int) -> float:
    """Dunning (1993) log-likelihood G² for freq `a` in corpus 1 (size `c`) vs `b` in
    corpus 2 (size `d`). ~χ²₁ (>10.83 ↔ p<0.001). ≥0; 0 when a/c = b/d."""
    if a + b == 0:
        return 0.0
    e1 = c * (a + b) / (c + d)
    e2 = d * (a + b) / (c + d)
    g2 = 0.0
    if a > 0 and e1 > 0:
        g2 += a * math.log(a / e1)
    if b > 0 and e2 > 0:
        g2 += b * math.log(b / e2)
    return 2.0 * g2


def g2_p_value(g2: float) -> float:
    """Right-tail χ²₁ p-value for a G² statistic."""
    from scipy.stats import chi2
    return float(chi2.sf(g2, df=1))


def hardie_log_ratio(a: int, b: int, c: int, d: int) -> tuple[float, float, float]:
    """Hardie (2014) Log Ratio (effect size) + 95% CI: log₂ of (a/c)/(b/d). +1 = twice
    as common in corpus 1. CI from the delta-method variance of the log relative risk."""
    if a <= 0 or b <= 0 or c <= 0 or d <= 0:
        return 0.0, 0.0, 0.0
    lr = math.log2((a / c) / (b / d))
    var = 1.0 / a + 1.0 / b - 1.0 / c - 1.0 / d
    se = (math.sqrt(var) / math.log(2)) if var > 0 else 0.0
    return lr, lr - 1.96 * se, lr + 1.96 * se


def bh_fdr(pvals: dict, alpha: float = 0.05) -> tuple[dict, dict]:
    """Benjamini–Hochberg over {key: raw_p} → ({key: q}, {key: reject@alpha}). Monotone
    step-up. The same procedure the trend path uses, exposed for keyness (F20/F43)."""
    keys = list(pvals)
    m = len(keys)
    if m == 0:
        return {}, {}
    order = sorted(keys, key=lambda i: pvals[i])
    q: dict = {}
    prev = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        prev = min(prev, pvals[i] * m / rank)
        q[i] = min(prev, 1.0)
    reject = {i: q[i] <= alpha for i in keys}
    return q, reject


# ─────────────────────────────────────────────────────────────────────────────
# #43 — drift CI: BCa bootstrap interval (Efron 1987)
# ─────────────────────────────────────────────────────────────────────────────

def bca_interval(observed: float, replicates: list[float],
                 jackknife: list[float], alpha: float = 0.05) -> tuple[float, float]:
    """Bias-corrected & accelerated (BCa) bootstrap CI.

    Corrects the percentile interval for median-bias (z0, from the share of replicates
    below the observed estimate) and skew (acceleration `a`, from the jackknife). This
    is the standard small-sample fix the shipped K=12 percentile interval lacked (F11);
    it needs K≥~1000 replicates to be trustworthy — this function just computes the
    interval, the caller supplies the replicates and leave-one-out jackknife values."""
    import numpy as np
    from scipy.stats import norm

    reps = np.asarray(replicates, dtype=float)
    if reps.size == 0:
        return float("nan"), float("nan")
    # bias-correction z0
    frac = float(np.mean(reps < observed))
    frac = min(max(frac, 1.0 / (reps.size + 1)), 1.0 - 1.0 / (reps.size + 1))
    z0 = float(norm.ppf(frac))
    # acceleration from the jackknife
    jk = np.asarray(jackknife, dtype=float)
    if jk.size >= 2:
        jbar = jk.mean()
        diff = jbar - jk
        denom = 6.0 * (float((diff ** 2).sum()) ** 1.5)
        a = float((diff ** 3).sum()) / denom if denom != 0 else 0.0
    else:
        a = 0.0
    zl, zu = float(norm.ppf(alpha / 2)), float(norm.ppf(1 - alpha / 2))

    def _adj(z):
        denom = 1.0 - a * (z0 + z)
        return float(norm.cdf(z0 + (z0 + z) / denom)) if denom != 0 else float(norm.cdf(z0 + z))

    lo = float(np.percentile(reps, 100 * _adj(zl)))
    hi = float(np.percentile(reps, 100 * _adj(zu)))
    return lo, hi
