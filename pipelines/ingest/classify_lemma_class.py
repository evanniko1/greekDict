"""Classify each lemma as 'content' or 'name' (Phase 2 / audit F37).

Proper names are ~76% of the lexicon (352,155 of 463,411). They own 42.8% of the search
index and carry the boilerplate «επώνυμο» sense, so they distort every coverage and
frequency figure and crowd out real words in search. This pass tags them so the API can
split them into their own namespace and report the honest content-lemma count (~111k).

Two signals, both conservative:
  1. POS — Wiktionary's own `pos='name'` tag (the primary 76%).
  2. Gloss — a non-name-POS lemma whose EVERY sense is a name gloss (surname / given
     name / patronymic / toponym). `all senses` matters: a word that is BOTH a common
     noun and a surname (it has a real sense too) stays content and is disambiguated at
     ranking, exactly as the homograph fix intends.

Idempotent: recomputes lemma_class from scratch each run. Run after ingest (it needs the
senses to exist), before build_search_index if you want the class carried into search.

    PYTHONIOENCODING=utf-8 python pipelines/ingest/classify_lemma_class.py \
        --db data/db/lexorama.sqlite
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys

# Greek gloss markers for a proper-name sense. Kept tight to avoid catching common words
# whose definition merely mentions a name (e.g. «το όνομά του»): these are the canonical
# Wiktionary name-defining phrases.
NAME_GLOSS_LIKE = ("%επώνυμο%", "%ανδρικό όνομα%", "%γυναικείο όνομα%",
                   "%πατρώνυμο%", "%τοπωνύμιο%", "%βαφτιστικό όνομα%")


def ensure_column(conn: sqlite3.Connection) -> None:
    cols = [r[1] for r in conn.execute("PRAGMA table_info(lemmas)")]
    if "lemma_class" not in cols:
        conn.execute("ALTER TABLE lemmas ADD COLUMN lemma_class TEXT NOT NULL DEFAULT 'content'")


def classify(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    ensure_column(conn)

    # Reset, then apply the two signals. Reset keeps the pass idempotent and correct if
    # a lemma's senses changed between runs.
    conn.execute("UPDATE lemmas SET lemma_class = 'content'")
    conn.execute("UPDATE lemmas SET lemma_class = 'name' WHERE pos = 'name'")

    # Gloss signal: non-name-POS lemmas whose EVERY sense matches a name marker.
    like = " OR ".join("s.gloss LIKE ?" for _ in NAME_GLOSS_LIKE)
    conn.execute(
        f"""
        UPDATE lemmas SET lemma_class = 'name'
        WHERE lemma_class = 'content' AND pos IS NOT 'name' AND id IN (
            SELECT l.id FROM lemmas l JOIN senses s ON s.lemma_id = l.id
            WHERE l.pos IS NOT 'name'
            GROUP BY l.id
            HAVING COUNT(*) = SUM(CASE WHEN {like} THEN 1 ELSE 0 END)
        )
        """,
        NAME_GLOSS_LIKE,
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lemmas_class ON lemmas (lemma_class)")
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM lemmas").fetchone()[0]
    names = conn.execute("SELECT COUNT(*) FROM lemmas WHERE lemma_class = 'name'").fetchone()[0]
    by_pos_name = conn.execute("SELECT COUNT(*) FROM lemmas WHERE pos = 'name'").fetchone()[0]
    conn.close()
    return {
        "total_lemmas": total,
        "name_lemmas": names,
        "content_lemmas": total - names,
        "name_share": round(names / total, 4) if total else 0.0,
        "by_pos_tag": by_pos_name,
        "by_gloss_only": names - by_pos_name,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Tag lemmas as content vs proper-name (F37).")
    ap.add_argument("--db", default=os.path.join("data", "db", "lexorama.sqlite"))
    args = ap.parse_args()
    if not os.path.exists(args.db):
        sys.exit(f"DB not found: {args.db}")
    import json
    print(json.dumps(classify(args.db), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
