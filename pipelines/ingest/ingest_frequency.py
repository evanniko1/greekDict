"""Ingest corpus word-frequency into the `frequency` table.

Wiktionary carries no usage frequency, so we layer it from an external word
list: a plain-text file of "word<space>count" lines (the OpenSubtitles-derived
FrequencyWords list, github.com/hermitdave/FrequencyWords, works directly).

Frequency is a property of a LEMMA, but a corpus counts surface forms. So we
resolve each surface through `search_index` (which maps both lemmas and inflected
forms to a lemma_id) and SUM the counts onto the lemma — i.e. a lemma's frequency
is the total of all its inflected occurrences. We then compute a Zipf value
(log10 of count-per-billion, the standard van-Heuven/wordfreq scale) and a coarse
display band, and a dense rank among matched lemmas.

This pass is idempotent: it clears the table for the given --source and rewrites.

Download the Greek list first, e.g.:
    curl -L -o data/raw/el_freq.txt ^
      https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/el/el_50k.txt

Run:
    python pipelines/ingest/ingest_frequency.py --freq-file data/raw/el_freq.txt \
        --db data/db/lexorama.sqlite
"""

from __future__ import annotations

import argparse
import math
import os
import sys

# Reuse the shared DB bootstrap + attribution registry + Greek normalizer.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipelines", "ingest"))
from ingest_kaikki import init_db, record_attribution  # noqa: E402
from normalize_greek import normalize  # noqa: E402


# No real lemma owns this share of a corpus. Anything above it is a symptom of a
# lemma owning a surface it should not (bare endings, punctuation) — audit F4, where
# αισώπειος held 0.81% of the parliament corpus via the bare endings ο/ος/ων.
# The most frequent genuine Greek word (the article) sits near 3-4%, so 0.5% is a
# loose guard that only fires on artifacts of the ingest bug, not on real vocabulary.
MAX_LEMMA_SHARE = 0.005

# The Zipf scale (van Heuven et al. 2014) is log10(count per billion); real corpora
# top out near 7. Anything above this means the counts are inflated.
ZIPF_CEILING = 7.5


def zipf_band(zipf: float) -> str:
    """Coarse display band from a Zipf value (log10 of count per billion words)."""
    if zipf >= 5.0:
        return "very_common"
    if zipf >= 4.0:
        return "common"
    if zipf >= 3.0:
        return "moderate"
    if zipf >= 2.0:
        return "uncommon"
    return "rare"


def read_freq_file(path: str) -> tuple[list[tuple[str, int]], int]:
    """Parse "word count" lines. Returns (rows, total_count) where total_count is
    the sum of ALL counts in the list (the corpus size used to normalise Zipf)."""
    rows: list[tuple[str, int]] = []
    total = 0
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) < 2:
                continue
            word = parts[0]
            try:
                count = int(parts[1])
            except ValueError:
                continue
            if count <= 0:
                continue
            rows.append((word, count))
            total += count
    return rows, total


def ingest_frequency(freq_file: str, db_path: str, source: str) -> dict:
    conn = init_db(db_path)
    record_attribution(conn, source)

    rows, total = read_freq_file(freq_file)
    if total <= 0:
        conn.close()
        sys.exit(f"No usable frequency rows in {freq_file}.")

    # Map a normalized surface -> the DISTINCT lemma_id(s) it can resolve to.
    #
    # This must be a set, not a list (audit F2). search_index holds one row per
    # (surface, lemma, match kind), so a lemma commonly appears several times for the
    # same surface; crediting per-ROW rather than per-LEMMA added 907,217,101 tokens of
    # pure duplication (33.6% of everything credited) and pushed the total to 1,026% of
    # the corpus, with MAX(zipf)=8.615 — off the scale van Heuven et al. (2014) define.
    # Inflation was word-dependent (median 1.29x, max 21.09x), so it distorted band
    # assignment and the frequency rank that orders search results.
    surface_to_lemmas: dict[str, set[int]] = {}
    for norm, lemma_id in conn.execute("SELECT normalized_surface, lemma_id FROM search_index"):
        surface_to_lemmas.setdefault(norm, set()).add(lemma_id)

    lemma_count: dict[int, int] = {}
    matched_surfaces = 0
    for word, count in rows:
        ids = surface_to_lemmas.get(normalize(word))
        if not ids:
            continue
        matched_surfaces += 1
        # A genuinely ambiguous surface still credits each candidate lemma in full:
        # the count is an upper bound per lemma, which is why `frequency` is documented
        # as attributable-token count and not a disambiguated corpus frequency.
        for lid in ids:
            lemma_count[lid] = lemma_count.get(lid, 0) + count

    # Plausibility guard (F4). No single lemma accounts for a large share of a corpus;
    # when one appears to, it is owning a surface it should never have had (bare
    # endings, punctuation). Drop and report rather than publish an absurd Zipf.
    cap = MAX_LEMMA_SHARE * total
    implausible = {lid: c for lid, c in lemma_count.items() if c > cap}
    for lid in implausible:
        del lemma_count[lid]
    if implausible:
        print(f"  dropped {len(implausible)} lemma(s) exceeding {MAX_LEMMA_SHARE:.1%} "
              f"of the corpus (implausible surface ownership): "
              f"{sorted(implausible.values(), reverse=True)[:5]}", file=sys.stderr)

    # Dense rank by count desc (1 = most frequent), then persist Zipf + band.
    ranked = sorted(lemma_count.items(), key=lambda kv: kv[1], reverse=True)
    conn.execute("DELETE FROM frequency WHERE source = ?", (source,))
    for rank, (lid, count) in enumerate(ranked, start=1):
        zipf = math.log10(count) - math.log10(total) + 9.0
        conn.execute(
            "INSERT OR REPLACE INTO frequency (lemma_id, count, rank, zipf, band, source) "
            "VALUES (?,?,?,?,?,?)",
            (lid, count, rank, round(zipf, 3), zipf_band(zipf), source),
        )
    conn.commit()

    bands: dict[str, int] = {}
    for _, c in ranked:
        b = zipf_band(math.log10(c) - math.log10(total) + 9.0)
        bands[b] = bands.get(b, 0) + 1
    conn.close()
    return {
        "freq_rows": len(rows),
        "corpus_total": total,
        "matched_surfaces": matched_surfaces,
        "lemmas_scored": len(ranked),
        "bands": bands,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest corpus word frequency into the frequency table.")
    ap.add_argument("--freq-file", required=True, help='Plain text "word count" per line.')
    ap.add_argument("--db", default="data/db/lexorama.sqlite")
    ap.add_argument("--source", default="opensubtitles-freq")
    args = ap.parse_args()

    if not os.path.exists(args.freq_file):
        sys.exit(f"Frequency file not found: {args.freq_file}")
    if not os.path.exists(args.db):
        sys.exit(f"DB not found: {args.db} (build the lexical store first).")

    print(f"Frequency pass: {args.freq_file} as {args.source} -> {args.db}", file=sys.stderr)
    import json
    print(json.dumps(ingest_frequency(args.freq_file, args.db, args.source), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
