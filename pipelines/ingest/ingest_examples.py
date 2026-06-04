"""Ingest KWIC example sentences (concordances) into `corpus_examples`.

Wiktionary's curated examples are sparse, so we surface *authentic* usage from a
sentence corpus: the Wortschatz Leipzig "ell_news" collection, which ships one
sentence per line as `id <TAB> sentence`.

A good example sentence is a property of a LEMMA. We tokenize each sentence,
resolve every token to a lemma via `search_index` (lemmas + inflected forms ->
lemma_id, exactly as the frequency/collocation passes do), and offer the sentence
as a candidate to each lemma it contains. We keep only the cleanest few per lemma,
ranked by a readability heuristic (well-formed length, proper capitalization and
terminal punctuation, low digit/symbol noise) so the word page shows natural,
complete sentences rather than corpus fragments.

Memory is bounded by the lexicon, not the corpus: we stream the sentence file and
maintain just the running top-N per lemma.

This pass is idempotent: it clears `corpus_examples` for the given --source.

Run (after building the lexical store + search_index):
    python pipelines/ingest/ingest_examples.py \
        --sentences-file data/raw/ell_news_2020_1M/ell_news_2020_1M-sentences.txt \
        --db data/db/lexorama.sqlite
"""

from __future__ import annotations

import argparse
import os
import sys

# Reuse the shared DB bootstrap + attribution registry + Greek normalizer +
# the curated stopword set (we don't generate examples for function words).
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipelines", "ingest"))
from ingest_kaikki import init_db, record_attribution  # noqa: E402
from ingest_collocations import STOPWORDS  # noqa: E402
from normalize_greek import normalize  # noqa: E402

DEFAULT_TOP_N = 5

# A readable sentence sits in this word-count window: long enough to give context,
# short enough to scan. Fragments and walls-of-text are rejected.
MIN_WORDS = 6
MAX_WORDS = 28
IDEAL_WORDS = 14

# Don't mine examples for closed-class / very short headwords (articles, particles):
# the sentences would be arbitrary and the feature is useless for them.
MIN_TARGET_LEN = 3

# Greek capitals (incl. accented) — a real sentence starts with one.
GREEK_UPPER = set("ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩΆΈΉΊΌΎΏΪΫ")
# Greek terminal punctuation: «;» is the Greek question mark.
TERMINALS = set(".!;…")
# Stripped from token edges before normalizing/resolving.
EDGE_PUNCT = "«»\"'“”‘’()[]{}.,:;·…!?-–—/\\|<>*•%&@#~_=+"


def clean_token(tok: str) -> str:
    return tok.strip(EDGE_PUNCT)


def sentence_quality(sentence: str, n_words: int) -> float | None:
    """Readability score for a candidate sentence; None rejects it outright.
    Higher is better. Favors mid-length, well-formed, low-noise sentences."""
    if n_words < MIN_WORDS or n_words > MAX_WORDS:
        return None
    s = sentence.strip()
    if not s:
        return None
    if s[0] not in GREEK_UPPER:
        return None
    if s[-1] not in TERMINALS:
        return None
    low = s.lower()
    if "http" in low or "www." in low or "@" in s:
        return None
    digits = sum(ch.isdigit() for ch in s)
    if digits > len(s) * 0.15:  # mostly numbers/dates — poor example
        return None
    # Penalize distance from the ideal length; small bonus for ending in a period.
    score = -abs(n_words - IDEAL_WORDS)
    if s[-1] == ".":
        score += 0.5
    return score


def ingest_examples(
    sentences_file: str,
    db_path: str,
    source: str,
    top_n: int = DEFAULT_TOP_N,
) -> dict:
    conn = init_db(db_path)
    record_attribution(conn, source)

    # normalized surface -> lemma_id(s). A surface may map to several lemmas
    # (homographs); the sentence is offered to each. Skip stopword/short surfaces
    # up front so we never even track function words.
    surface_to_lemmas: dict[str, list[int]] = {}
    for norm, lemma_id in conn.execute("SELECT normalized_surface, lemma_id FROM search_index"):
        if len(norm) < MIN_TARGET_LEN or norm in STOPWORDS:
            continue
        surface_to_lemmas.setdefault(norm, []).append(lemma_id)

    # lemma_id -> list of (score, sentence), the running top-N for that lemma.
    best: dict[int, list[tuple[float, str]]] = {}

    def offer(lid: int, score: float, sentence: str) -> None:
        bucket = best.setdefault(lid, [])
        if len(bucket) < top_n:
            bucket.append((score, sentence))
            return
        # Replace the current worst if this one is better.
        worst_i = min(range(len(bucket)), key=lambda i: bucket[i][0])
        if score > bucket[worst_i][0]:
            bucket[worst_i] = (score, sentence)

    sentences_seen = 0
    sentences_used = 0
    with open(sentences_file, "r", encoding="utf-8") as fh:
        for line in fh:
            sentences_seen += 1
            # Leipzig format: "id <TAB> sentence". Fall back to whole line.
            tab = line.find("\t")
            sentence = (line[tab + 1:] if tab != -1 else line).strip()
            tokens = sentence.split()
            score = sentence_quality(sentence, len(tokens))
            if score is None:
                continue
            # Which known content lemmas does this sentence mention? (deduped)
            lemmas: set[int] = set()
            for tok in tokens:
                nrm = normalize(clean_token(tok))
                if not nrm:
                    continue
                ids = surface_to_lemmas.get(nrm)
                if ids:
                    lemmas.update(ids)
            if not lemmas:
                continue
            sentences_used += 1
            for lid in lemmas:
                offer(lid, score, sentence)

    conn.execute("DELETE FROM corpus_examples WHERE source = ?", (source,))
    total_rows = 0
    lemmas_with_examples = 0
    for lid, bucket in best.items():
        if not bucket:
            continue
        lemmas_with_examples += 1
        # Best score first; for equal scores prefer the shorter sentence.
        ordered = sorted(bucket, key=lambda sv: (-sv[0], len(sv[1])))
        for seq, (_score, sentence) in enumerate(ordered):
            conn.execute(
                "INSERT INTO corpus_examples (lemma_id, sentence, source, seq) VALUES (?,?,?,?)",
                (lid, sentence, source, seq),
            )
            total_rows += 1
    conn.commit()
    conn.close()
    return {
        "sentences_seen": sentences_seen,
        "sentences_used": sentences_used,
        "lemmas_with_examples": lemmas_with_examples,
        "example_rows": total_rows,
        "top_n": top_n,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest KWIC example sentences into corpus_examples.")
    ap.add_argument("--sentences-file", required=True, help="Leipzig *-sentences.txt")
    ap.add_argument("--db", default="data/db/lexorama.sqlite")
    ap.add_argument("--source", default="leipzig-examples")
    ap.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    args = ap.parse_args()

    if not os.path.exists(args.sentences_file):
        sys.exit(f"Sentences file not found: {args.sentences_file}")
    if not os.path.exists(args.db):
        sys.exit(f"DB not found: {args.db} (build the lexical store first).")

    print(f"Examples pass: {args.sentences_file} as {args.source} -> {args.db}", file=sys.stderr)
    import json
    print(json.dumps(
        ingest_examples(args.sentences_file, args.db, args.source, args.top_n),
        indent=2, ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
