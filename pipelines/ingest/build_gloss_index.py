"""Build the cross-language (en→el) lookup index for bilingual mode (#39).

The en-Wiktionary edition gives an English gloss for ~32k Greek lemmas — e.g.
αετός → "eagle; kite (toy)", οστό → "bone (part of skeleton)". This pipeline lets
a user type an English word and land on the Greek lemma: for each English gloss it
extracts the clean LEADING headword phrase(s) — the actual translation, not the
parenthetical clarification — and maps them back to the lemma in `gloss_index`.

Extraction is deliberately conservative (precision over recall): a noisy en→el row
sends a searcher to the wrong word, which is worse than no row. So we:
  • skip cross-reference glosses ("for the constellation see …", "alternative form
    of …", "inflection of …") — they're not translations;
  • drop parentheticals and keep only the head of each ';'/',' -separated clause;
  • accept only short ASCII phrases (1–3 words, letters/space/hyphen/apostrophe),
    so Greek text or long definitions never leak into the index;
  • weight the first clause of a gloss above later ones (the primary translation).

The Greek dictionary stays primary; this is a lookup aid and every row keeps its
'en-wiktionary' provenance. Idempotent: clears and rewrites `gloss_index`.

Run (STOP the API first — writes the WAL DB):
    PYTHONIOENCODING=utf-8 python pipelines/ingest/build_gloss_index.py \
        --db data/db/lexorama.sqlite
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipelines", "ingest"))
from ingest_kaikki import init_db  # noqa: E402

# Glosses that are cross-references / form-of pointers, not translations.
_SKIP_RE = re.compile(
    r"\b(see|alternative (form|spelling) of|obsolete (form|spelling) of|"
    r"synonym of|misspelling of|inflection of|genitive of|plural of|"
    r"vocative of|accusative of|diminutive of|abbreviation of|initialism of|"
    r"clipping of|contraction of|surname|given name)\b",
    re.IGNORECASE,
)
_PARENS = re.compile(r"\([^)]*\)")
_VALID = re.compile(r"^[a-z][a-z'\- ]*[a-z]$")
# Bare function words that are never a useful standalone lookup key.
_STOP = {
    "of", "the", "a", "an", "to", "and", "or", "for", "in", "on", "at", "by",
    "with", "as", "from", "that", "this", "it", "its", "etc", "esp", "e.g",
}
_ARTICLE = re.compile(r"^(a|an|the|to)\s+")


def _phrases(gloss: str) -> list[str]:
    """Extract clean candidate English headword phrases from one gloss, in order
    (first = primary translation). Returns [] for cross-references / unusable text."""
    g = gloss.strip()
    if not g or _SKIP_RE.search(g):
        return []
    g = _PARENS.sub("", g).lower()
    out: list[str] = []
    seen: set[str] = set()
    for clause in re.split(r"[;,/]", g):
        p = clause.strip()
        p = _ARTICLE.sub("", p).strip()
        p = re.sub(r"\s+", " ", p)
        if not p or len(p) < 2 or len(p) > 40:
            continue
        if p.count(" ") > 2:        # at most 3 words
            continue
        if not _VALID.match(p):     # ASCII letters/space/hyphen/apostrophe only
            continue
        if p in _STOP or all(w in _STOP for w in p.split()):
            continue
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def build(db_path: str) -> dict:
    conn = init_db(db_path)  # applies schema.sql (idempotent) → ensures gloss_index
    conn.row_factory = sqlite3.Row
    conn.execute("DELETE FROM gloss_index")

    rows = conn.execute(
        "SELECT lemma_id, gloss, sense_index, source FROM senses "
        "WHERE source LIKE 'en%' AND gloss IS NOT NULL AND gloss != ''"
    ).fetchall()

    # (en_term, lemma_id) → best rank_weight, so duplicates collapse to the
    # strongest signal (a term that is some lemma's PRIMARY translation wins).
    best: dict[tuple[str, int], tuple[float, str]] = {}
    for r in rows:
        terms = _phrases(r["gloss"])
        for pos, term in enumerate(terms):
            # 1.0 for the gloss's leading translation, decaying for later clauses.
            w = round(1.0 / (1.0 + pos), 4)
            k = (term, r["lemma_id"])
            cur = best.get(k)
            if cur is None or w > cur[0]:
                best[k] = (w, r["source"])

    conn.executemany(
        "INSERT INTO gloss_index (en_term, lemma_id, rank_weight, source) VALUES (?,?,?,?)",
        [(term, lid, w, src) for (term, lid), (w, src) in best.items()],
    )
    conn.commit()

    n = conn.execute("SELECT COUNT(*) FROM gloss_index").fetchone()[0]
    terms = conn.execute("SELECT COUNT(DISTINCT en_term) FROM gloss_index").fetchone()[0]
    lemmas = conn.execute("SELECT COUNT(DISTINCT lemma_id) FROM gloss_index").fetchone()[0]
    conn.close()
    return {"rows": n, "distinct_terms": terms, "lemmas_covered": lemmas,
            "en_senses_scanned": len(rows)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Build en→el cross-language index (#39).")
    ap.add_argument("--db", default="data/db/lexorama.sqlite")
    args = ap.parse_args()
    stats = build(args.db)
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
