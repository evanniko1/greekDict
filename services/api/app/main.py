"""Λεξόραμα API (M0/M1).

The core endpoint is /api/search: it resolves a raw Greek (or Greeklish) query
to a lemma and, crucially, EXPLAINS the match — e.g. an inflected form maps back
to its lemma with grammatical features. That resolution+explanation is the whole
point of the product.

Run:
    uvicorn services.api.app.main:app --reload
    (set LEXORAMA_DB to point at the sqlite file; defaults to data/db/lexorama.sqlite)
"""

from __future__ import annotations

import json
import os
import sqlite3

from fastapi import FastAPI, HTTPException, Query

# Make the normalization module importable from the pipeline package.
import sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipelines", "ingest"))
from normalize_greek import normalize, greeklish_to_greek  # noqa: E402

DB_PATH = os.environ.get("LEXORAMA_DB", os.path.join(ROOT, "data", "db", "lexorama.sqlite"))

app = FastAPI(title="Λεξόραμα API", version="0.1.0")


def db() -> sqlite3.Connection:
    if not os.path.exists(DB_PATH):
        raise HTTPException(503, f"Database not built. Expected at {DB_PATH}. Run the ingest pipeline.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _features_label(features_json: str | None) -> str | None:
    if not features_json:
        return None
    try:
        tags = json.loads(features_json)
    except (json.JSONDecodeError, TypeError):
        return None
    return ", ".join(tags) if tags else None


@app.get("/api/search")
def search(q: str = Query(..., min_length=1), limit: int = 10):
    """Resolve a query to ranked lemma candidates, each with a match explanation."""
    conn = db()
    key = normalize(q)

    # Candidate keys, in priority order. Greeklish is a fallback widening.
    candidates: list[tuple[str, str]] = [(key, "direct")]
    gk = normalize(greeklish_to_greek(q))
    if gk and gk != key:
        candidates.append((gk, "greeklish"))

    seen: set[int] = set()
    results = []
    for cand_key, via in candidates:
        rows = conn.execute(
            """
            SELECT si.lemma_id, si.surface, si.surface_type, si.features, si.rank_weight,
                   l.lemma, l.pos, l.gender
            FROM search_index si JOIN lemmas l ON l.id = si.lemma_id
            WHERE si.normalized_surface = ?
            ORDER BY si.rank_weight DESC
            """,
            (cand_key,),
        ).fetchall()
        for r in rows:
            if r["lemma_id"] in seen:
                continue
            seen.add(r["lemma_id"])
            is_form = r["surface_type"] == "form"
            feat = _features_label(r["features"])
            if is_form:
                match_type = "inflected_form"
                explanation = f"{r['surface']} → {r['lemma']}"
                if feat:
                    explanation += f" ({feat})"
            else:
                match_type = "lemma" if via == "direct" else "greeklish"
                explanation = r["lemma"]
            snippet_row = conn.execute(
                "SELECT gloss FROM senses WHERE lemma_id = ? ORDER BY sense_index LIMIT 1",
                (r["lemma_id"],),
            ).fetchone()
            results.append({
                "lemma_id": r["lemma_id"],
                "lemma": r["lemma"],
                "pos": r["pos"],
                "gender": r["gender"],
                "match_type": match_type,
                "matched_surface": r["surface"],
                "features": feat,
                "explanation": explanation,
                "via": via,
                "score": round(float(r["rank_weight"]), 3),
                "snippet": snippet_row["gloss"] if snippet_row else None,
            })
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break

    conn.close()
    return {"query": q, "normalized": key, "resolved": bool(results), "results": results}


@app.get("/api/word/{lemma}")
def word(lemma: str):
    """Full word-page payload for a lemma (accent-insensitive lookup)."""
    conn = db()
    key = normalize(lemma)
    lrows = conn.execute(
        "SELECT * FROM lemmas WHERE normalized_lemma = ? ORDER BY id", (key,)
    ).fetchall()
    if not lrows:
        conn.close()
        raise HTTPException(404, f"No lemma for '{lemma}'.")

    payloads = []
    for l in lrows:
        senses = conn.execute(
            "SELECT sense_index, gloss, tags, examples, source FROM senses WHERE lemma_id = ? ORDER BY sense_index",
            (l["id"],),
        ).fetchall()
        forms = conn.execute(
            "SELECT form, features, source FROM forms WHERE lemma_id = ? ORDER BY id", (l["id"],)
        ).fetchall()
        payloads.append({
            "lemma_id": l["id"],
            "lemma": l["lemma"],
            "pos": l["pos"],
            "gender": l["gender"],
            "sources": (l["sources"] or "").split(","),
            "senses": [
                {
                    "index": s["sense_index"],
                    "gloss": s["gloss"],
                    "tags": json.loads(s["tags"] or "[]"),
                    "examples": json.loads(s["examples"] or "[]"),
                    "source": s["source"],
                }
                for s in senses
            ],
            "forms": [
                {"form": f["form"], "features": json.loads(f["features"] or "[]"), "source": f["source"]}
                for f in forms
            ],
        })
    conn.close()
    return {"lemma": lemma, "entries": payloads}


@app.get("/api/word/{lemma}/graph")
def word_graph(lemma: str):
    """Minimal graph payload (M0 stub): explicit relations from the store.

    Real semantic neighbours (WordNet, embeddings) land in M4. For now this
    returns whatever typed relations ingest captured, so the frontend graph
    component can be built against a stable shape.
    """
    conn = db()
    key = normalize(lemma)
    lrow = conn.execute("SELECT id, lemma FROM lemmas WHERE normalized_lemma = ? LIMIT 1", (key,)).fetchone()
    if not lrow:
        conn.close()
        raise HTTPException(404, f"No lemma for '{lemma}'.")
    rels = conn.execute(
        "SELECT target_text, relation_type, weight, source FROM relations WHERE source_lemma_id = ? LIMIT 20",
        (lrow["id"],),
    ).fetchall()
    nodes = [{"id": lrow["lemma"], "label": lrow["lemma"], "type": "current"}]
    edges = []
    for r in rels:
        if not r["target_text"]:
            continue
        nodes.append({"id": r["target_text"], "label": r["target_text"], "type": r["relation_type"]})
        edges.append({
            "source": lrow["lemma"], "target": r["target_text"],
            "type": r["relation_type"], "weight": r["weight"], "source_name": r["source"],
        })
    conn.close()
    return {"nodes": nodes, "edges": edges}


@app.get("/api/health")
def health():
    return {"ok": True, "db": DB_PATH, "db_exists": os.path.exists(DB_PATH)}
