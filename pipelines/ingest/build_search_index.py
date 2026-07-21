"""Populate search_index from lemmas + forms after ingest.

Lemmas rank above forms; forms carry their grammatical features so the API can
render the "ανθρώπων → άνθρωπος, genitive plural" resolution card.

Usage:
    python build_search_index.py --db data/db/lexorama.sqlite
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(__file__))
import manifest  # noqa: E402


def build(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM search_index")

    conn.execute(
        """
        INSERT INTO search_index (normalized_surface, surface, lemma_id, surface_type, features, rank_weight)
        SELECT normalized_lemma, lemma, id, 'lemma', NULL, 1.0 FROM lemmas
        """
    )
    conn.execute(
        """
        INSERT INTO search_index (normalized_surface, surface, lemma_id, surface_type, features, rank_weight)
        SELECT normalized_form, form, lemma_id, 'form', features, 0.7 FROM forms
        """
    )
    conn.commit()
    n = conn.execute("SELECT count(*) FROM search_index").fetchone()[0]
    by_type = dict(conn.execute("SELECT surface_type, count(*) FROM search_index GROUP BY surface_type").fetchall())
    conn.close()
    return {"total": n, "by_type": by_type}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/db/lexorama.sqlite")
    args = ap.parse_args()
    stats = build(args.db)
    conn = sqlite3.connect(args.db)
    manifest.record_build(conn, "build_search_index", tables=["search_index"])
    conn.close()
    print(json.dumps(stats, indent=2), file=sys.stderr)
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
