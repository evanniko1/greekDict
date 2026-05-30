"""Stream a Kaikki Greek JSONL dump into the SQLite lexical store.

IMPORTANT (token economy): this script is meant to be run by the user in a
terminal against a multi-hundred-MB file. The dump is NEVER read into an LLM
context — it is processed one line at a time. Use --limit while iterating so
you can validate on a few thousand entries before a full run.

Usage:
    python ingest_kaikki.py --input data/raw/el-extract.jsonl --source el-wiktionary --db data/db/lexorama.sqlite
    python ingest_kaikki.py --input data/raw/en-extract.jsonl --source en-wiktionary --db data/db/lexorama.sqlite

Run el first, then en — en entries merge onto existing el lemmas by
(normalized_lemma, pos).
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(__file__))
from normalize_greek import normalize  # noqa: E402

HERE = os.path.dirname(__file__)
SCHEMA = os.path.join(HERE, "schema.sql")


def init_db(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    with open(SCHEMA, "r", encoding="utf-8") as fh:
        conn.executescript(fh.read())
    return conn


def upsert_lemma(conn: sqlite3.Connection, lemma: str, pos: str, gender: str, source: str) -> int:
    norm = normalize(lemma)
    cur = conn.execute(
        "SELECT id, sources FROM lemmas WHERE normalized_lemma = ? AND pos IS ?",
        (norm, pos),
    )
    row = cur.fetchone()
    if row:
        lemma_id, sources = row
        srcs = set((sources or "").split(",")) - {""}
        if source not in srcs:
            srcs.add(source)
            conn.execute("UPDATE lemmas SET sources = ? WHERE id = ?", (",".join(sorted(srcs)), lemma_id))
        return lemma_id
    cur = conn.execute(
        "INSERT INTO lemmas (lemma, normalized_lemma, pos, gender, sources) VALUES (?,?,?,?,?)",
        (lemma, norm, pos, gender, source),
    )
    return cur.lastrowid


def parse_gender(entry: dict) -> str | None:
    for form in entry.get("forms", []):
        tags = form.get("tags") or []
        for g in ("masculine", "feminine", "neuter"):
            if g in tags:
                return g
    return None


def ingest(input_path: str, source: str, db_path: str, limit: int | None) -> dict:
    conn = init_db(db_path)
    stats = {"lines": 0, "lemmas": 0, "senses": 0, "forms": 0, "skipped": 0}
    with open(input_path, "r", encoding="utf-8") as fh:
        for line in fh:
            if limit is not None and stats["lines"] >= limit:
                break
            line = line.strip()
            if not line:
                continue
            stats["lines"] += 1
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                stats["skipped"] += 1
                continue

            word = entry.get("word")
            if not word:
                stats["skipped"] += 1
                continue
            # en dump is multilingual; keep only Greek. el dump is already Greek.
            if entry.get("lang_code") not in (None, "el"):
                stats["skipped"] += 1
                continue

            pos = entry.get("pos")
            gender = parse_gender(entry)
            lemma_id = upsert_lemma(conn, word, pos, gender, source)
            stats["lemmas"] += 1

            for i, sense in enumerate(entry.get("senses", [])):
                glosses = sense.get("glosses") or sense.get("raw_glosses") or []
                if not glosses:
                    continue
                examples = [ex.get("text") for ex in sense.get("examples", []) if ex.get("text")]
                conn.execute(
                    "INSERT INTO senses (lemma_id, sense_index, gloss, tags, examples, source) VALUES (?,?,?,?,?,?)",
                    (lemma_id, i, "; ".join(glosses), json.dumps(sense.get("tags", []), ensure_ascii=False),
                     json.dumps(examples, ensure_ascii=False), source),
                )
                stats["senses"] += 1

            seen_forms: set[str] = set()
            for form in entry.get("forms", []):
                ftext = form.get("form")
                if not ftext or ftext in ("-", word):
                    continue
                tags = form.get("tags") or []
                if "table-tags" in tags or "inflection-template" in tags:
                    continue
                key = (ftext, tuple(tags))
                if key in seen_forms:
                    continue
                seen_forms.add(key)
                conn.execute(
                    "INSERT INTO forms (lemma_id, form, normalized_form, features, source) VALUES (?,?,?,?,?)",
                    (lemma_id, ftext, normalize(ftext), json.dumps(tags, ensure_ascii=False), source),
                )
                stats["forms"] += 1

            if stats["lines"] % 5000 == 0:
                conn.commit()
                print(f"  ...{stats['lines']} lines", file=sys.stderr)

    conn.commit()
    conn.close()
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest a Kaikki Greek JSONL dump into SQLite.")
    ap.add_argument("--input", required=True)
    ap.add_argument("--source", required=True, choices=["el-wiktionary", "en-wiktionary"])
    ap.add_argument("--db", default="data/db/lexorama.sqlite")
    ap.add_argument("--limit", type=int, default=None, help="Stop after N lines (for quick validation).")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        sys.exit(f"Input not found: {args.input}\nRun pipelines/download_data.ps1 (or .sh) first.")

    print(f"Ingesting {args.input} as {args.source} -> {args.db}", file=sys.stderr)
    stats = ingest(args.input, args.source, args.db, args.limit)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
