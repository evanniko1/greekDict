"""Fill missing inflection cells with the validated paradigm engine.

This is the *write* counterpart to `validate_paradigms.py`. Validation has shown
every enabled class clears a ≥0.97 precision bar against real Wiktionary forms;
this script generates the paradigm for each in-scope lemma and inserts ONLY the
cells that are still missing, tagged `source='generated'`.

Hard guarantees (so we never corrupt sourced data):
  · fill-missing-only — a generated form is inserted for a cell ONLY when no
    stored form already carries that cell signature (`_cell_key`). Wiktionary
    always wins; we never overwrite or duplicate a sourced cell.
  · idempotent — re-running first deletes every prior `source='generated'` row,
    so the backfill can be replayed after an engine change without drift.
  · the engine itself refuses anything out of scope (multiword, Latin letters,
    hiatus-ambiguous lemmas, unsupported endings) and returns [].

The API holds the SQLite WAL DB, so STOP it before running and restart after.
Run:  python -m pipelines.ingest.backfill_paradigms
Then rebuild the search index:  python -m pipelines.ingest.build_search_index
"""

from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys

from .paradigm_engine import generate
from .normalize_greek import normalize
from .validate_paradigms import _cell_key, _class_of

DB = "data/db/lexorama.sqlite"
SOURCE = "generated"


def backfill(db_path: str, dry_run: bool = False) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # idempotent: clear prior generated rows so an engine change replays cleanly
    prior = conn.execute("SELECT count(*) FROM forms WHERE source=?", (SOURCE,)).fetchone()[0]
    if not dry_run:
        conn.execute("DELETE FROM forms WHERE source=?", (SOURCE,))

    lemmas = conn.execute(
        "SELECT id, lemma, pos, gender FROM lemmas WHERE pos IN ('noun','adj','verb')"
    ).fetchall()

    per_class = collections.defaultdict(lambda: {"lemmas": 0, "inserted": 0})
    inserted = 0
    rows: list[tuple] = []

    for r in lemmas:
        gen_forms = generate(r["lemma"], r["pos"], r["gender"])
        if not gen_forms:
            continue
        # existing cell signatures for this lemma (from ANY source)
        stored = conn.execute(
            "SELECT features FROM forms WHERE lemma_id=?", (r["id"],)
        ).fetchall()
        have_keys = set()
        for s in stored:
            try:
                tags = json.loads(s["features"]) if s["features"] else []
            except Exception:
                tags = []
            k = _cell_key(tags)
            if k != (None, None, None):
                have_keys.add(k)

        cls = _class_of(r["lemma"], r["pos"], r["gender"])
        added_here = 0
        added_keys = set()  # guard against intra-paradigm key collisions
        for form, tags in gen_forms:
            key = _cell_key(tags)
            if key == (None, None, None) or key in have_keys or key in added_keys:
                continue
            added_keys.add(key)
            rows.append((r["id"], form, normalize(form), json.dumps(tags), SOURCE))
            added_here += 1

        if added_here:
            per_class[cls]["lemmas"] += 1
            per_class[cls]["inserted"] += added_here
            inserted += added_here

    if not dry_run and rows:
        conn.executemany(
            "INSERT INTO forms (lemma_id, form, normalized_form, features, source) "
            "VALUES (?,?,?,?,?)",
            rows,
        )
        conn.commit()
    conn.close()

    return {
        "prior_generated_deleted": prior if not dry_run else 0,
        "inserted": inserted,
        "dry_run": dry_run,
        "per_class": {k: dict(v) for k, v in sorted(per_class.items())},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--dry-run", action="store_true", help="count only, write nothing")
    args = ap.parse_args()
    stats = backfill(args.db, dry_run=args.dry_run)
    print(f"{'class':12} {'lemmas':>8} {'inserted':>10}", file=sys.stderr)
    for cls, s in stats["per_class"].items():
        print(f"{cls:12} {s['lemmas']:>8} {s['inserted']:>10}", file=sys.stderr)
    print(
        f"\nprior generated rows deleted: {stats['prior_generated_deleted']}\n"
        f"total cells inserted: {stats['inserted']}  (dry_run={stats['dry_run']})",
        file=sys.stderr,
    )
    print(json.dumps({k: v for k, v in stats.items() if k != "per_class"}))


if __name__ == "__main__":
    main()
