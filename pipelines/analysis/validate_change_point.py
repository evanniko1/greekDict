"""Offline null-validation of the #44 change-point detector.

The shipped detector (`ingest_diachronic.change_point_year`) is argmax of the steepest
trajectory step with a robust-z gate; the audit found it collapses onto a single
artefactual spike (82.6% of news words → change-point 2016, the first slice after a
three-year corpus gap; F5/F9). The replacement (`estimators.change_point`, Pettitt 1979
+ optional permutation null) must clear the obvious bar the old one failed: on a
NO-CHANGE trajectory it must almost never report a change point.

We build that no-change trajectory empirically: draw K+1 disjoint equal-sized samples
of ONE year, train an independent word2vec on each, align each to the reference sample,
and read each lemma's distance-from-reference across the K trajectory points. No time
elapsed, so every point is pure estimation noise and the series is flat — any "change
point" is a false positive. We then run BOTH detectors on the identical per-lemma
series and report the false-positive rate of each. A correct detector sits near its
nominal α; the old one should fire far more often.

Usage (minutes, offline; set PYTHONIOENCODING=utf-8):
    python pipelines/analysis/validate_change_point.py --corpus news \
        --year 2019 --k 9 --sample 40000 --alpha 0.05 --n-perm 0
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from drift_signal_test import reservoir_sample, train, RESTRICT_VOCAB, MIN_MEASURE_COUNT  # noqa: E402
from estimators import change_point  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ingest"))
from ingest_diachronic import _align, _cos_dist, existing_slices, change_point_year  # noqa: E402


def disjoint_samples(path: str, k: int, n: int, rng: random.Random) -> list[list[str]]:
    """k disjoint samples of n lines each from one file (reservoir 2… then split)."""
    pool = reservoir_sample(path, k * n, rng)
    rng.shuffle(pool)
    return [pool[i * n:(i + 1) * n] for i in range(k)]


def build_no_change_trajectories(path: str, k: int, sample: int, seed: int):
    """Return {lemma: [distance-from-reference at each of k trajectory points]}.

    sample+1 disjoint draws of ONE year: draw 0 is the reference frame, draws 1..k are
    the trajectory. Every distance is between two independent models of the SAME year,
    so the series is flat noise by construction."""
    rng = random.Random(seed)
    chunks = disjoint_samples(path, k + 1, sample, rng)
    ref = train(chunks[0], seed=1000, workers=1)
    ref_top = set(ref.index_to_key[:RESTRICT_VOCAB])
    series: dict[str, list[float]] = {}
    for t in range(1, k + 1):
        wv = train(chunks[t], seed=1000 + t, workers=1)
        aligned, key_index = _align(ref, wv)  # rotate wv into ref's frame
        if aligned is None:
            continue
        shared = ref_top & set(wv.index_to_key[:RESTRICT_VOCAB])
        for w in shared:
            if ref.get_vecattr(w, "count") < MIN_MEASURE_COUNT:
                continue
            if wv.get_vecattr(w, "count") < MIN_MEASURE_COUNT:
                continue
            series.setdefault(w, []).append(_cos_dist(ref[w], aligned[key_index[w]]))
    # keep only lemmas present at every trajectory point (a complete series)
    return {w: v for w, v in series.items() if len(v) == k}


def main() -> None:
    ap = argparse.ArgumentParser(description="Null-validate the #44 change-point detector.")
    ap.add_argument("--corpus", default="news")
    ap.add_argument("--year", type=int, help="year to build the no-change trajectory from (default: largest slice)")
    ap.add_argument("--k", type=int, default=9, help="trajectory points (needs k+1 disjoint samples)")
    ap.add_argument("--sample", type=int, default=40000, help="lines per model")
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--n-perm", type=int, default=0, help="permutation reps for the new detector (0 = asymptotic)")
    ap.add_argument("--out", default=os.path.join("data", "analysis"))
    args = ap.parse_args()

    slices = dict(existing_slices(args.corpus))
    if not slices:
        sys.exit(f"No materialized slices for corpus={args.corpus}.")

    def linecount(p):
        with open(p, encoding="utf-8") as fh:
            return sum(1 for _ in fh)

    year = args.year or max(slices, key=lambda y: linecount(slices[y]))
    if year not in slices:
        sys.exit(f"year {year} not in {sorted(slices)}")

    print(f"building {args.k}-point no-change trajectories from {args.corpus} {year} "
          f"({args.sample} lines/model) …", file=sys.stderr)
    t0 = time.time()
    trajs = build_no_change_trajectories(slices[year], args.k, args.sample, seed=99)
    if not trajs:
        sys.exit("no complete trajectories built (year too small for k+1 samples?)")

    # Probe A — the flat no-change trajectory: is each detector calibrated on pure noise?
    # Probe B — the same trajectory with ONE spike injected mid-series, simulating a
    #   corpus-gap step (the F5/F9 mechanism: an independent-model discontinuity the old
    #   argmax deterministically latches onto). A location test (Pettitt) should resist a
    #   lone spike; the steepest-single-step argmax should not.
    new_fp = old_fp = 0
    new_spike = old_spike = 0
    labels = list(range(1, args.k + 1))
    spike_at = args.k // 2
    for w, dists in trajs.items():
        series = list(zip(labels, dists))
        if change_point(series, alpha=args.alpha, n_perm=args.n_perm).significant:
            new_fp += 1
        # old detector: prepend the reference (0.0) it expects, then read its own gate
        if change_point_year([(0, 0.0)] + series, min_z=2.0)[0] is not None:
            old_fp += 1

        spiked = list(dists)
        spiked[spike_at] += 0.30  # a lone gap-sized bump at one interior slice
        s_series = list(zip(labels, spiked))
        if change_point(s_series, alpha=args.alpha, n_perm=args.n_perm).significant:
            new_spike += 1
        if change_point_year([(0, 0.0)] + s_series, min_z=2.0)[0] is not None:
            old_spike += 1

    m = len(trajs)
    report = {
        "corpus": args.corpus, "year": year, "k": args.k, "sample": args.sample,
        "alpha": args.alpha, "n_perm": args.n_perm, "lemmas": m,
        "flat_no_change": {
            "new_detector_fp_rate": round(new_fp / m, 4),
            "old_detector_fp_rate": round(old_fp / m, 4),
        },
        "single_spike_injected": {
            "new_detector_fp_rate": round(new_spike / m, 4),
            "old_detector_fp_rate": round(old_spike / m, 4),
        },
        "elapsed_sec": round(time.time() - t0, 1),
    }
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, f"change_point_null_{args.corpus}.json"), "w",
              encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    fl, sp = report["flat_no_change"], report["single_spike_injected"]
    print("\n" + "=" * 68)
    print(f"CHANGE-POINT NULL VALIDATION — {args.corpus} {year}  ({report['elapsed_sec']}s)")
    print("=" * 68)
    print(f"  no-change trajectories tested: {m} lemmas × {args.k} points\n")
    print(f"  [A] FLAT no-change trajectory — false-positive rate (want ≈ {args.alpha*100:.0f}%):")
    print(f"      NEW (Pettitt)          {fl['new_detector_fp_rate']*100:5.1f}%")
    print(f"      OLD (argmax + robust-z){fl['old_detector_fp_rate']*100:5.1f}%")
    print(f"\n  [B] + one gap-sized spike injected mid-series (the F5/F9 mechanism):")
    print(f"      NEW (Pettitt)          {sp['new_detector_fp_rate']*100:5.1f}%   ← location test resists a lone spike")
    print(f"      OLD (argmax + robust-z){sp['old_detector_fp_rate']*100:5.1f}%   ← steepest-step latches onto it")
    print("\n  A correct detector stays near α on [A] and resists the artefact on [B].")
    print("  The [B] gap is how the shipped layer collapsed 82.6% of news words onto a")
    print("  single gap year (audit F5/F9).")


if __name__ == "__main__":
    main()
