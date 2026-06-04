"""Measure paradigm-engine precision against real Wiktionary forms.

For every lemma that ALREADY has sourced forms, generate the paradigm and check
each generated cell against the stored form(s) carrying the same case/number(+
gender) tags. Reports per-class:
  · cells     — generated cells that had a stored form to compare against
  · agree     — generated form matched a stored form for that cell
  · precision — agree / cells
  · misses    — a few example disagreements for inspection

This is the gate: a class is only enabled in the backfill once precision is high
(we use a ≥0.97 bar). Run:  python -m pipelines.ingest.validate_paradigms
"""

from __future__ import annotations

import collections
import sqlite3
import json
import os
import unicodedata

from .paradigm_engine import generate
from .greek_accent import strip_tonos

DB = os.path.join("data", "db", "lexorama.sqlite")

CASE_NUM = {"nominative", "genitive", "accusative", "vocative", "singular", "plural"}
GENDERS = {"masculine", "feminine", "neuter"}


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


PERSONS = {"first-person", "second-person", "third-person"}


def _cell_key(tags: list[str]) -> tuple:
    """The signature we compare cells on — ignore extra/derived tags.

    For nominals: (case, number, gender?). For finite verbs (a person tag is
    present): ("V", person, number) keyed on the present-active-indicative cell
    so we can score conjugation against stored Wiktionary forms."""
    t = {x.lower() for x in tags}
    person = next((p for p in PERSONS if p in t), None)
    num = "plural" if "plural" in t else ("singular" if "singular" in t else None)
    if person:
        # only score the cells our engine generates: present indicative active
        if "present" in t and "indicative" in t and "active" in t:
            return ("V", person, num)
        return (None, None, None)
    case = next((c for c in ("nominative", "genitive", "accusative", "vocative") if c in t), None)
    gen = next((g for g in GENDERS if g in t), None)
    return (case, num, gen)


def _class_of(lemma: str, pos: str, gender: str | None) -> str:
    p = pos.lower()
    if p == "verb":
        return "verb:present"
    if p == "adj":
        return "adj:-ος"
    g = (gender or "")[:1]
    for suf in ("μα", "ος", "ό", "ο", "α", "ά", "η", "ή", "ι", "ί"):
        if lemma.endswith(suf):
            return f"noun:-{suf}"
    return "noun:?"


def main(limit_per_class: int = 100000):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, lemma, pos, gender FROM lemmas WHERE pos IN ('noun','adj','verb')"
    ).fetchall()

    stats = collections.defaultdict(lambda: {"cells": 0, "agree": 0, "lemmas": 0, "miss": []})

    for r in rows:
        gen_forms = generate(r["lemma"], r["pos"], r["gender"])
        if not gen_forms:
            continue
        stored = conn.execute(
            "SELECT form, features FROM forms WHERE lemma_id=?", (r["id"],)
        ).fetchall()
        if not stored:
            continue
        # stored cell → set of accepted forms (NFC, accents kept)
        cell_forms: dict[tuple, set] = collections.defaultdict(set)
        for s in stored:
            try:
                tags = json.loads(s["features"]) if s["features"] else []
            except Exception:
                tags = []
            key = _cell_key(tags)
            if key[0] and key[1]:
                cell_forms[key].add(_nfc(s["form"]))
        if not cell_forms:
            continue
        cls = _class_of(r["lemma"], r["pos"], r["gender"])
        stats[cls]["lemmas"] += 1
        for form, tags in gen_forms:
            key = _cell_key(tags)
            # Skip the citation cell: nom-sg (masc/none) often stores comparative
            # / alternate headwords (ελληνικότερος) under the same tags, which the
            # engine can't and shouldn't reproduce — counting it just adds noise.
            if key[0] == "nominative" and key[1] == "singular" and key[2] in (None, "masculine"):
                continue
            if key not in cell_forms:
                continue
            stats[cls]["cells"] += 1
            if _nfc(form) in cell_forms[key]:
                stats[cls]["agree"] += 1
            elif len(stats[cls]["miss"]) < 8:
                stats[cls]["miss"].append(
                    f"{r['lemma']} {key[0][:3]}.{key[1][:2]} gen={form} ≠ {sorted(cell_forms[key])}"
                )

    print(f"{'class':12} {'lemmas':>7} {'cells':>7} {'agree':>7} {'prec':>6}")
    for cls in sorted(stats):
        s = stats[cls]
        prec = s["agree"] / s["cells"] if s["cells"] else 0.0
        print(f"{cls:12} {s['lemmas']:>7} {s['cells']:>7} {s['agree']:>7} {prec:>6.3f}")
    print()
    for cls in sorted(stats):
        if stats[cls]["miss"]:
            print(f"-- {cls} sample misses --")
            for m in stats[cls]["miss"]:
                print("  ", m)


if __name__ == "__main__":
    main()
