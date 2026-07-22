"""Offline diagnostic: is the diachronic drift signal real, or estimator noise?

This is the harness that answers **BACKLOG D3** — "is drift/change-point worth the
8–10 h Tier B rebuild?" — WITHOUT the rebuild. It runs on the already-materialized
slices in data/processed/diachronic/, trains a handful of word2vec models, and asks
the one question the live pipeline never asked: does measured drift exceed the noise
floor of the estimator itself?

Three probes, cheapest first:

  1. REPRODUCIBILITY (audit F44/F50). Train the SAME slice twice. With workers=1 and a
     fixed seed the two models must be near-identical (drift ≈ 0). The production
     pipeline trains with workers=os.cpu_count() and no seed, which is nondeterministic
     even with a seed set — this probe quantifies how much apparent "drift" that alone
     manufactures. If the workers>1 floor is comparable to real drift, every displayed
     drift number is partly training noise.

  2. NO-CHANGE CONTROL (audit F7; Dubossarsky et al. 2017 "Outta Control"). Split ONE
     year's corpus into two disjoint equal-sized halves, train a model on each, align,
     and measure per-lemma cosine "drift". No time elapsed, so this drift is pure
     estimation noise. Repeated K times, it is the NOISE FLOOR — the distribution any
     real signal must clear to be believed.

  3. SIGNAL TEST (audit F7/F12). For a real pair of years, measure per-lemma drift with
     the IDENTICAL setup (same sample size, same alignment), so the only difference from
     the control is elapsed time. Compare against the noise floor:
       · SNR   = median(real drift) / median(control drift). ≈1 ⇒ no signal.
       · signal-bearing fraction = share of lemmas whose real drift exceeds the control
         95th percentile. The audit's claim was ~96% noise ⇒ expect a small fraction.

All comparisons use EQUAL-SIZED samples (fairness: a smaller corpus yields noisier
vectors, Antoniak & Mimno 2018), reuse the production alignment (`_align`) so the
diagnostic is faithful, and are fully offline — nothing is written to the DB or served.

Usage (the user runs this; it is minutes, not the 8–10 h rebuild):
    python pipelines/analysis/drift_signal_test.py --corpus news \
        --control-year 2019 --pairs 2011:2024,2016:2024 \
        --sample 150000 --reps 5 --workers 1

Output: a JSON + printed summary under data/analysis/. Set PYTHONIOENCODING=utf-8.
Determinism note: gensim is bit-reproducible only with workers=1 AND PYTHONHASHSEED set;
the harness forces workers=1 for probes 2/3 and reports the workers>1 floor in probe 1.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ingest"))
# Reuse the PRODUCTION alignment + cosine so the diagnostic measures the same thing the
# pipeline ships — not a re-implementation that could differ (audit faithfulness).
from ingest_diachronic import _align, _cos_dist, existing_slices  # noqa: E402

# Match the production training hyperparameters (ingest_diachronic defaults) so the
# noise floor characterises the estimator as actually deployed.
VEC_SIZE = 100
WINDOW = 5
MIN_COUNT = 10
EPOCHS = 5
# Measure drift only on the shared high-frequency core. Rare-word vectors are noise
# even in a single model; the pipeline itself gates neighbours at count>=50 and
# restricts overlap to the top 10k. We do the same so the floor is not dominated by
# words no honest system would report on.
RESTRICT_VOCAB = 10000
MIN_MEASURE_COUNT = 50


def reservoir_sample(path: str, n: int, rng: random.Random) -> list[str]:
    """Uniform sample of `n` lines from `path`, memory-bounded to O(n) (files reach
    ~220 MB). Deterministic given `rng`."""
    out: list[str] = []
    i = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            i += 1
            if len(out) < n:
                out.append(line)
            else:
                j = rng.randint(0, i - 1)
                if j < n:
                    out[j] = line
    return out


def disjoint_halves(path: str, n: int, rng: random.Random) -> tuple[list[str], list[str]]:
    """Two DISJOINT samples of `n` lines each from one file (for the no-change control):
    reservoir-sample 2n, shuffle, split. Needs the slice to have >= 2n lines."""
    pool = reservoir_sample(path, 2 * n, rng)
    rng.shuffle(pool)
    if len(pool) < 2 * n:
        half = len(pool) // 2
        return pool[:half], pool[half: 2 * half]
    return pool[:n], pool[n: 2 * n]


def train(lines: list[str], seed: int, workers: int):
    """Train a word2vec model on an in-memory sample, via a temp corpus_file (so we use
    gensim's fast file path, matching the production `_train`). Returns the KeyedVectors.
    workers=1 + seed is the reproducible setting; workers>1 is nondeterministic by design
    of gensim's parallel training, which is the point probe 1 measures."""
    from gensim.models import Word2Vec

    fd, tmp = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.writelines(lines)
        model = Word2Vec(
            corpus_file=tmp,
            vector_size=VEC_SIZE,
            window=WINDOW,
            min_count=MIN_COUNT,
            workers=workers,
            sg=0,
            epochs=EPOCHS,
            seed=seed,
        )
        return model.wv
    finally:
        os.unlink(tmp)


def measure_drift(wv_a, wv_b) -> dict[str, float]:
    """Per-lemma cosine drift between two models after aligning B into A's frame.
    Restricted to the shared frequent core (both models' top RESTRICT_VOCAB, count
    >= MIN_MEASURE_COUNT in both) so the distribution reflects measurable words."""
    # _align(base, other) rotates `other` into `base`'s frame and returns the rotated
    # matrix for `other`'s keys. Rotate B into A so both live in one frame before we
    # compare — the same orthogonal Procrustes the production pipeline uses.
    aligned, key_index = _align(wv_a, wv_b)
    if aligned is None:
        return {}
    a_top = set(wv_a.index_to_key[:RESTRICT_VOCAB])
    b_top = set(wv_b.index_to_key[:RESTRICT_VOCAB])
    shared = a_top & b_top
    drifts: dict[str, float] = {}
    for w in shared:
        if wv_a.get_vecattr(w, "count") < MIN_MEASURE_COUNT:
            continue
        if wv_b.get_vecattr(w, "count") < MIN_MEASURE_COUNT:
            continue
        drifts[w] = _cos_dist(wv_a[w], aligned[key_index[w]])
    return drifts


def _pct(values: list[float], p: float) -> float:
    import numpy as np
    return float(np.percentile(values, p)) if values else float("nan")


def _summary(values: list[float]) -> dict:
    import numpy as np
    if not values:
        return {"n": 0}
    a = np.asarray(values)
    return {
        "n": int(a.size),
        "mean": round(float(a.mean()), 4),
        "median": round(float(np.median(a)), 4),
        "p95": round(float(np.percentile(a, 95)), 4),
        "p99": round(float(np.percentile(a, 99)), 4),
        "max": round(float(a.max()), 4),
    }


def reproducibility_probe(path: str, sample: int, workers_hi: int) -> dict:
    """F44/F50: same data, same seed — how much drift is pure training nondeterminism?"""
    rng = random.Random(1001)
    lines = reservoir_sample(path, sample, rng)
    # Deterministic path: workers=1, identical seed → should be ~0.
    d1 = measure_drift(train(lines, seed=42, workers=1), train(lines, seed=42, workers=1))
    det = _summary(list(d1.values()))
    # Nondeterministic path: workers>1, identical seed → gensim is not reproducible.
    nd = _summary(list(measure_drift(
        train(lines, seed=42, workers=workers_hi),
        train(lines, seed=42, workers=workers_hi),
    ).values()))
    return {"deterministic_workers1": det, "nondeterministic_workers_hi": nd,
            "workers_hi": workers_hi}


def noise_floor(path: str, sample: int, reps: int) -> tuple[dict, list[float]]:
    """F7: disjoint same-year halves, K reps → the estimator noise floor."""
    pooled: list[float] = []
    for k in range(reps):
        rng = random.Random(2000 + k)
        a_lines, b_lines = disjoint_halves(path, sample, rng)
        wv_a = train(a_lines, seed=100 + k, workers=1)
        wv_b = train(b_lines, seed=500 + k, workers=1)
        pooled.extend(measure_drift(wv_a, wv_b).values())
    return _summary(pooled), pooled


def signal_test(path_a: str, path_b: str, sample: int) -> dict[str, float]:
    """Real cross-year drift with the control's identical setup."""
    rng = random.Random(7777)
    a_lines = reservoir_sample(path_a, sample, rng)
    b_lines = reservoir_sample(path_b, sample, rng)
    wv_a = train(a_lines, seed=11, workers=1)
    wv_b = train(b_lines, seed=22, workers=1)
    return measure_drift(wv_a, wv_b)


def main() -> None:
    ap = argparse.ArgumentParser(description="Offline drift signal-vs-noise diagnostic (D3).")
    ap.add_argument("--corpus", default="news", help="materialized corpus under data/processed/diachronic")
    ap.add_argument("--control-year", type=int, help="year for the no-change control (defaults to the largest slice)")
    ap.add_argument("--pairs", default="", help="comma list of real year pairs, e.g. 2011:2024,2016:2024")
    ap.add_argument("--sample", type=int, default=150_000, help="lines per model (equal-sized for fairness)")
    ap.add_argument("--reps", type=int, default=5, help="no-change-control repetitions")
    ap.add_argument("--workers-hi", type=int, default=os.cpu_count() or 8, help="worker count for the nondeterminism probe")
    ap.add_argument("--skip-repro", action="store_true", help="skip probe 1")
    ap.add_argument("--out", default=os.path.join("data", "analysis"))
    args = ap.parse_args()

    slices = dict(existing_slices(args.corpus))
    if not slices:
        sys.exit(f"No materialized slices for corpus={args.corpus} under data/processed/diachronic/.")
    years = sorted(slices)
    # Line counts to choose a control year with >= 2*sample lines.
    def linecount(p: str) -> int:
        with open(p, encoding="utf-8") as fh:
            return sum(1 for _ in fh)

    control_year = args.control_year
    if control_year is None:
        control_year = max(years, key=lambda y: linecount(slices[y]))
    if control_year not in slices:
        sys.exit(f"control-year {control_year} not in {years}")

    pairs: list[tuple[int, int]] = []
    if args.pairs:
        for tok in args.pairs.split(","):
            a, b = tok.split(":")
            pairs.append((int(a), int(b)))
    else:
        pairs = [(years[0], years[-1])]  # first vs last
    for a, b in pairs:
        for y in (a, b):
            if y not in slices:
                sys.exit(f"pair year {y} not in {years}")

    print(f"corpus={args.corpus}  years={years}", file=sys.stderr)
    print(f"control-year={control_year}  pairs={pairs}  sample={args.sample}  reps={args.reps}",
          file=sys.stderr)

    report: dict = {
        "corpus": args.corpus, "control_year": control_year, "pairs": pairs,
        "sample": args.sample, "reps": args.reps,
        "params": {"vector_size": VEC_SIZE, "window": WINDOW, "min_count": MIN_COUNT,
                   "epochs": EPOCHS, "restrict_vocab": RESTRICT_VOCAB,
                   "min_measure_count": MIN_MEASURE_COUNT},
    }
    t0 = time.time()

    if not args.skip_repro:
        print("probe 1/3: reproducibility …", file=sys.stderr)
        report["reproducibility"] = reproducibility_probe(slices[control_year], args.sample, args.workers_hi)

    print("probe 2/3: no-change control (noise floor) …", file=sys.stderr)
    floor_summary, floor_vals = noise_floor(slices[control_year], args.sample, args.reps)
    report["noise_floor"] = floor_summary
    floor_p95 = _pct(floor_vals, 95)

    print("probe 3/3: signal test …", file=sys.stderr)
    report["signals"] = []
    for a, b in pairs:
        drifts = signal_test(slices[a], slices[b], args.sample)
        vals = list(drifts.values())
        summ = _summary(vals)
        above = sum(1 for v in vals if v > floor_p95)
        snr_median = (summ.get("median", 0.0) / floor_summary["median"]) if floor_summary.get("median") else None
        # Top movers that clear the floor — the words a fixed pipeline would legitimately surface.
        movers = sorted(drifts.items(), key=lambda kv: kv[1], reverse=True)
        report["signals"].append({
            "pair": [a, b], "drift": summ,
            "signal_bearing_fraction": round(above / len(vals), 4) if vals else None,
            "snr_median_vs_noise": round(snr_median, 3) if snr_median else None,
            "top_movers": [{"lemma": w, "drift": round(d, 4)} for w, d in movers[:15]],
        })

    report["elapsed_sec"] = round(time.time() - t0, 1)

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, f"drift_signal_{args.corpus}.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    # ── human summary + a mechanical read of the D3 verdict ──
    print("\n" + "=" * 72)
    print(f"DRIFT SIGNAL DIAGNOSTIC — corpus={args.corpus}  ({report['elapsed_sec']}s)")
    print("=" * 72)
    if "reproducibility" in report:
        r = report["reproducibility"]
        d1, dh = r["deterministic_workers1"], r["nondeterministic_workers_hi"]
        print(f"\n[1] Reproducibility (same data, same seed) — mean / p95 / max drift:")
        print(f"    workers=1  {d1.get('mean')} / {d1.get('p95')} / {d1.get('max')}  (want ≈0 — determinism achievable)")
        print(f"    workers={r['workers_hi']:<2} {dh.get('mean')} / {dh.get('p95')} / {dh.get('max')}  ← nondeterminism floor (F44/F50)")
    f = report["noise_floor"]
    print(f"\n[2] No-change control / NOISE FLOOR (n={f['n']} word-measurements):")
    print(f"    median={f['median']}  p95={f['p95']}  p99={f['p99']}  mean={f['mean']}")
    print(f"\n[3] Real cross-year drift vs the floor:")
    for s in report["signals"]:
        print(f"    {s['pair'][0]}→{s['pair'][1]}: median={s['drift'].get('median')}  "
              f"SNR(median)={s['snr_median_vs_noise']}  "
              f"signal-bearing={None if s['signal_bearing_fraction'] is None else f'{s['signal_bearing_fraction']*100:.1f}%'}")
    print("\nRead: SNR≈1 and a tiny signal-bearing fraction ⇒ the layer is mostly estimator")
    print("noise (demote/remove). SNR clearly >1 with a substantial fraction clearing the")
    print("floor ⇒ real signal survives (fix + keep). This is the evidence for BACKLOG D3.")
    print(f"\nFull report: {out_path}")


if __name__ == "__main__":
    main()
