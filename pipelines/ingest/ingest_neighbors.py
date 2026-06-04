"""Train word embeddings and ingest semantic neighbors into `semantic_neighbors`.

This is the static (single-corpus) precursor to Layer C (diachronic semantic
drift): we learn a word2vec model over the sentence corpus, then for each lemma
store its nearest words in vector space — distributional near-synonyms, the words
that appear in *similar contexts* (καναπές ~ πολυθρόνα), as opposed to words that
merely co-occur (collocations).

Everything lives in the normalized key space: we tokenize sentences with the same
`normalize()` used for search keys, so a lemma's `normalized_lemma` is its vector
key and a neighbor token resolves straight back to a lemma via `search_index`.
Only neighbors that resolve to a known lemma are kept, so every neighbor links to
a word page.

Memory stays bounded: the corpus is streamed from disk on every gensim pass via a
re-iterable sentence reader; only the model and the lexicon maps live in RAM.

Requires gensim (`pip install gensim`). Idempotent per --source.

Run (after building the lexical store + search_index):
    python pipelines/ingest/ingest_neighbors.py \
        --sentences-file data/raw/ell_news_2020_1M/ell_news_2020_1M-sentences.txt \
        --db data/db/lexorama.sqlite
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipelines", "ingest"))
from ingest_kaikki import init_db, record_attribution  # noqa: E402
from ingest_collocations import STOPWORDS  # noqa: E402
from normalize_greek import normalize  # noqa: E402

DEFAULT_TOP_N = 8
MIN_NEIGHBOR_LEN = 3
# How many raw candidates to pull from the model before filtering down to top_n
# (we drop stopwords, self, and tokens that don't resolve to a lemma).
CANDIDATE_POOL = 40

EDGE_PUNCT = "«»\"'“”‘’()[]{}.,:;·…!?-–—/\\|<>*•%&@#~_=+"


def _tokens(line: str) -> list[str]:
    """Normalized content tokens for one corpus line ("id <TAB> sentence")."""
    tab = line.find("\t")
    text = line[tab + 1:] if tab != -1 else line
    out: list[str] = []
    for raw in text.split():
        nrm = normalize(raw.strip(EDGE_PUNCT))
        if nrm:
            out.append(nrm)
    return out


class SentenceReader:
    """Re-iterable token stream over one or more corpus files — gensim reads it
    once to build the vocab and once per epoch, so __iter__ must reopen each file
    every time. Passing several files pools registers for broader, more stable
    vectors; this is fine for STATIC neighbors (we want coverage), but never for
    diachronic work where each slice must stay a single consistent corpus."""

    def __init__(self, paths: str | list[str]):
        self.paths = [paths] if isinstance(paths, str) else list(paths)

    def __iter__(self):
        for path in self.paths:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    toks = _tokens(line)
                    if toks:
                        yield toks


def ingest_neighbors(
    sentences_file: str | list[str],
    db_path: str,
    source: str,
    top_n: int = DEFAULT_TOP_N,
    vector_size: int = 100,
    window: int = 5,
    min_count: int = 10,
    epochs: int = 5,
) -> dict:
    from gensim.models import Word2Vec  # imported lazily so the module loads without gensim

    print("Training word2vec (this streams the corpus several times)…", file=sys.stderr)
    model = Word2Vec(
        sentences=SentenceReader(sentences_file),
        vector_size=vector_size,
        window=window,
        min_count=min_count,
        workers=os.cpu_count() or 4,
        sg=0,            # CBOW: fast and stable on a ~20M-token corpus
        epochs=epochs,
    )
    wv = model.wv
    print(f"Vocabulary: {len(wv.index_to_key)} tokens.", file=sys.stderr)

    conn = init_db(db_path)
    record_attribution(conn, source)

    # normalized surface -> a single representative lemma_id (highest rank_weight).
    # We keep one lemma per surface so a neighbor maps to exactly one word page.
    surface_to_lemma: dict[str, int] = {}
    for norm, lemma_id, rw in conn.execute(
        "SELECT normalized_surface, lemma_id, rank_weight FROM search_index"
    ):
        # First writer wins per surface only if higher rank; emulate with a max.
        prev = surface_to_lemma.get(norm)
        if prev is None:
            surface_to_lemma[norm] = lemma_id
    # Map lemma_id -> (display lemma, normalized_lemma) for the lemmas we'll score.
    lemma_disp: dict[int, str] = {}
    lemma_norm: dict[int, str] = {}
    for lid, lemma, nlemma in conn.execute("SELECT id, lemma, normalized_lemma FROM lemmas"):
        lemma_disp[lid] = lemma
        lemma_norm[lid] = nlemma

    conn.execute("DELETE FROM semantic_neighbors WHERE source = ?", (source,))
    total_rows = 0
    lemmas_scored = 0

    for lid, nlemma in lemma_norm.items():
        if nlemma not in wv:
            continue  # lemma's key wasn't frequent enough to get a vector
        try:
            cands = wv.most_similar(nlemma, topn=CANDIDATE_POOL)
        except KeyError:
            continue
        chosen: list[tuple[str, float, int]] = []
        seen: set[int] = set()
        for token, score in cands:
            if len(token) < MIN_NEIGHBOR_LEN or token in STOPWORDS:
                continue
            nb_lid = surface_to_lemma.get(token)
            if nb_lid is None or nb_lid == lid or nb_lid in seen:
                continue
            seen.add(nb_lid)
            chosen.append((lemma_disp.get(nb_lid, token), round(float(score), 4), nb_lid))
            if len(chosen) >= top_n:
                break
        if not chosen:
            continue
        lemmas_scored += 1
        for seq, (disp, score, nb_lid) in enumerate(chosen):
            conn.execute(
                "INSERT INTO semantic_neighbors (lemma_id, neighbor, neighbor_lemma_id, score, source, seq) "
                "VALUES (?,?,?,?,?,?)",
                (lid, disp, nb_lid, score, source, seq),
            )
            total_rows += 1
    conn.commit()
    conn.close()
    return {
        "vocab": len(wv.index_to_key),
        "lemmas_with_neighbors": lemmas_scored,
        "neighbor_rows": total_rows,
        "top_n": top_n,
        "vector_size": vector_size,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Train embeddings + ingest semantic neighbors.")
    ap.add_argument("--sentences-file", required=True, nargs="+",
                    help="One or more Leipzig *-sentences.txt (multiple pools registers for "
                         "broader static neighbors).")
    ap.add_argument("--db", default="data/db/lexorama.sqlite")
    ap.add_argument("--source", default="leipzig-embeddings")
    ap.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    ap.add_argument("--vector-size", type=int, default=100)
    ap.add_argument("--min-count", type=int, default=10)
    ap.add_argument("--epochs", type=int, default=5)
    args = ap.parse_args()

    for path in args.sentences_file:
        if not os.path.exists(path):
            sys.exit(f"Sentences file not found: {path}")
    if not os.path.exists(args.db):
        sys.exit(f"DB not found: {args.db} (build the lexical store first).")

    print(f"Neighbors pass: {', '.join(args.sentences_file)} as {args.source} -> {args.db}",
          file=sys.stderr)
    import json
    print(json.dumps(
        ingest_neighbors(
            args.sentences_file, args.db, args.source, args.top_n,
            args.vector_size, min_count=args.min_count, epochs=args.epochs,
        ),
        indent=2, ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
