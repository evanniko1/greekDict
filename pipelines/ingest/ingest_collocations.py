"""Ingest corpus co-occurrence (collocations) into the `collocations` table.

Wiktionary has no collocation data, so we layer it from an external corpus: the
Wortschatz Leipzig "Corpora Collection" for Modern Greek, which ships sentence
co-occurrence statistics computed over a news/web corpus.

A Leipzig corpus archive (e.g. `ell_news_2020_300K.tar.gz`) unpacks to several
tab-separated files; we need two:
    *-words.txt   word_id <TAB> word <TAB> freq
    *-co_s.txt    w1_id  <TAB> w2_id <TAB> sentence_cooccurrence_freq <TAB> significance

`significance` is a log-likelihood-style association score: higher = the two
words co-occur far more than chance. Pairs are stored ONCE (unordered), so we
credit the collocate to both members of each pair.

A collocation is a property of a LEMMA. We resolve each corpus word through
`search_index` (lemmas + inflected forms -> lemma_id) and attach the strongest
collocates to the lemma, keeping the top --top-n per lemma by significance. When
the collocate itself resolves to a known lemma we store collocate_lemma_id so the
chip links to that word's page.

This pass is idempotent: it clears the table for the given --source and rewrites.

Download a Greek corpus from https://wortschatz.uni-leipzig.de/en/download/Modern%20Greek
and unpack it, then run:
    python pipelines/ingest/ingest_collocations.py \
        --words-file  data/raw/ell_news_2020_300K-words.txt \
        --cooc-file   data/raw/ell_news_2020_300K-co_s.txt \
        --db data/db/lexorama.sqlite
"""

from __future__ import annotations

import argparse
import os
import sys

# Reuse the shared DB bootstrap + attribution registry + Greek normalizer.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipelines", "ingest"))
from ingest_kaikki import init_db, record_attribution  # noqa: E402
from normalize_greek import normalize  # noqa: E402

DEFAULT_TOP_N = 12
# Skip very short / closed-class tokens that dominate co-occurrence by frequency
# alone (articles, conjunctions, particles) — they are noise as "collocations".
MIN_WORD_LEN = 3

# Greek function words (articles, prepositions, conjunctions, pronouns, particles,
# auxiliaries) co-occur with everything and have huge raw log-likelihood, so they
# swamp the genuinely informative collocates. Filtered out by normalized form.
_STOPWORDS_RAW = """
ο η το οι τα του της των τον την τη στο στη στον στην στα στους στις στους
ένας ένα μια μία έναν ενός μιας
και κι ή είτε ούτε μήτε αλλά όμως ωστόσο ενώ αν εάν όταν καθώς αφού επειδή
διότι γιατί ότι πως που να θα ας μα δηλαδή λοιπόν άρα ώστε
σε με από για προς κατά μετά παρά αντί δια χωρίς μέχρι έως ως πριν μέσα έξω
πάνω κάτω μπροστά πίσω δίπλα κοντά μακριά γύρω εκτός εντός
εγώ εσύ αυτός αυτή αυτό εμείς εσείς αυτοί αυτές αυτά εμένα εσένα μας σας τους
μου σου του της μου εμάς εσάς μην μη δεν όχι ναι
είμαι είσαι είναι είμαστε είστε ήμουν ήσουν ήταν ήμασταν ήταν
έχω έχεις έχει έχουμε έχετε έχουν είχα είχε
αυτού εκείνος εκείνη εκείνο τι ποιος ποια ποιο πού πώς ποτέ κάθε όλα όλος όλη
πολύ πιο πλέον ήδη ακόμη ακόμα μόνο επίσης
""".split()
STOPWORDS = {normalize(w) for w in _STOPWORDS_RAW}


def read_words_file(path: str) -> dict[str, str]:
    """Parse "word_id <TAB> word <TAB> freq" -> {word_id: word}."""
    id_to_word: dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            id_to_word[parts[0]] = parts[1]
    return id_to_word


def ingest_collocations(
    words_file: str,
    cooc_file: str,
    db_path: str,
    source: str,
    top_n: int = DEFAULT_TOP_N,
) -> dict:
    conn = init_db(db_path)
    record_attribution(conn, source)

    id_to_word = read_words_file(words_file)

    # normalized surface -> lemma_id(s). A surface may map to several lemmas
    # (homographs); we attach the collocate to each.
    surface_to_lemmas: dict[str, list[int]] = {}
    for norm, lemma_id in conn.execute("SELECT normalized_surface, lemma_id FROM search_index"):
        surface_to_lemmas.setdefault(norm, []).append(lemma_id)

    # The co_s file can be millions of pairs, so we DON'T load it all. We only
    # care about words that resolve to a lemma, so precompute, per word-id that
    # resolves: its normalized form (for self-checks) and the lemma_id(s) it feeds.
    # Then stream the pairs and accumulate collocates straight into per-lemma
    # buckets — memory is bounded by the lexicon, not the corpus.
    tracked: dict[str, tuple[str, list[int]]] = {}  # word_id -> (normalized_word, [lemma_id])
    for wid, word in id_to_word.items():
        nrm = normalize(word)
        lemmas = surface_to_lemmas.get(nrm)
        if lemmas:
            tracked[wid] = (nrm, lemmas)

    # lemma_id -> { collocate_display: best_significance }. Keeping the best
    # significance per (lemma, collocate-display) collapses inflected variants of
    # the same collocate to their strongest hit.
    lemma_collocs: dict[int, dict[str, float]] = {}
    matched_word_ids: set[str] = set()

    def credit(src_id: str, collocate: str, sig: float) -> None:
        """Attach `collocate` to every lemma fed by the tracked word `src_id`."""
        entry = tracked.get(src_id)
        if entry is None:
            return
        src_norm, lemmas = entry
        if len(collocate) < MIN_WORD_LEN:
            return
        cn = normalize(collocate)
        if cn == src_norm:  # don't collocate a word with itself
            return
        if cn in STOPWORDS:  # drop function words (articles, prepositions, …)
            return
        matched_word_ids.add(src_id)
        for lid in lemmas:
            bucket = lemma_collocs.setdefault(lid, {})
            if sig > bucket.get(collocate, float("-inf")):
                bucket[collocate] = sig

    with open(cooc_file, "r", encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4:
                continue
            id1, id2 = parts[0], parts[1]
            # Skip the pair entirely unless at least one side is a tracked lemma word.
            if id1 not in tracked and id2 not in tracked:
                continue
            try:
                sig = float(parts[3])
            except ValueError:
                continue
            w1 = id_to_word.get(id1)
            w2 = id_to_word.get(id2)
            if not w1 or not w2:
                continue
            credit(id1, w2, sig)  # pairs are unordered, so credit both directions
            credit(id2, w1, sig)

    if not lemma_collocs:
        conn.close()
        sys.exit(f"No co-occurrence pairs from {cooc_file} resolved to a lemma.")
    matched_words = len(matched_word_ids)

    conn.execute("DELETE FROM collocations WHERE source = ?", (source,))
    total_rows = 0
    lemmas_with_collocs = 0
    for lid, bucket in lemma_collocs.items():
        # Walk strongest-first, deduping by the collocate's resolved lemma (so
        # inflected variants of the same target — "Δίκαιο"/"δίκαιο" — collapse to
        # one chip, keeping the highest score), and drop a collocate that resolves
        # back to the headword itself. Slice to top_n AFTER dedupe so duplicates
        # don't eat slots.
        seen_targets: set = set()
        chosen: list[tuple[str, float, int | None]] = []
        for collocate, sig in sorted(bucket.items(), key=lambda kv: kv[1], reverse=True):
            coll_ids = surface_to_lemmas.get(normalize(collocate))
            coll_lemma_id = coll_ids[0] if coll_ids else None
            if coll_lemma_id == lid:  # an inflected form of the headword — skip
                continue
            key = ("L", coll_lemma_id) if coll_lemma_id is not None else ("N", normalize(collocate))
            if key in seen_targets:
                continue
            seen_targets.add(key)
            chosen.append((collocate, sig, coll_lemma_id))
            if len(chosen) >= top_n:
                break
        if not chosen:
            continue
        lemmas_with_collocs += 1
        for seq, (collocate, sig, coll_lemma_id) in enumerate(chosen):
            conn.execute(
                "INSERT INTO collocations "
                "(lemma_id, collocate, collocate_lemma_id, score, source, seq) "
                "VALUES (?,?,?,?,?,?)",
                (lid, collocate, coll_lemma_id, round(sig, 3), source, seq),
            )
            total_rows += 1
    conn.commit()
    conn.close()
    return {
        "words": len(id_to_word),
        "matched_words": matched_words,
        "lemmas_with_collocations": lemmas_with_collocs,
        "collocation_rows": total_rows,
        "top_n": top_n,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest corpus co-occurrence into the collocations table.")
    ap.add_argument("--words-file", required=True, help="Leipzig *-words.txt")
    ap.add_argument("--cooc-file", required=True, help="Leipzig *-co_s.txt")
    ap.add_argument("--db", default="data/db/lexorama.sqlite")
    ap.add_argument("--source", default="leipzig-coocc")
    ap.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    args = ap.parse_args()

    for f in (args.words_file, args.cooc_file):
        if not os.path.exists(f):
            sys.exit(f"Input file not found: {f}")
    if not os.path.exists(args.db):
        sys.exit(f"DB not found: {args.db} (build the lexical store first).")

    print(f"Collocations pass: {args.words_file} + {args.cooc_file} as {args.source} -> {args.db}", file=sys.stderr)
    import json
    print(json.dumps(
        ingest_collocations(args.words_file, args.cooc_file, args.db, args.source, args.top_n),
        indent=2, ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
