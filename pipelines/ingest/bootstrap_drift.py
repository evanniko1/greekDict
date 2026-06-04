"""Layer C significance (#36) — bootstrap confidence intervals on semantic drift.

The single-model drift score (`diachronic_drift.drift_score`) is a point estimate:
it can't say whether a word's apparent movement is real or just the noise of
estimating a vector from finite, independently-trained slices (Dubossarsky et al.
2017 — rare words look like big movers purely from sampling instability). This
script answers "real vs. noise" by BOOTSTRAPPING over slice models:

  • Resample the two anchor slices' sentences WITH REPLACEMENT K times and retrain
    a word2vec model on each resample. This regenerates the dominant noise source —
    vector estimation under finite, resampled data.
  • REAL drift sample k = cosine distance first_k ↔ last_k (Procrustes-aligned),
    one per bootstrap pair → a per-lemma distribution → a 95% CI (2.5/97.5 pct).
  • CONTROL (null) drift = distance between two bootstrap models of the SAME first
    slice (first_i ↔ first_j). No time elapses between them, so any distance is
    pure estimation noise. We reuse the K already-trained first-slice models for
    this — no extra training. This is the Dubossarsky "no-change" control.
  • A lemma's drift is SIGNIFICANT when its real-drift CI lower bound clears the
    control-noise CI upper bound (real_pct2.5 > ctrl_pct97.5): the movement is
    larger than this word's own estimation noise at the same frequency.

Idempotent: only UPDATEs drift_ci_low / drift_ci_high / drift_significant on rows
already in `diachronic_drift` for the chosen corpus (built by ingest_diachronic).
It does NOT retrain the whole trajectory — just the two anchor slices, K times.

Compute note: news 2024 is ~1M sentences. We cap each bootstrap resample at
--cap sentences (default 250k) so the big slice stays tractable; a smaller
effective sample only WIDENS the CI (conservative), never narrows it. K is the
dominant cost: each resample retrains a word2vec model, so --k 100 is ≈8× the
legacy --k 12 — an overnight job across both axes. Run it stopped/idle.

Requires gensim, scipy, numpy.

Example:
    python pipelines/ingest/bootstrap_drift.py --corpus parliament --k 100
    python pipelines/ingest/bootstrap_drift.py --corpus news --k 100 --cap 250000
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipelines", "ingest"))
from ingest_kaikki import init_db  # noqa: E402
from ingest_diachronic import (  # noqa: E402
    _train, _align, _cos_dist, PROCESSED, _pool_members, _adaptive_members,
)
from normalize_greek import normalize_keep_accents  # noqa: E402


def _bh_fdr(p_by_id: dict[int, float], alpha: float = 0.05):
    """Benjamini–Hochberg FDR over {lemma_id: raw_p}. Returns ({id: q}, {id: reject}).
    Thousands of lemmas are tested for drift at once, so an uncorrected per-lemma
    flag admits ~α·m false movers; BH bounds the expected false-discovery proportion
    among the flagged set instead. q-values are the monotone step-up adjusted p's."""
    ids = list(p_by_id)
    m = len(ids)
    if m == 0:
        return {}, {}
    order = sorted(ids, key=lambda i: p_by_id[i])
    q: dict[int, float] = {}
    prev = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        prev = min(prev, p_by_id[i] * m / rank)
        q[i] = min(prev, 1.0)
    reject = {i: q[i] <= alpha for i in ids}
    return q, reject


def _percentile_ci(replicates: list[float], alpha: float = 0.05):
    """Plain percentile bootstrap CI (2.5/97.5). Honest about its limit: the cut-points
    are only as smooth as the resample count K, so the interval is coarse below K≈100
    (#43) — we do NOT dress it up as BCa, whose acceleration term would need a data-level
    jackknife we can't afford here. Returns (lo, hi), or None for <2 replicates."""
    import numpy as np

    if len(replicates) < 2:
        return None
    arr = np.asarray(replicates, dtype=float)
    return (round(float(np.percentile(arr, 100 * alpha / 2)), 4),
            round(float(np.percentile(arr, 100 * (1 - alpha / 2))), 4))


def _resample_to_tempfile(lines: list[str], cap: int, tmp_dir: str) -> str:
    """Write a bootstrap resample (sample WITH REPLACEMENT) of `lines` to a temp
    file and return its path. Caller deletes it. Capped at `cap` sentences so a
    huge slice (news 2024 ≈ 1M) stays tractable — a smaller draw only widens CIs."""
    k = min(len(lines), cap)
    draw = random.choices(lines, k=k)  # with replacement = bootstrap
    fd, path = tempfile.mkstemp(suffix=".txt", dir=tmp_dir)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.writelines(draw)
    return path


def _train_bootstrap(lines: list[str], cap: int, tmp_dir: str,
                     vector_size: int, window: int, min_count: int, epochs: int):
    """One bootstrap model: resample → train → return wv. Temp file cleaned up."""
    path = _resample_to_tempfile(lines, cap, tmp_dir)
    try:
        return _train(path, vector_size, window, min_count, epochs).wv
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _drift_per_lemma(base_wv, other_wv, lemma_norm: dict[int, str]) -> dict[int, float]:
    """Aligned cosine-distance of every tracked lemma between two slice models.
    base_wv defines the frame; other_wv is Procrustes-rotated into it."""
    aligned, key_index = _align(base_wv, other_wv)
    out: dict[int, float] = {}
    if aligned is None:
        return out
    for lid, nlemma in lemma_norm.items():
        if nlemma in base_wv and nlemma in key_index:
            out[lid] = _cos_dist(base_wv[nlemma], aligned[key_index[nlemma]])
    return out


def _read_anchor_lines(slice_dir: str, anchor_y: int, all_years: list[int],
                       pool_window: int, read_cap: int,
                       pool_adaptive: bool = False, pool_target: int = 200_000,
                       line_count: dict[int, int] | None = None) -> list[str]:
    """Lines for an anchor slice. With pool_window>0, pool the ±window band (#37) so the
    CI matches the pooled point estimate; with pool_adaptive the band is sized per the
    same target as ingest_diachronic (#49) — anchors are the dense endpoints, so this
    usually collapses to a small/zero window. Uniform-reservoir down to read_cap to
    bound memory. The per-bootstrap resample then draws WITH REPLACEMENT from these lines."""
    if pool_window <= 0:
        members = [anchor_y]
    elif pool_adaptive:
        members = _adaptive_members(anchor_y, all_years, line_count or {}, pool_target, pool_window)
    else:
        members = _pool_members(anchor_y, all_years, pool_window)
    paths = [os.path.join(slice_dir, f"{y}.txt") for y in members]
    reservoir: list[str] = []
    n = 0
    for p in paths:
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                n += 1
                if read_cap <= 0 or len(reservoir) < read_cap:
                    reservoir.append(line)
                else:
                    j = random.randint(0, n - 1)
                    if j < read_cap:
                        reservoir[j] = line
    return reservoir


def bootstrap_drift(
    db_path: str,
    corpus: str,
    k: int = 100,
    cap: int = 250_000,
    vector_size: int = 100,
    window: int = 5,
    min_count: int = 10,
    epochs: int = 5,
    seed: int = 0,
    pool_window: int = 0,
    pool_cap: int = 500_000,
    pool_adaptive: bool = False,
    pool_target: int = 200_000,
) -> dict:
    import numpy as np

    import sqlite3

    random.seed(seed)
    conn = init_db(db_path)
    conn.row_factory = sqlite3.Row  # dict-style row access below

    # Forward-compat columns (schema.sql is source of truth; guard for old DBs).
    cols = {r[1] for r in conn.execute("PRAGMA table_info(diachronic_drift)")}
    for col in ("drift_ci_lo", "drift_ci_hi"):
        if col not in cols:
            conn.execute(f"ALTER TABLE diachronic_drift ADD COLUMN {col} REAL")
    if "drift_significant" not in cols:
        conn.execute("ALTER TABLE diachronic_drift ADD COLUMN drift_significant INTEGER")
    if "drift_q" not in cols:  # BH-FDR adjusted p-value (#2)
        conn.execute("ALTER TABLE diachronic_drift ADD COLUMN drift_q REAL")
    if "drift_score_boot" not in cols:  # #50: bootstrap-mean point estimate
        conn.execute("ALTER TABLE diachronic_drift ADD COLUMN drift_score_boot REAL")

    anchors = conn.execute(
        "SELECT DISTINCT first_year, last_year FROM diachronic_drift WHERE corpus=?",
        (corpus,),
    ).fetchall()
    if not anchors:
        conn.close()
        sys.exit(f"No diachronic_drift rows for corpus={corpus}; run ingest_diachronic first.")
    first_y, last_y = anchors[0]["first_year"], anchors[0]["last_year"]
    if first_y == last_y:
        conn.close()
        sys.exit(f"corpus={corpus} has a single anchor slice; drift CIs need two.")

    # Only lemmas that already have a drift row get CIs. (The displayed point estimate
    # is the bootstrap mean computed below, #50, so we just need the tracked id set.)
    tracked = {r["lemma_id"] for r in conn.execute(
        "SELECT lemma_id FROM diachronic_drift WHERE corpus=?", (corpus,))}
    # CRITICAL (#1): key on the ACCENT-PRESERVING form, exactly like ingest_diachronic —
    # the bootstrap word2vec models are trained on accent-preserving slices, so the
    # accent-FOLDED normalized_lemma ("νομοσ") would miss every accented wv key
    # ("νόμοσ") and silently drop ~94% of lemmas from the CI/significance pass.
    lemma_norm = {lid: normalize_keep_accents(lemma)
                  for lid, lemma in conn.execute("SELECT id, lemma FROM lemmas")
                  if lid in tracked}

    slice_dir = os.path.join(PROCESSED, corpus)
    first_path = os.path.join(slice_dir, f"{first_y}.txt")
    last_path = os.path.join(slice_dir, f"{last_y}.txt")
    for p in (first_path, last_path):
        if not os.path.exists(p):
            conn.close()
            sys.exit(f"Missing anchor slice file {p} — materialize slices first.")

    # All materialized years for this corpus (for pooling the anchor bands, #37).
    all_years = sorted(
        int(n[:-4]) for n in os.listdir(slice_dir)
        if n.endswith(".txt") and n[:-4].isdigit()
    )
    # Per-year line counts only when adaptive pooling needs to size the anchor band (#49).
    line_count: dict[int, int] = {}
    if pool_window > 0 and pool_adaptive:
        for y in all_years:
            p = os.path.join(slice_dir, f"{y}.txt")
            if os.path.exists(p):
                with open(p, encoding="utf-8") as fh:
                    line_count[y] = sum(1 for _ in fh)

    tmp_dir = os.path.join(slice_dir, "_bootstrap_tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    pool_note = (f" pool={'adaptive≤±' if pool_adaptive else '±'}{pool_window}yr"
                 if pool_window > 0 else "")
    print(f"Bootstrap drift CIs: corpus={corpus} anchors={first_y}↔{last_y} "
          f"K={k} cap={cap}{pool_note}", file=sys.stderr)

    def _anchor_lines(anchor_y):
        return _read_anchor_lines(slice_dir, anchor_y, all_years, pool_window, pool_cap,
                                  pool_adaptive=pool_adaptive, pool_target=pool_target,
                                  line_count=line_count)

    # ── train K bootstrap models of the FIRST slice; keep them (reused as the
    #    control null via first_i↔first_j pairs — no extra training). ──
    first_lines = _anchor_lines(first_y)
    first_models = []
    for i in range(k):
        wv = _train_bootstrap(first_lines, cap, tmp_dir, vector_size, window, min_count, epochs)
        first_models.append(wv)
        print(f"  · first[{i+1}/{k}] vocab {len(wv.index_to_key)}", file=sys.stderr)
    del first_lines

    # ── REAL drift: each last_k aligned to its paired first_k; stream (discard). ──
    real: dict[int, list[float]] = {lid: [] for lid in lemma_norm}
    last_lines = _anchor_lines(last_y)
    for i in range(k):
        last_wv = _train_bootstrap(last_lines, cap, tmp_dir, vector_size, window, min_count, epochs)
        d = _drift_per_lemma(first_models[i], last_wv, lemma_norm)
        for lid, val in d.items():
            real[lid].append(val)
        print(f"  · last[{i+1}/{k}] vocab {len(last_wv.index_to_key)} "
              f"(real pairs so far {i+1})", file=sys.stderr)
        del last_wv
    del last_lines

    # ── CONTROL null: first_i ↔ first_j pairs (no time change = pure noise). ──
    pairs = [(i, j) for i in range(k) for j in range(i + 1, k)]
    random.shuffle(pairs)
    pairs = pairs[: max(k, 1)]  # ~K control samples is plenty alongside K real
    control: dict[int, list[float]] = {lid: [] for lid in lemma_norm}
    for n, (i, j) in enumerate(pairs):
        d = _drift_per_lemma(first_models[i], first_models[j], lemma_norm)
        for lid, val in d.items():
            control[lid].append(val)
        print(f"  · control[{n+1}/{len(pairs)}] first[{i}]↔first[{j}]", file=sys.stderr)

    # ── per-lemma CI + significance test, then BH-FDR (#2). ──
    # Point estimate = bootstrap mean (#50; stable across word2vec's stochasticity).
    # CI = percentile of the real samples (#43; coarse below K≈100). Significance = a
    # one-sided p that real drift exceeds this lemma's OWN control-noise distribution
    # (z = (mean_real − mean_ctrl)/sd_ctrl), fed to BH-FDR. Control null unchanged.
    from scipy.stats import norm as _norm
    MIN_SAMPLES = max(4, k // 2)
    ci_by_id: dict[int, tuple[float, float]] = {}
    p_by_id: dict[int, float] = {}
    boot_mean_by_id: dict[int, float] = {}
    for lid in lemma_norm:
        rs = real[lid]
        if len(rs) < MIN_SAMPLES:
            continue
        boot_mean = float(np.mean(rs))
        boot_mean_by_id[lid] = round(boot_mean, 4)
        ci_by_id[lid] = _percentile_ci(rs)
        cs = control[lid]
        if len(cs) >= MIN_SAMPLES:
            mu_c = float(np.mean(cs))
            sd_c = float(np.std(cs, ddof=1))
            if sd_c > 1e-9:
                z = (boot_mean - mu_c) / sd_c
                p_by_id[lid] = float(_norm.sf(z))  # one-sided: real > control noise

    # Pass 2: BH-FDR across every lemma that got a p, then UPDATE in place.
    q_by_id, sig_by_id = _bh_fdr(p_by_id, alpha=0.05)
    updated = sig_count = 0
    for lid, (lo, hi) in ci_by_id.items():
        if lid in q_by_id:
            significant = 1 if sig_by_id[lid] else 0
            q_val = round(q_by_id[lid], 4)
            sig_count += significant
        else:
            significant, q_val = None, None
        conn.execute(
            "UPDATE diachronic_drift SET drift_ci_lo=?, drift_ci_hi=?, "
            "drift_significant=?, drift_q=?, drift_score_boot=? WHERE lemma_id=? AND corpus=?",
            (lo, hi, significant, q_val, boot_mean_by_id.get(lid), lid, corpus),
        )
        updated += 1

    conn.commit()
    conn.close()
    # best-effort temp cleanup
    try:
        for f in os.listdir(tmp_dir):
            os.remove(os.path.join(tmp_dir, f))
        os.rmdir(tmp_dir)
    except OSError:
        pass

    return {
        "corpus": corpus, "first_year": first_y, "last_year": last_y,
        "k": k, "cap": cap, "pool_window": pool_window, "control_pairs": len(pairs),
        "lemmas_updated": updated, "significant": sig_count,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Bootstrap CIs + significance on diachronic drift (#36).")
    ap.add_argument("--db", default="data/db/lexorama.sqlite")
    ap.add_argument("--corpus", required=True, help="parliament | news")
    ap.add_argument("--k", type=int, default=100,
                    help="bootstrap resamples per anchor slice (≥100 for smooth percentile "
                         "cut-points; this is the dominant compute cost — see header)")
    ap.add_argument("--cap", type=int, default=250_000,
                    help="max sentences per bootstrap resample (caps the huge news slice)")
    ap.add_argument("--vector-size", type=int, default=100)
    ap.add_argument("--window", type=int, default=5)
    ap.add_argument("--min-count", type=int, default=10)
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--pool-window", type=int, default=0,
                    help="Pool a ±N-year band around each anchor (#37) so the CI matches a "
                         "pooled ingest_diachronic point estimate. 0 = single-year anchors.")
    ap.add_argument("--pool-cap", type=int, default=500_000,
                    help="Max lines read per pooled anchor band (reservoir); bounds memory.")
    ap.add_argument("--pool-adaptive", action="store_true",
                    help="Size each anchor's pooled band adaptively (#49), matching an "
                         "ingest_diachronic --pool-adaptive run. Treats --pool-window as the MAX.")
    ap.add_argument("--pool-target", type=int, default=200_000,
                    help="Target lines per anchor band for --pool-adaptive.")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        sys.exit(f"DB not found: {args.db}")

    import json
    print(json.dumps(
        bootstrap_drift(
            args.db, args.corpus, k=args.k, cap=args.cap,
            vector_size=args.vector_size, window=args.window,
            min_count=args.min_count, epochs=args.epochs, seed=args.seed,
            pool_window=args.pool_window, pool_cap=args.pool_cap,
            pool_adaptive=args.pool_adaptive, pool_target=args.pool_target,
        ),
        indent=2, ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
