"""Rebuild the `etymons` chain from already-stored el prose — multi-hop upgrade.

The original ingest parsed only the IMMEDIATE ancestor out of the Greek prose
etymology ("headword < αρχαία ελληνική X"), so ~97% of lemmas carried a single
etymon and the graph showed no diachronic depth. `parse_el_etymology_prose` now
walks the WHOLE " < " chain (grc → grc-koi → ine-pro …); this script re-applies
it to the prose ALREADY in the `etymology` table, so we get the full chains
WITHOUT re-streaming the 1.4 GB Kaikki dump.

Faithful to `store_etymology`'s precedence (el overrides en):
  · For a lemma whose el prose now yields etymons → delete ALL its etymons and
    reinsert the el chain (el wins over any en-template etymons).
  · For a lemma whose el prose now yields NOTHING (redirect / pure internal
    derivation / "λείπει η ετυμολογία") → delete only its STALE el etymons,
    leaving any en-template etymons intact.
  · en-template etymons are otherwise never touched.

Idempotent: re-running reproduces the same rows. Deterministic (regex over
stored text). The API holds the WAL DB — STOP it before running, restart after.
Run:  python -m pipelines.ingest.reparse_etymology [--dry-run]
"""

from __future__ import annotations

import argparse
import collections
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(__file__))
from ingest_kaikki import parse_el_etymology_prose  # noqa: E402

DB = "data/db/lexorama.sqlite"
SOURCE = "el-wiktionary"


def reparse(db_path: str, dry_run: bool = False) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    before = conn.execute(
        "SELECT count(*) FROM etymons WHERE source=?", (SOURCE,)
    ).fetchone()[0]

    rows = conn.execute(
        "SELECT lemma_id, text FROM etymology WHERE source=? AND text IS NOT NULL",
        (SOURCE,),
    ).fetchall()

    inserted = 0
    lemmas_with_chain = 0          # el lemmas that now carry ≥1 etymon
    lemmas_multi = 0               # …of which ≥2 (a real chain)
    cleared_stale = 0             # el lemmas whose prose now yields nothing
    depth = collections.Counter()  # chain-length histogram

    for r in rows:
        etymons = parse_el_etymology_prose(r["text"])
        lid = r["lemma_id"]
        if etymons:
            depth[len(etymons)] += 1
            lemmas_with_chain += 1
            if len(etymons) >= 2:
                lemmas_multi += 1
            if not dry_run:
                # el overrides all (mirror store_etymology): drop en + old el rows
                conn.execute("DELETE FROM etymons WHERE lemma_id=?", (lid,))
                conn.executemany(
                    "INSERT INTO etymons (lemma_id, relation, lang_code, term, source, seq) "
                    "VALUES (?,?,?,?,?,?)",
                    [(lid, rel, lang, term, SOURCE, seq) for (rel, lang, term, seq) in etymons],
                )
            inserted += len(etymons)
        else:
            # prose no longer yields a typed ancestor → drop stale el etymons only
            if not dry_run:
                cur = conn.execute(
                    "DELETE FROM etymons WHERE lemma_id=? AND source=?", (lid, SOURCE)
                )
                if cur.rowcount:
                    cleared_stale += 1
            else:
                if conn.execute(
                    "SELECT 1 FROM etymons WHERE lemma_id=? AND source=? LIMIT 1",
                    (lid, SOURCE),
                ).fetchone():
                    cleared_stale += 1

    if not dry_run:
        conn.commit()
    after = conn.execute(
        "SELECT count(*) FROM etymons WHERE source=?", (SOURCE,)
    ).fetchone()[0]
    conn.close()

    return {
        "el_prose_rows": len(rows),
        "el_etymons_before": before,
        "el_etymons_after": after if not dry_run else "(dry-run)",
        "el_etymons_inserted": inserted,
        "lemmas_with_chain": lemmas_with_chain,
        "lemmas_multihop": lemmas_multi,
        "stale_el_cleared": cleared_stale,
        "depth_histogram": {k: depth[k] for k in sorted(depth)},
        "dry_run": dry_run,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    s = reparse(args.db, dry_run=args.dry_run)
    print(
        f"el prose rows scanned: {s['el_prose_rows']}\n"
        f"el etymons before: {s['el_etymons_before']}  after: {s['el_etymons_after']}  "
        f"inserted: {s['el_etymons_inserted']}\n"
        f"lemmas with a chain: {s['lemmas_with_chain']}  (multi-hop ≥2: {s['lemmas_multihop']})\n"
        f"stale el rows cleared: {s['stale_el_cleared']}\n"
        f"depth histogram: {s['depth_histogram']}  (dry_run={s['dry_run']})",
        file=sys.stderr,
    )
    import json
    print(json.dumps({k: v for k, v in s.items() if k != "depth_histogram"}))


if __name__ == "__main__":
    main()
