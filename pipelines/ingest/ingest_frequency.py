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

    # Map a normalized surface -> the lemma_id(s) it can resolve to. A surface may
    # belong to several lemmas (homographs); we credit each, so a lemma's count is
    # an upper bound that sums every form attributable to it.
    surface_to_lemmas: dict[str, list[int]] = {}
    for norm, lemma_id in conn.execute("SELECT normalized_surface, lemma_id FROM search_index"):
        surface_to_lemmas.setdefault(norm, []).append(lemma_id)

    lemma_count: dict[int, int] = {}
    matched_surfaces = 0
    for word, count in rows:
        ids = surface_to_lemmas.get(normalize(word))
        if not ids:
            continue
        matched_surfaces += 1
        for lid in ids:
            lemma_count[lid] = lemma_count.get(lid, 0) + count

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
