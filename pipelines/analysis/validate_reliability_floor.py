"""Offline calibration of the #51 per-era frequency floor.

`embedding_ops.is_reliable(count, floor)` needs a defensible `floor`. This measures it:
train a no-change control (two disjoint halves of one year → the noise floor) and a real
cross-year pair with the identical setup, then bin per-lemma drift by the lemma's per-era
count and compute, per band, the SNR = median(real drift) / median(control drift). Rare
words sit at SNR ≈ 1 — their drift is indistinguishable from estimation noise, so their
neighbour lists / drift should be suppressed. The recommended floor is the smallest count
band where SNR rises clearly above 1. Offline; reuses the harness primitives.

Usage (minutes; set PYTHONIOENCODING=utf-8):
    python pipelines/analysis/validate_reliability_floor.py --corpus news \
        --control-year 2019 --from 2011 --to 2024 --sample 60000
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from drift_signal_test import reservoir_sample, disjoint_halves, train, RESTRICT_VOCAB  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ingest"))
from ingest_diachronic import _align, _cos_dist, existing_slices  # noqa: E402

# Count bands (per-era occurrence count of a lemma). MIN_KEEP is low on purpose — the
# whole point is to include rare words and show they are noise.
MIN_KEEP = 5
BANDS = [(5, 20), (20, 50), (50, 100), (100, 300), (300, 1000), (1000, 10 ** 9)]


def drift_with_counts(wv_a, wv_b) -> list[tuple[float, int]]:
    """(cosine drift, min per-model count) for each shared word, no count floor."""
    aligned, key_index = _align(wv_a, wv_b)
    if aligned is None:
        return []
    a_top = set(wv_a.index_to_key[:RESTRICT_VOCAB])
    b_top = set(wv_b.index_to_key[:RESTRICT_VOCAB])
    out = []
    for w in a_top & b_top:
        ca = wv_a.get_vecattr(w, "count")
        cb = wv_b.get_vecattr(w, "count")
        if min(ca, cb) < MIN_KEEP:
            continue
        out.append((_cos_dist(wv_a[w], aligned[key_index[w]]), int(min(ca, cb))))
    return out


def _median(xs):
    import numpy as np
    return float(np.median(xs)) if xs else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser(description="Calibrate the #51 per-era frequency floor.")
    ap.add_argument("--corpus", default="news")
    ap.add_argument("--control-year", type=int)
    ap.add_argument("--from", dest="y_from", type=int)
    ap.add_argument("--to", dest="y_to", type=int)
    ap.add_argument("--sample", type=int, default=60000)
    ap.add_argument("--out", default=os.path.join("data", "analysis"))
    args = ap.parse_args()

    slices = dict(existing_slices(args.corpus))
    if not slices:
        sys.exit(f"No materialized slices for corpus={args.corpus}.")
    years = sorted(slices)

    def linecount(p):
        with open(p, encoding="utf-8") as fh:
            return sum(1 for _ in fh)

    cy = args.control_year or max(years, key=lambda y: linecount(slices[y]))
    yf = args.y_from or years[0]
    yt = args.y_to or years[-1]
    for y in (cy, yf, yt):
        if y not in slices:
            sys.exit(f"year {y} not in {years}")

    print(f"training control ({cy} halves) + signal ({yf}→{yt}) @ {args.sample} lines …",
          file=sys.stderr)
    t0 = time.time()
    rng = random.Random(4242)
    a, b = disjoint_halves(slices[cy], args.sample, rng)
    control = drift_with_counts(train(a, seed=1, workers=1), train(b, seed=2, workers=1))
    sig = drift_with_counts(
        train(reservoir_sample(slices[yf], args.sample, random.Random(11)), seed=3, workers=1),
        train(reservoir_sample(slices[yt], args.sample, random.Random(12)), seed=4, workers=1),
    )

    def band_of(c):
        for lo, hi in BANDS:
            if lo <= c < hi:
                return (lo, hi)
        return None

    rows = []
    floor = None
    for lo, hi in BANDS:
        cd = [d for d, c in control if lo <= c < hi]
        sd = [d for d, c in sig if lo <= c < hi]
        cm, sm = _median(cd), _median(sd)
        snr = (sm / cm) if cm and cm == cm else None
        rows.append({"band": f"{lo}-{hi if hi < 10 ** 9 else '∞'}", "lo": lo,
                     "n_control": len(cd), "n_signal": len(sd),
                     "control_median": round(cm, 4), "signal_median": round(sm, 4),
                     "snr": round(snr, 3) if snr else None})
        if floor is None and snr and snr >= 1.5:
            floor = lo

    report = {"corpus": args.corpus, "control_year": cy, "pair": [yf, yt],
              "sample": args.sample, "bands": rows, "recommended_floor": floor,
              "elapsed_sec": round(time.time() - t0, 1)}
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, f"reliability_floor_{args.corpus}.json"), "w",
              encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    print("\n" + "=" * 72)
    print(f"RELIABILITY FLOOR (#51) — {args.corpus} {yf}→{yt}  ({report['elapsed_sec']}s)")
    print("=" * 72)
    print(f"  {'count band':>12} {'n':>6} {'noise med':>10} {'real med':>9} {'SNR':>6}")
    for r in rows:
        print(f"  {r['band']:>12} {r['n_signal']:>6} {r['control_median']:>10} "
              f"{r['signal_median']:>9} {str(r['snr']):>6}")
    print(f"\n  Recommended per-era floor: count ≥ {report['recommended_floor']} "
          f"(smallest band with SNR ≥ 1.5).")
    print("  Below it, drift ≈ the no-change noise — neighbour lists there are noise")
    print("  presented as fact and should be suppressed/flagged (#51).")


if __name__ == "__main__":
    main()
