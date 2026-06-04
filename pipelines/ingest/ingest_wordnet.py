"""Densify the lexical graph with Open Multilingual Wordnet (Greek) edges.

Wiktionary gives us plenty of `synonym`/`related`/`antonym` edges but almost no
**taxonomy**: only ~130 hypernym/hyponym edges total. WordNet's whole point is the
is-a hierarchy, so this importer adds the missing `hypernym`/`hyponym` (and any
extra `synonym`) edges from `omw-el`, the Greek wordnet, whose synset relations
live in the Princeton structure shared via `omw-en` (the `expand` lexicon).

Design choices that keep the graph clean and honest (cardinal rule: every edge
typed + sourced):
  · POS-matched — a wordnet noun sense only attaches to a `noun` lemma in our
    store, never to a same-spelled verb/adjective homograph.
  · linked-only — an edge is emitted only when BOTH endpoints already exist as
    single-word lemmas in our DB (target_lemma_id resolved). WordNet's many
    multiword/periphrastic synset members (“αυτοκινούμενο όχημα”) produce no
    dangling text nodes.
  · idempotent — every prior `source='omw-el'` row is deleted first, so the
    importer can be replayed after a wordnet refresh.
  · provenance — `source='omw-el'`, distinct from the wiktionary edges, so the
    graph view can label and (if desired) style wordnet edges separately.

The API holds the SQLite WAL DB — STOP it before running, restart after.
Run:  python -m pipelines.ingest.ingest_wordnet
"""

from __future__ import annotations

import argparse
import collections
import sqlite3
import sys

DB = "data/db/lexorama.sqlite"
SOURCE = "omw-el"

# wordnet POS → our lemmas.pos vocabulary
_POS = {"n": "noun", "v": "verb", "a": "adj", "s": "adj", "r": "adv"}


def _norm_index(conn: sqlite3.Connection) -> dict[tuple[str, str], list[int]]:
    """(normalized_lemma, pos) → [lemma_id]. POS-keyed so we attach a wordnet
    sense only to a lemma of the matching part of speech."""
    idx: dict[tuple[str, str], list[int]] = collections.defaultdict(list)
    for lid, norm, pos in conn.execute(
        "SELECT id, normalized_lemma, pos FROM lemmas"
    ):
        if norm and pos:
            idx[(norm, pos)].append(lid)
    return idx


def ingest(db_path: str, dry_run: bool = False) -> dict:
    import wn
    from .normalize_greek import normalize
    from .ingest_kaikki import record_attribution

    el = wn.Wordnet("omw-el:1.4", expand="omw-en:1.4")
    conn = sqlite3.connect(db_path)
    idx = _norm_index(conn)

    def lemmas_for(text: str, pos: str) -> list[int]:
        return idx.get((normalize(text), pos), [])

    # collected, de-duplicated edges: (src_id, tgt_id, relation_type)
    edges: set[tuple[int, int, str]] = set()
    counts = collections.Counter()
    seen_words = 0

    for w in el.words():
        our_pos = _POS.get(w.pos)
        if not our_pos:
            continue
        src_lemma = w.lemma()
        src_ids = lemmas_for(src_lemma, our_pos)
        if not src_ids:
            continue  # the headword isn't an entry we hold → nothing to attach to
        seen_words += 1

        for syn in w.synsets():
            # synonyms: co-members of the same synset
            for other in syn.lemmas():
                if other == src_lemma or " " in other:
                    continue
                for tid in lemmas_for(other, our_pos):
                    for sid in src_ids:
                        if sid != tid:
                            edges.add((sid, tid, "synonym"))

            # taxonomy: hypernym (broader) and hyponym (narrower)
            for rel, related in (("hypernym", syn.hypernyms()),
                                 ("hyponym", syn.hyponyms())):
                tgt_pos = our_pos  # taxonomy stays within a POS
                for rs in related:
                    for tgt_lemma in rs.lemmas():
                        if " " in tgt_lemma:
                            continue  # skip multiword/periphrastic synset members
                        for tid in lemmas_for(tgt_lemma, tgt_pos):
                            for sid in src_ids:
                                if sid != tid:
                                    edges.add((sid, tid, rel))

    for _, _, rel in edges:
        counts[rel] += 1

    if not dry_run:
        prior = conn.execute(
            "DELETE FROM relations WHERE source=?", (SOURCE,)
        ).rowcount
        conn.executemany(
            "INSERT INTO relations (source_lemma_id, target_lemma_id, target_text, "
            "relation_type, weight, source) VALUES (?,?,NULL,?,1.0,?)",
            [(s, t, r, SOURCE) for (s, t, r) in edges],
        )
        record_attribution(conn, SOURCE)
        conn.commit()
    else:
        prior = 0
    conn.close()

    return {
        "wordnet_headwords_matched": seen_words,
        "edges": len(edges),
        "by_type": dict(counts),
        "prior_deleted": prior,
        "dry_run": dry_run,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    stats = ingest(args.db, dry_run=args.dry_run)
    print(
        f"matched headwords: {stats['wordnet_headwords_matched']}\n"
        f"edges: {stats['edges']}  by_type={stats['by_type']}\n"
        f"prior omw-el rows deleted: {stats['prior_deleted']}  (dry_run={stats['dry_run']})",
        file=sys.stderr,
    )
    import json
    print(json.dumps({k: v for k, v in stats.items() if k != "by_type"}))


if __name__ == "__main__":
    main()
