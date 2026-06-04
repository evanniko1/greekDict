"""Layer B — ingest frequency-over-time into `frequency_timeseries`.

For each (corpus, year) slice we sum a lemma's occurrences (over all its forms,
resolved via search_index) and normalize by the slice's total token count to
per-million, so years and corpora share a comparable y-axis.

CARDINAL RULE: a time series is valid only within ONE consistent corpus. So one
invocation handles one corpus — either a directory of Leipzig year-folders
(corpus=news) or the Parliament CSV (corpus=parliament). Never merge the two into
a single line; the UI shows them as separate labeled series.

Idempotent: clears `frequency_timeseries` for the chosen corpus, then rewrites.

Examples:
    # News axis from several Leipzig year-folders under data/raw/
    python pipelines/ingest/ingest_frequency_timeseries.py \
        --leipzig-dir data/raw --db data/db/lexorama.sqlite

    # Parliament axis from the Zenodo CSV
    python pipelines/ingest/ingest_frequency_timeseries.py \
        --parliament-csv data/raw/Greek_Parliament_Proceedings_1989_2020.csv \
        --db data/db/lexorama.sqlite
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipelines", "ingest"))
from ingest_kaikki import init_db, record_attribution  # noqa: E402
from normalize_greek import normalize_keep_accents  # noqa: E402
import corpus_sources as cs  # noqa: E402


def _surface_to_lemmas(conn) -> dict[str, list[int]]:
    """Map an ACCENT-PRESERVING surface key to the lemma_id(s) that own it. Keyed on
    `normalize_keep_accents(search_index.surface)`, NOT the accent-folded
    `normalized_surface`: folding accents merges νόμος/νομός etc., which would then
    double-attribute every corpus token to both homographs. Corpus tokens are keyed
    the same way (cs.tokenize), so a token only counts toward a lemma whose accented
    form it actually matches."""
    m: dict[str, list[int]] = {}
    for surface, lemma_id in conn.execute("SELECT surface, lemma_id FROM search_index"):
        key = normalize_keep_accents(surface)
        if key:
            m.setdefault(key, []).append(lemma_id)
    return m


def ingest_timeseries(db_path: str, corpus: str, slices: dict, source: str) -> dict:
    """`slices` maps year -> a counter of (lemma_id -> count) plus a special key
    "__total__" -> total tokens in that year's slice. Built by the caller so this
    function stays corpus-agnostic."""
    conn = init_db(db_path)
    record_attribution(conn, source)
    conn.execute("DELETE FROM frequency_timeseries WHERE corpus = ?", (corpus,))

    rows = 0
    for year in sorted(slices):
        per_lemma = slices[year]
        total = per_lemma.pop("__total__", 0) or 1
        for lemma_id, count in per_lemma.items():
            per_million = count / total * 1_000_000
            conn.execute(
                "INSERT INTO frequency_timeseries (lemma_id, corpus, year, count, per_million, source) "
                "VALUES (?,?,?,?,?,?)",
                (lemma_id, corpus, year, count, round(per_million, 3), source),
            )
            rows += 1
    conn.commit()
    conn.close()
    return {"corpus": corpus, "years": sorted(slices), "rows": rows}


def build_from_leipzig(conn_map: dict[str, list[int]], leipzig_dir: str,
                       source: str | None = None) -> dict:
    """Accumulate per-year lemma counts from Leipzig word-frequency files. When
    `source` is set, only that corpus's folders are read (keeps co-located corpora
    on separate axes)."""
    slices: dict[int, dict] = {}
    discovered = cs.discover_leipzig_slices(leipzig_dir, source)
    if not discovered:
        avail = cs.discover_leipzig_sources(leipzig_dir)
        hint = f" Available: {avail}." if avail else ""
        sys.exit(f"No Leipzig corpus folders (…_YYYY_…) found under {leipzig_dir}"
                 f"{f' for source={source!r}' if source else ''}.{hint}")
    for year, folder in discovered:
        bucket = slices.setdefault(year, {"__total__": 0})
        for word, freq in cs.read_leipzig_words(folder):
            bucket["__total__"] += freq
            ids = conn_map.get(normalize_keep_accents(word))
            if not ids:
                continue
            for lid in ids:
                bucket[lid] = bucket.get(lid, 0) + freq
        print(f"  · {os.path.basename(folder)} (year {year}): {bucket['__total__']} tokens",
              file=sys.stderr)
    return slices


def build_from_parliament(conn_map: dict[str, list[int]], csv_path: str,
                          text_col: str, date_col: str) -> dict:
    """Stream the Parliament CSV, counting per-year lemma occurrences on the fly
    (memory bounded by lemmas×years, not by the corpus)."""
    slices: dict[int, dict] = {}
    n = 0
    for year, text in cs.iter_parliament_speeches(csv_path, text_col, date_col):
        bucket = slices.setdefault(year, {"__total__": 0})
        for tok in cs.tokenize(text):
            bucket["__total__"] += 1
            ids = conn_map.get(tok)
            if not ids:
                continue
            for lid in ids:
                bucket[lid] = bucket.get(lid, 0) + 1
        n += 1
        if n % 100_000 == 0:
            print(f"  · {n} speeches…", file=sys.stderr)
    return slices


def main() -> None:
    ap = argparse.ArgumentParser(description="Layer B: ingest frequency over time.")
    ap.add_argument("--db", default="data/db/lexorama.sqlite")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--leipzig-dir", help="Directory holding Leipzig year-folders.")
    src.add_argument("--parliament-csv", help="Greek Parliament Proceedings CSV (corpus=parliament).")
    ap.add_argument("--leipzig-source",
                    help="When several Leipzig corpora share --leipzig-dir, pick ONE by its "
                         "source prefix ('ell_news', 'ell_wikipedia') or clean label "
                         "('news', 'wiki'). The corpus axis label defaults from it. "
                         "Omit only when the directory holds a single corpus.")
    ap.add_argument("--corpus", help="Override the corpus label.")
    ap.add_argument("--text-col", default="speech")
    ap.add_argument("--date-col", default="sitting_date")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        sys.exit(f"DB not found: {args.db} (build the lexical store first).")

    conn = init_db(args.db)
    conn_map = _surface_to_lemmas(conn)
    conn.close()

    if args.leipzig_dir:
        # Resolve the axis label from the chosen Leipzig source, so a wiki corpus
        # lands on a 'wiki' axis rather than defaulting to 'news'.
        avail = cs.discover_leipzig_sources(args.leipzig_dir)
        if args.leipzig_source is None and len(avail) > 1:
            sys.exit(f"--leipzig-dir holds multiple corpora {avail}; pass --leipzig-source "
                     "to pick one (each stays on its own axis — never merged).")
        label = cs.LEIPZIG_CORPUS_LABELS.get(args.leipzig_source or "", args.leipzig_source)
        if label is None and avail:
            label = next(iter(avail))
        corpus = args.corpus or label or "news"
        source = "leipzig-freq-ts"
        slices = build_from_leipzig(conn_map, args.leipzig_dir, args.leipzig_source)
    else:
        corpus = args.corpus or "parliament"
        source = "parliament-freq-ts"
        slices = build_from_parliament(conn_map, args.parliament_csv, args.text_col, args.date_col)

    import json
    print(json.dumps(ingest_timeseries(args.db, corpus, slices, source), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
