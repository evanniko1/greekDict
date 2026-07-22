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
import datetime
import html
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(__file__))
from normalize_greek import normalize  # noqa: E402
import manifest  # noqa: E402

HERE = os.path.dirname(__file__)
SCHEMA = os.path.join(HERE, "schema.sql")


def init_db(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    with open(SCHEMA, "r", encoding="utf-8") as fh:
        conn.executescript(fh.read())
    return conn


# CC BY-SA + GFDL attribution metadata, one row per data source. Wiktionary text
# is dual-licensed CC BY-SA 4.0 / GFDL; we extract via Kaikki (wiktextract) and
# restructure it, so the notice must flag that the data was modified. This is the
# compliance backbone of "AI explains; sources define" — recorded once per source,
# surfaced centrally in the UI (site footer + /licensing) rather than per term.
SOURCE_META: dict[str, dict[str, str]] = {
    "el-wiktionary": {
        "source_url": "https://el.wiktionary.org/",
        "license": "CC BY-SA 4.0 / GFDL",
        "attribution_text": (
            "Λεξικογραφικά δεδομένα από το Βικιλεξικό (el.wiktionary.org), "
            "© συντάκτες του Βικιλεξικού, διαθέσιμα υπό τις άδειες CC BY-SA 4.0 "
            "και GFDL· εξαγωγή μέσω Kaikki.org (wiktextract). Τα δεδομένα έχουν "
            "τροποποιηθεί (ανάλυση, ομαδοποίηση σε πίνακες κλίσης, μετάφραση ετικετών)."
        ),
    },
    "en-wiktionary": {
        "source_url": "https://en.wiktionary.org/",
        "license": "CC BY-SA 4.0 / GFDL",
        "attribution_text": (
            "Lexical data from Wiktionary (en.wiktionary.org), © Wiktionary "
            "contributors, available under CC BY-SA 4.0 and GFDL; extracted via "
            "Kaikki.org (wiktextract). The data has been modified (parsing, grouping "
            "into inflection tables, translation of grammatical labels)."
        ),
    },
    "opensubtitles-freq": {
        "source_url": "https://github.com/hermitdave/FrequencyWords",
        "license": "CC BY-SA 4.0",
        "attribution_text": (
            "Δεδομένα συχνότητας λέξεων από τη λίστα FrequencyWords (hermitdave), "
            "παραγόμενη από το σώμα υποτίτλων OpenSubtitles, διαθέσιμα υπό την άδεια "
            "CC BY-SA 4.0. Οι συχνότητες έχουν συναθροιστεί ανά λήμμα (άθροισμα των "
            "κλιτών τύπων) και κατηγοριοποιηθεί σε ζώνες συχνότητας."
        ),
    },
    "omw-el": {
        "source_url": "https://github.com/omwn/omw-data",
        "license": "Apache-2.0 (omw-el) / WordNet 3.0 License (Princeton omw-en)",
        "attribution_text": (
            "Σημασιολογικές σχέσεις (συνώνυμα, υπερώνυμα/υπώνυμα) από το Ελληνικό "
            "WordNet (omw-el, Open Multilingual Wordnet) υπό την άδεια Apache-2.0. "
            "Η ταξινομική δομή (ιεραρχία is-a) προέρχεται από το Princeton WordNet "
            "(omw-en, χρησιμοποιούμενο ως δομή expand) υπό την άδεια WordNet 3.0. "
            "Οι σχέσεις έχουν αντιστοιχιστεί σε μονολεκτικά λήμματα με ταίριασμα "
            "μέρους του λόγου· πολυλεκτικά μέλη synset παραλείπονται."
        ),
    },
    "leipzig-coocc": {
        "source_url": "https://wortschatz.uni-leipzig.de/en/download/Modern%20Greek",
        "license": "CC BY-NC 4.0",
        "attribution_text": (
            "Δεδομένα συνεμφάνισης λέξεων (συνάψεις) από τα Corpora Collection "
            "του Wortschatz Leipzig (Πανεπιστήμιο της Λειψίας), διαθέσιμα υπό την "
            "άδεια CC BY-NC 4.0. Οι συνάψεις έχουν αντιστοιχιστεί σε λήμματα και "
            "ταξινομηθεί κατά ισχύ συσχέτισης (log-likelihood)."
        ),
    },
    "leipzig-examples": {
        "source_url": "https://wortschatz.uni-leipzig.de/en/download/Modern%20Greek",
        "license": "CC BY-NC 4.0",
        "attribution_text": (
            "Παραδείγματα χρήσης (αυθεντικές προτάσεις) από τα Corpora Collection "
            "του Wortschatz Leipzig (Πανεπιστήμιο της Λειψίας) — σώμα ειδησεογραφικού "
            "λόγου, διαθέσιμα υπό την άδεια CC BY-NC 4.0. Κάθε πρόταση έχει αντιστοιχιστεί "
            "σε λήμματα μέσω των τύπων της και επιλεγεί με κριτήρια αναγνωσιμότητας."
        ),
    },
    "leipzig-embeddings": {
        "source_url": "https://wortschatz.uni-leipzig.de/en/download/Modern%20Greek",
        "license": "CC BY-NC 4.0",
        "attribution_text": (
            "Σημασιολογικοί γείτονες από μοντέλο διανυσματικών αναπαραστάσεων λέξεων "
            "(word2vec) εκπαιδευμένο στο σώμα κειμένων Wortschatz Leipzig (Πανεπιστήμιο "
            "της Λειψίας), διαθέσιμο υπό την άδεια CC BY-NC 4.0. Οι γείτονες υπολογίζονται "
            "ως οι λέξεις με τα πλησιέστερα διανύσματα (ομοιότητα συνημιτόνου) και έχουν "
            "αντιστοιχιστεί σε λήμματα."
        ),
    },
}


def record_attribution(conn: sqlite3.Connection, source: str) -> None:
    """Upsert the CC BY-SA/GFDL attribution row for this source.

    Idempotent and keyed by source_name, so re-running ingest just refreshes
    retrieved_at. Skips gracefully if a source has no metadata defined.
    """
    meta = SOURCE_META.get(source)
    if not meta:
        return
    conn.execute(
        """
        INSERT INTO source_attributions
            (source_name, source_url, license, attribution_text, retrieved_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(source_name) DO UPDATE SET
            source_url = excluded.source_url,
            license = excluded.license,
            attribution_text = excluded.attribution_text,
            retrieved_at = excluded.retrieved_at
        """,
        (source, meta["source_url"], meta["license"], meta["attribution_text"],
         datetime.date.today().isoformat()),
    )


_GREEK = re.compile(r"[Ͱ-Ͽἀ-῿]")
# Template/markup debris that leaks out of Wiktionary inflection tables.
_FORM_JUNK = set("{}[]|_<>\\/*=")
# Guillemets and quote characters: Leipzig counts these as tokens, so a lemma that
# "owns" one absorbs hundreds of thousands of corpus tokens (audit F1).
_FORM_PUNCT = set("«»\"'“”‘’()،,.;:!?·—–-")


def is_admissible_form(ftext: str, lemma: str) -> bool:
    """Reject Wiktionary "forms" that are not actually inflected words (F1, F4).

    Nothing in the dump guarantees a `forms[].form` is a word. Punctuation, bare
    inflectional endings and the component tokens of multiword idioms all appear, and
    once stored they become searchable surfaces that absorb corpus tokens — the
    guillemets « » made περιπλέκω the 4th most "news-distinctive" word in Greek, and the
    bare endings ο/ος/ων made αισώπειος the #1 falling word (0.81% of the corpus).

    The rules are deliberately conservative: each rejects a class that cannot be a
    legitimate inflected form of `lemma`.
    """
    if not ftext:
        return False
    f = ftext.strip()
    if not f or f == "-" or f == lemma:
        return False
    # 1. Must contain at least one Greek letter. Drops punctuation-only surfaces,
    #    bare Latin glosses ('arse and pants') and romanizations stored as forms.
    if not _GREEK.search(f):
        return False
    # 2. Template debris.
    if any(ch in _FORM_JUNK for ch in f):
        return False
    # 3. Punctuation-only once Greek is stripped is covered by (1); this catches a
    #    form that is a real word glued to a quote mark.
    if any(ch in _FORM_PUNCT for ch in f):
        return False
    # 4. Bare inflectional endings. A long lemma cannot have a 1-3 character inflected
    #    form; requiring a gap of >=2 keeps genuinely short paradigms (έχω/είχα) intact.
    if len(f) <= 3 and (len(lemma) - len(f)) >= 2:
        return False
    # 5. Components of a multiword lemma. «με σκοπό να» must not own «με», «σκοπό», «να».
    if " " in lemma and " " not in f:
        return False
    return True


# Mediopassive (παθητική) markers for Modern Greek verbs. el-wiktionary omits the voice
# tag on 99% of verb forms, so active and mediopassive collapse into one grid cell for
# 33.9% of verbs (audit F3). Voice is the primary axis of the Greek verb, so it is
# recovered here from the form itself rather than left to the front end to guess.
_MP_FINITE = ("ομαι", "όμαι", "εσαι", "έσαι", "εται", "έται", "όμαστε", "ομαστε",
              "όσαστε", "εστε", "έστε", "ονται", "ούνται", "ούμαι", "άμαι",
              "όμουν", "όσουν", "όταν", "όμασταν", "όσασταν", "ονταν", "όντουσαν",
              # Colloquial imperfect variants carrying a final -α/-ε. Without these the
              # suffix test misses σκοτωνόμουνα/απτόσουνα/αβγοκοβότανε and the form is
              # tagged active, landing a mediopassive in the Ενεργητική grid.
              "όμουνα", "όσουνα", "ότανε", "όμασταν", "όντανε",
              # B-conjugation (contract) mediopassive: αγαπιέμαι, θυμιέσαι.
              "ιέμαι", "ιέσαι", "ιέται", "ιόμαστε", "ιέστε", "ιούνται",
              "ιόμουν", "ιόσουν", "ιόταν", "ιόμουνα", "ιόσουνα", "ιότανε")
_MP_AORIST = ("θηκα", "τηκα", "στηκα", "χτηκα", "φτηκα", "θήκαμε", "τήκαμε",
              "στήκαμε", "θηκες", "θηκε", "θήκατε", "θηκαν", "χτηκε", "φτηκε")
_MP_NONFINITE = ("θεί", "τεί", "στεί", "χτεί", "φτεί", "θούμε", "θούν",
                 "μένος", "μένη", "μένο")


def infer_voice(ftext: str, tags: list[str], pos: str) -> str | None:
    """Return 'passive' | 'active' | None for an untagged Greek verb form (F3).

    Returns None when the voice is already tagged, when the entry is not a verb, or
    when the form gives no morphological evidence — inventing a tag would be worse
    than leaving the cell untagged.
    """
    if pos != "verb":
        return None
    lowered = [t.lower() for t in tags]
    if "active" in lowered or "passive" in lowered or "middle" in lowered:
        return None
    if not ftext:
        return None
    # Periphrastic forms (έχω σκοτωθεί, θα σκοτωθώ): the lexical verb carries the voice.
    token = ftext.strip().split()[-1] if " " in ftext.strip() else ftext.strip()
    if not _GREEK.search(token):
        return None
    if token.endswith(_MP_AORIST) or token.endswith(_MP_FINITE) or token.endswith(_MP_NONFINITE):
        return "passive"
    # Only claim 'active' for recognisable active endings; silence otherwise.
    if token.endswith(("ω", "εις", "ει", "ουμε", "ετε", "ουν", "α", "ες", "ε",
                       "αμε", "ατε", "αν", "σω", "σεις", "σει", "ας", "ώ", "άς",
                       "εί", "ούμε", "είτε", "ούν")):
        return "active"
    return None


def find_lemma_id(conn: sqlite3.Connection, word: str, pos: str) -> int | None:
    """Resolve a dump entry to an existing lemma row, refusing to guess.

    Lemma identity is (lemma, pos) — the ACCENTED surface (R2 / audit F21). Matching
    on the accent-folded key alone would attach data to whichever homograph happened
    to be inserted first (νόμος "law" vs νομός "prefecture"). We therefore try the
    exact surface first, and fall back to the folded key only when it is unambiguous;
    an ambiguous fold returns None so the caller counts it unmatched rather than
    silently corrupting the wrong word.
    """
    row = conn.execute(
        "SELECT id FROM lemmas WHERE lemma = ? AND pos IS ?", (word, pos)
    ).fetchone()
    if row:
        return row[0]
    rows = conn.execute(
        "SELECT id FROM lemmas WHERE normalized_lemma = ? AND pos IS ?",
        (normalize(word), pos),
    ).fetchall()
    return rows[0][0] if len(rows) == 1 else None


def upsert_lemma(conn: sqlite3.Connection, lemma: str, pos: str, gender: str, source: str) -> int:
    norm = normalize(lemma)
    # Identity is the ACCENTED surface + pos. Accent is phonemic in Greek, so folding
    # it into the primary key silently destroyed distinct words — ποτέ "never",
    # νομός "prefecture", δουλεία "slavery", χαλί "carpet" all had 0 rows (audit F21).
    # normalized_lemma remains the SEARCH key; it is not the identity key.
    cur = conn.execute(
        "SELECT id, sources FROM lemmas WHERE lemma = ? AND pos IS ?",
        (lemma, pos),
    )
    row = cur.fetchone()
    if row:
        lemma_id, sources = row
        srcs = set((sources or "").split(",")) - {""}
        if source not in srcs:
            srcs.add(source)
            conn.execute("UPDATE lemmas SET sources = ? WHERE id = ?", (",".join(sorted(srcs)), lemma_id))
        return lemma_id
    # lemma_class (Phase 2 / audit F37): proper names are 76% of the lexicon and
    # distort every coverage/frequency figure and crowd search. Tag by POS here; the
    # gloss-based refinement (a noun whose every sense is «επώνυμο») is applied by the
    # post-ingest classify_lemma_class pass, which needs the senses to exist first.
    lemma_class = "name" if pos == "name" else "content"
    cur = conn.execute(
        "INSERT INTO lemmas (lemma, normalized_lemma, pos, gender, sources, lemma_class) "
        "VALUES (?,?,?,?,?,?)",
        (lemma, norm, pos, gender, source, lemma_class),
    )
    return cur.lastrowid


def is_form_of_entry(entry: dict) -> bool:
    """True when an entry is purely an inflected-form stub (e.g. the standalone
    "ανθρώπων = genitive plural of άνθρωπος" page), not a lemma in its own right.

    Such entries would otherwise become a competing `lemma` row that outranks the
    correct form→lemma resolution. We require EVERY sense to be a form-of pointer
    (a structured `form_of` field or a "form-of" sense tag) so we never drop an
    entry that carries any independent definition. The entry-level "form-of" tag
    alone is too aggressive — words like μηδέν/σε/λίγο carry it yet have real senses.
    """
    senses = entry.get("senses", [])
    if not senses:
        return False
    return all(
        s.get("form_of") or "form-of" in (s.get("tags") or [])
        for s in senses
    )


# Wiktionary relation keys → our typed relation_type (schema lists:
# synonym|antonym|hypernym|hyponym|derived|related). Keys appear both at the
# entry level and per-sense; both carry lists of {"word": ...} objects.
RELATION_KEYS = {
    "synonyms": "synonym",
    "antonyms": "antonym",
    "hypernyms": "hypernym",
    "hyponyms": "hyponym",
    "derived": "derived",
    "derived_terms": "derived",
    "related": "related",
    "coordinate_terms": "related",
}


def sense_tags(sense: dict) -> list[str]:
    """Tags to store for a sense: grammatical/register `tags` + subject `topics`.

    Wiktionary keeps usage register in `tags` (figuratively, formal, slang…) but
    subject domains in a separate `topics` list (medicine, law…). We merge both,
    de-duped and order-preserved, so the frontend can classify them into usage /
    domain / grammar chips from one flat array.
    """
    out: list[str] = []
    seen: set[str] = set()
    for t in (sense.get("tags") or []) + (sense.get("topics") or []):
        t = str(t).strip()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _is_junk_target(target: str) -> bool:
    """Reject descriptive Wiktionary cruft masquerading as a relation target.

    Some Kaikki relation lists carry category-page prose rather than a word,
    e.g. "-γενής Νεοελληνικές λέξεις με επίθημα -γενής στο Βικιλεξικό". These
    leak in via non-breaking spaces, newlines, or the "Βικιλεξικ" self-reference
    marker — none are real lexical neighbours.
    """
    if "\xa0" in target or "\n" in target:
        return True
    if "Βικιλεξικ" in target:
        return True
    return False


# Greek (incl. polytonic) letters. A genuine relation target is pure Greek;
# any Latin letter signals English cross-reference prose that en-wiktionary
# folded into the `word` field (e.g. "γραπτός and γραπτ-", "χαρτί n and
# derivatives", "γιατρός m and [Term?]", "and see: χάρτης").
_GREEK_RE = re.compile(r"[Ͱ-Ͽἀ-῿]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def _clean_relation_targets(raw: str) -> list[str]:
    """Split an English-contaminated relation target into clean Greek terms.

    A target with NO Latin letters is genuine Greek — kept whole, so phrases and
    proverbs ("πυρ, γυνή και θάλασσα") survive intact. A target WITH Latin letters
    is prose: we walk its tokens, keep contiguous Greek-script runs as terms, and
    drop everything Latin (and/or/see, gender markers m·f·n, "derivatives",
    "[Term?]", …). Morphological stems (leading/trailing hyphen) aren't lemmas, so
    they're dropped too.
    """
    if not _LATIN_RE.search(raw):
        return [raw]
    parts: list[str] = []
    cur: list[str] = []
    for tok in raw.split():
        if _LATIN_RE.search(tok):
            if cur:
                parts.append(" ".join(cur))
                cur = []
        else:
            cur.append(tok)
    if cur:
        parts.append(" ".join(cur))
    out: list[str] = []
    for p in parts:
        p = p.strip(" ,.:;·()[]")
        if len(p) < 2 or p.startswith("-") or p.endswith("-"):
            continue
        if not _GREEK_RE.search(p):
            continue
        out.append(p)
    return out


def extract_relations(entry: dict) -> list[tuple[str, str]]:
    """Yield (relation_type, target_text) pairs from an entry's relation lists.

    Pulls from both entry level and each sense, dedupes within the entry, and
    cleans HTML entities. Each raw `word` is run through _clean_relation_targets
    to strip English cross-reference prose. Target text is kept as a display form;
    the lemma id is resolved in a later pass once all lemmas exist.
    """
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    containers = [entry] + list(entry.get("senses", []))
    for c in containers:
        for key, rel_type in RELATION_KEYS.items():
            for item in c.get(key) or []:
                word = (item or {}).get("word")
                if not word:
                    continue
                raw = html.unescape(word).strip()
                if not raw or _is_junk_target(raw):
                    continue
                for target in _clean_relation_targets(raw):
                    pair = (rel_type, target)
                    if pair in seen:
                        continue
                    seen.add(pair)
                    out.append(pair)
    return out


# Wiktionary etymology-template names → our origin relation_type. The template
# arg layout differs: inh/der/bor/cal carry {1:defined-lang, 2:source-lang,
# 3:source-term}; cog/cogn carry {1:source-lang, 2:source-term}. "borrowed" folds
# learned/semi-learned borrowings; "derived" folds uncategorised der (uder).
ETY_TEMPLATE_REL: dict[str, str] = {
    "inh": "inherited", "inh+": "inherited",
    "der": "derived", "der+": "derived", "uder": "derived",
    "bor": "borrowed", "bor+": "borrowed", "lbor": "borrowed", "slbor": "borrowed",
    "cal": "calque", "calque": "calque", "clq": "calque",
    "cog": "cognate", "cogn": "cognate",
}


# --- el.wiktionary prose etymology parsing -------------------------------------
# The el dump carries NO etymology_templates — only prose `etymology_text` with a
# consistent grammar: "headword < (relation-marker) LANGUAGE term < older < …".
# We deterministically extract the IMMEDIATE ancestor (first " < " step) when we
# can identify a source language. Internal compounds/affixes (no language) are
# left unparsed — the verbatim prose is still shown ("sources define").

# Greek language-name phrases → Wiktionary/ISO codes. Order matters: longer,
# more-specific phrases are matched before their shorter prefixes.
_EL_LANGS: list[tuple[str, str]] = [
    ("αρχαία ελληνική", "grc"), ("ελληνιστική κοινή", "grc-koi"),
    ("μεσαιωνική ελληνική", "gkm"), ("μεσαιωνική λατινική", "la-med"),
    ("ύστερη λατινική", "la-lat"), ("δημώδης λατινική", "la-vul"),
    ("πρωτοϊνδοευρωπαϊκή", "ine-pro"), ("ινδοευρωπαϊκή", "ine-pro"),
    ("πρωτοελληνική", "grk-pro"), ("προελληνική", "qfa-sub"),
    ("οθωμανική τουρκική", "ota"), ("κλασική συριακή", "syc"),
    ("πρωτοσλαβική", "sla-pro"), ("παλαιά γαλλική", "fro"), ("αρχαία γαλλική", "fro"),
    ("λατινική", "la"), ("λατινικά", "la"), ("γαλλική", "fr"), ("γαλλικά", "fr"),
    ("ιταλική", "it"), ("ιταλικά", "it"), ("βενετική", "vec"), ("βενετικά", "vec"),
    ("τουρκική", "tr"), ("τουρκικά", "tr"), ("αραβική", "ar"), ("αραβικά", "ar"),
    ("περσική", "fa"), ("περσικά", "fa"), ("εβραϊκή", "he"), ("εβραϊκά", "he"),
    ("σανσκριτική", "sa"), ("σανσκριτικά", "sa"), ("αγγλική", "en"), ("αγγλικά", "en"),
    ("γερμανική", "de"), ("γερμανικά", "de"), ("ισπανική", "es"), ("ισπανικά", "es"),
    ("ρωσική", "ru"), ("ρωσικά", "ru"), ("βουλγαρική", "bg"), ("βουλγαρικά", "bg"),
    ("αλβανική", "sq"), ("αλβανικά", "sq"), ("συριακή", "syc"), ("αραμαϊκή", "arc"),
    ("κοπτική", "cop"), ("αιγυπτιακή", "egy"), ("σλαβική", "sla"),
]
# Older stages of Greek (and PIE/proto): an unmarked link to these reads as
# inheritance; an unmarked link to a foreign language reads as borrowing.
_EL_OLD_GREEK = {"grc", "grc-koi", "gkm", "grk-pro", "qfa-sub", "ine-pro"}
_EL_STEP = re.compile(r"\s+<\s+")
_EL_MARKER = re.compile(r"^\(([^)]*)\)\s*")
_EL_TERM = re.compile(r"[«\"]?([*\-]?[^\s,.;:»\"()<]+)")
# Connector words that may sit between a language name and the actual ancestor
# term in el prose ("πρωτοϊνδοευρωπαϊκή ρίζα *reh-", "λατινική λέξη rosa"). Skip
# them so we capture the real term, not the connector.
_EL_CONNECTORS = {
    "ρίζα", "ρίζας", "λέξη", "λέξης", "ρήμα", "ρήματος", "θέμα", "θέματος",
    "όνομα", "ονόματος", "ουσιαστικό", "επίθετο", "επίρρημα", "μετοχή",
    "τύπος", "τύπο", "τύπου", "προέλευσης", "καταγωγής",
    "ο", "η", "το", "τη", "την", "του", "της", "από", "στο", "στη",
}


def _el_first_term(rest: str) -> str:
    """First real ancestor token in `rest`, skipping connector words. Returns ""
    when nothing usable is found (pure connector run / empty)."""
    s = rest
    for _ in range(4):  # bounded: skip at most a few connectors
        tm = _EL_TERM.match(s)
        if not tm:
            return ""
        tok = tm.group(1).strip("«».,;:")
        if tok and tok.lower() not in _EL_CONNECTORS:
            return tok
        # advance past this connector token and retry
        nxt = s[tm.end():].lstrip()
        if nxt == s:
            return ""
        s = nxt
    return ""


def _el_relation(marker: str, lang: str) -> str:
    m = marker.lower()
    if "μεταφραστικό" in m or "απόδοση" in m:
        return "calque"
    if "κληρονομ" in m or "διαχρονικό" in m:
        return "inherited"
    if "δάνειο" in m or "δάνεια" in m or "αντιδάνειο" in m:
        return "borrowed"
    return "inherited" if lang in _EL_OLD_GREEK else "borrowed"


def parse_el_etymology_prose(text: str) -> list[tuple[str, str, str, int]]:
    """Extract the full ancestor CHAIN from el prose etymology.

    The el grammar is "headword < (marker) LANGUAGE term < (marker) LANGUAGE
    older < …". We walk every " < " step and emit one (relation, lang_code,
    term, seq) tuple per step whose segment names a recognised source language,
    with `seq` preserving chain order (0 = immediate ancestor, deepest last).

    Conservative by design: a step with no recognised language (a pure internal
    Greek morpheme — "χρῶμα < χρώς", an affix sum, a redirect "δείτε τη λέξη …")
    is skipped rather than guessed, so we never assert an ancestor we can't type.
    The verbatim prose is still shown — "sources define".
    """
    parts = _EL_STEP.split(text)
    out: list[tuple[str, str, str, int]] = []
    seen: set[tuple[str, str, str]] = set()
    seq = 0
    for seg in parts[1:]:
        seg = seg.strip()
        marker = ""
        mm = _EL_MARKER.match(seg)
        if mm:
            marker = mm.group(1)
            seg = seg[mm.end():].strip()
        for phrase, code in _EL_LANGS:
            if seg.startswith(phrase):
                rest = seg[len(phrase):].strip()
                term = _el_first_term(rest)
                if term:
                    key = (_el_relation(marker, code), code, term)
                    if key not in seen:
                        seen.add(key)
                        out.append((key[0], key[1], key[2], seq))
                        seq += 1
                break
    return out


def extract_etymology(entry: dict) -> tuple[str | None, list[tuple[str, str, str, int]]]:
    """Return (etymology_text, [(relation, lang_code, term, seq), ...]).

    Structured origins come from `etymology_templates` when present (en dump),
    else from parsing the Greek prose `etymology_text` (el dump, which has no
    templates). Inline {{m}}/{{l}} mentions are intentionally ignored.
    """
    text = entry.get("etymology_text")
    if text:
        text = html.unescape(text).strip() or None
    etymons: list[tuple[str, str, str, int]] = []
    seen: set[tuple[str, str, str]] = set()
    seq = 0
    for tpl in entry.get("etymology_templates") or []:
        rel = ETY_TEMPLATE_REL.get((tpl.get("name") or "").lower())
        if not rel:
            continue
        args = tpl.get("args") or {}
        if rel == "cognate":
            lang, term = args.get("1"), args.get("2")
        else:
            lang, term = args.get("2"), args.get("3")
        if not term:
            continue
        term = html.unescape(str(term)).strip()
        lang = (str(lang).strip() if lang else "")
        if not term or term in ("-", "—"):
            continue
        dedup = (rel, lang, term)
        if dedup in seen:
            continue
        seen.add(dedup)
        etymons.append((rel, lang, term, seq))
        seq += 1

    # No templates (el dump): fall back to deterministic prose parsing.
    if not etymons and text:
        etymons = parse_el_etymology_prose(text)
    return text, etymons


def store_etymology(conn: sqlite3.Connection, lemma_id: int, text: str | None,
                    etymons: list[tuple[str, str, str, int]], source: str) -> int:
    """Persist etymology prose + structured etymons, preferring el-wiktionary.

    Idempotent: el data overwrites any earlier en data; en never overwrites el.
    Re-running the same source refreshes cleanly (etymons are replaced wholesale).
    """
    is_el = source == "el-wiktionary"
    if text:
        conn.execute(
            "INSERT INTO etymology (lemma_id, text, source) VALUES (?,?,?) "
            "ON CONFLICT(lemma_id) DO UPDATE SET text=excluded.text, source=excluded.source "
            "WHERE excluded.source = 'el-wiktionary' OR etymology.source = excluded.source",
            (lemma_id, text, source),
        )
    if not etymons:
        return 0
    existing = conn.execute("SELECT DISTINCT source FROM etymons WHERE lemma_id=?", (lemma_id,)).fetchall()
    have_el = any(r[0] == "el-wiktionary" for r in existing)
    if existing and not is_el and not have_el:
        # only en data exists; allow another en pass to refresh it
        conn.execute("DELETE FROM etymons WHERE lemma_id=? AND source=?", (lemma_id, source))
    elif existing and not is_el:
        return 0  # el data present — en must not override
    elif existing and is_el:
        conn.execute("DELETE FROM etymons WHERE lemma_id=?", (lemma_id,))  # el refreshes/overrides all
    n = 0
    for rel, lang, term, seq in etymons:
        conn.execute(
            "INSERT INTO etymons (lemma_id, relation, lang_code, term, source, seq) VALUES (?,?,?,?,?,?)",
            (lemma_id, rel, lang, term, source, seq),
        )
        n += 1
    return n


def extract_pronunciations(entry: dict) -> list[str]:
    """Return ordered, de-duplicated IPA strings from the `sounds` field.

    Wiktionary `sounds` is a list of dicts; we only take `ipa` (audio is link-out
    only). Leading/trailing slashes/brackets are stripped so display can wrap them
    consistently (/…/). Order is preserved (first reading is the primary one).
    """
    out: list[str] = []
    seen: set[str] = set()
    for item in entry.get("sounds") or []:
        ipa = item.get("ipa") if isinstance(item, dict) else None
        if not ipa:
            continue
        ipa = html.unescape(str(ipa)).strip().strip("/[]").strip()
        if not ipa or ipa in seen:
            continue
        seen.add(ipa)
        out.append(ipa)
    return out


def store_pronunciations(conn: sqlite3.Connection, lemma_id: int, ipas: list[str], source: str) -> int:
    """Persist IPA readings for a lemma. Idempotent via (lemma_id, ipa) PK.

    el-wiktionary is preferred: an el pass replaces any prior readings for the
    lemma; en only fills lemmas that have none yet (never overrides el).
    """
    if not ipas:
        return 0
    is_el = source == "el-wiktionary"
    existing = conn.execute("SELECT DISTINCT source FROM pronunciations WHERE lemma_id=?", (lemma_id,)).fetchall()
    have_el = any(r[0] == "el-wiktionary" for r in existing)
    if existing and is_el:
        conn.execute("DELETE FROM pronunciations WHERE lemma_id=?", (lemma_id,))  # el refreshes all
    elif existing and have_el:
        return 0  # el present — en must not override
    elif existing and not is_el:
        conn.execute("DELETE FROM pronunciations WHERE lemma_id=? AND source=?", (lemma_id, source))
    n = 0
    for seq, ipa in enumerate(ipas):
        conn.execute(
            "INSERT OR IGNORE INTO pronunciations (lemma_id, ipa, source, seq) VALUES (?,?,?,?)",
            (lemma_id, ipa, source, seq),
        )
        n += 1
    return n


# raw_tag (or leading inline marker) on a descendant → our relation_type. Mirrors
# the etymology relations but in the forward (Greek → other language) direction.
DESC_REL = {
    "borrowed": "borrowed", "inherited": "inherited",
    "calque": "calque", "semi-calque": "calque",
    "derived": "derived", "transliteration": "borrowed",
}


def extract_descendants(entry: dict) -> list[tuple[str, str, str, str, str | None, int]]:
    """Return [(relation, lang_code, lang_name, term, roman, seq), ...].

    From en-wiktionary's `descendants` field — words in other languages that came
    FROM this Greek lemma. relation comes from the item's raw_tags (mostly
    "borrowed"), defaulting to "borrowed" (the overwhelming majority).
    """
    out: list[tuple[str, str, str, str, str | None, int]] = []
    seen: set[tuple[str, str]] = set()
    seq = 0
    for it in entry.get("descendants") or []:
        if not isinstance(it, dict):
            continue
        term = it.get("word")
        if not term:
            continue
        term = html.unescape(str(term)).strip()
        if not term or term in ("-", "—"):
            continue
        rel = "borrowed"
        for t in it.get("raw_tags") or it.get("tags") or []:
            mapped = DESC_REL.get(str(t).strip().lower())
            if mapped:
                rel = mapped
                break
        lang_code = (str(it.get("lang_code")).strip() if it.get("lang_code") else "")
        lang_name = (str(it.get("lang")).strip() if it.get("lang") else "")
        roman = it.get("roman")
        roman = html.unescape(str(roman)).strip() if roman else None
        dedup = (lang_code, term)
        if dedup in seen:
            continue
        seen.add(dedup)
        out.append((rel, lang_code, lang_name, term, roman, seq))
        seq += 1
    return out


def store_descendants(conn: sqlite3.Connection, lemma_id: int,
                      descs: list[tuple[str, str, str, str, str | None, int]], source: str) -> int:
    """Persist descendants for a lemma. Idempotent: a re-run from the same source
    replaces that source's rows wholesale (descendants are en-only in practice)."""
    if not descs:
        return 0
    conn.execute("DELETE FROM descendants WHERE lemma_id=? AND source=?", (lemma_id, source))
    n = 0
    for rel, lang_code, lang_name, term, roman, seq in descs:
        conn.execute(
            "INSERT INTO descendants (lemma_id, relation, lang_code, lang_name, term, roman, source, seq) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (lemma_id, rel, lang_code, lang_name, term, roman, source, seq),
        )
        n += 1
    return n


def resolve_relation_targets(conn: sqlite3.Connection) -> int:
    """Link relations.target_text to a lemma id by normalized surface.

    Idempotent: only touches rows still missing a target_lemma_id, so it is safe
    to re-run after each ingest pass (el then en). Returns rows newly resolved.
    """
    lemma_by_norm: dict[str, int] = {}
    for lid, norm in conn.execute("SELECT id, normalized_lemma FROM lemmas"):
        lemma_by_norm.setdefault(norm, lid)
    resolved = 0
    rows = conn.execute(
        "SELECT id, target_text FROM relations WHERE target_lemma_id IS NULL AND target_text IS NOT NULL"
    ).fetchall()
    for rel_id, target_text in rows:
        lid = lemma_by_norm.get(normalize(target_text))
        if lid is not None:
            conn.execute("UPDATE relations SET target_lemma_id = ? WHERE id = ?", (lid, rel_id))
            resolved += 1
    return resolved


def parse_gender(entry: dict) -> str | None:
    for form in entry.get("forms", []):
        tags = form.get("tags") or []
        for g in ("masculine", "feminine", "neuter"):
            if g in tags:
                return g
    return None


def ingest(input_path: str, source: str, db_path: str, limit: int | None) -> dict:
    conn = init_db(db_path)
    record_attribution(conn, source)
    stats = {"lines": 0, "lemmas": 0, "senses": 0, "forms": 0, "relations": 0,
             "etymology": 0, "etymons": 0,
             "relations_resolved": 0, "skipped": 0, "form_of_skipped": 0,
             "forms_rejected": 0, "voice_inferred": 0}
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

            # Form-of stubs are recoverable from their lemma's inflection table;
            # keeping them as lemmas would outrank the correct form resolution.
            if is_form_of_entry(entry):
                stats["form_of_skipped"] += 1
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
                    (lemma_id, i, "; ".join(glosses), json.dumps(sense_tags(sense), ensure_ascii=False),
                     json.dumps(examples, ensure_ascii=False), source),
                )
                stats["senses"] += 1

            seen_forms: set[str] = set()
            for form in entry.get("forms", []):
                ftext = form.get("form")
                tags = form.get("tags") or []
                if "table-tags" in tags or "inflection-template" in tags:
                    continue
                # Admissibility gate (F1/F4): a "form" that is punctuation, template
                # debris, a bare ending or a component of a multiword lemma becomes a
                # searchable surface that absorbs corpus tokens.
                if not is_admissible_form(ftext, word):
                    stats["forms_rejected"] += 1
                    continue
                voice = infer_voice(ftext, tags, pos)
                if voice:
                    tags = list(tags) + [voice]
                    stats["voice_inferred"] += 1
                key = (ftext, tuple(tags))
                if key in seen_forms:
                    continue
                seen_forms.add(key)
                conn.execute(
                    "INSERT INTO forms (lemma_id, form, normalized_form, features, source) VALUES (?,?,?,?,?)",
                    (lemma_id, ftext, normalize(ftext), json.dumps(tags, ensure_ascii=False), source),
                )
                stats["forms"] += 1

            for rel_type, target in extract_relations(entry):
                conn.execute(
                    "INSERT INTO relations (source_lemma_id, target_text, relation_type, source) VALUES (?,?,?,?)",
                    (lemma_id, target, rel_type, source),
                )
                stats["relations"] += 1

            ety_text, etymons = extract_etymology(entry)
            if ety_text or etymons:
                added = store_etymology(conn, lemma_id, ety_text, etymons, source)
                if ety_text:
                    stats["etymology"] += 1
                stats["etymons"] += added

            if stats["lines"] % 5000 == 0:
                conn.commit()
                print(f"  ...{stats['lines']} lines", file=sys.stderr)

    stats["relations_resolved"] = resolve_relation_targets(conn)
    conn.commit()
    conn.close()
    return stats


def ingest_etymology_only(input_path: str, source: str, db_path: str, limit: int | None) -> dict:
    """Update ONLY the etymology + etymons tables for lemmas already in the store.

    Unlike a full ingest, this never inserts lemmas/senses/forms/relations, so it
    is safe to run repeatedly on a populated DB (no duplication). Use it to add or
    refresh etymology after the rest of the data is built. Run el then en.
    """
    conn = init_db(db_path)
    record_attribution(conn, source)
    stats = {"lines": 0, "matched": 0, "unmatched": 0, "etymology": 0, "etymons": 0, "skipped": 0}
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
            if not word or entry.get("lang_code") not in (None, "el") or is_form_of_entry(entry):
                stats["skipped"] += 1
                continue
            ety_text, etymons = extract_etymology(entry)
            if not ety_text and not etymons:
                continue
            lemma_id = find_lemma_id(conn, word, entry.get("pos"))
            if lemma_id is None:
                stats["unmatched"] += 1
                continue
            stats["matched"] += 1
            added = store_etymology(conn, lemma_id, ety_text, etymons, source)
            if ety_text:
                stats["etymology"] += 1
            stats["etymons"] += added
            if stats["lines"] % 50000 == 0:
                conn.commit()
                print(f"  ...{stats['lines']} lines", file=sys.stderr)
    conn.commit()
    conn.close()
    return stats


def ingest_pronunciation_only(input_path: str, source: str, db_path: str, limit: int | None) -> dict:
    """Update ONLY the pronunciations table for lemmas already in the store.

    Mirrors ingest_etymology_only: never inserts lemmas/senses/forms/relations, so
    it is safe to re-run on a populated DB (no duplication). Run el then en.
    """
    conn = init_db(db_path)
    record_attribution(conn, source)
    stats = {"lines": 0, "matched": 0, "unmatched": 0, "lemmas": 0, "ipas": 0, "skipped": 0}
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
            if not word or entry.get("lang_code") not in (None, "el") or is_form_of_entry(entry):
                stats["skipped"] += 1
                continue
            ipas = extract_pronunciations(entry)
            if not ipas:
                continue
            lemma_id = find_lemma_id(conn, word, entry.get("pos"))
            if lemma_id is None:
                stats["unmatched"] += 1
                continue
            stats["matched"] += 1
            added = store_pronunciations(conn, lemma_id, ipas, source)
            if added:
                stats["lemmas"] += 1
            stats["ipas"] += added
            if stats["lines"] % 50000 == 0:
                conn.commit()
                print(f"  ...{stats['lines']} lines", file=sys.stderr)
    conn.commit()
    conn.close()
    return stats


def ingest_descendants_only(input_path: str, source: str, db_path: str, limit: int | None) -> dict:
    """Update ONLY the descendants table for lemmas already in the store.

    Mirrors ingest_etymology_only / ingest_pronunciation_only: never inserts
    lemmas/senses/forms/relations, so it is safe to re-run. Descendants live in the
    en dump, so run this with --source en-wiktionary.
    """
    conn = init_db(db_path)
    record_attribution(conn, source)
    stats = {"lines": 0, "matched": 0, "unmatched": 0, "lemmas": 0, "descendants": 0, "skipped": 0}
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
            if not word or entry.get("lang_code") not in (None, "el") or is_form_of_entry(entry):
                stats["skipped"] += 1
                continue
            descs = extract_descendants(entry)
            if not descs:
                continue
            lemma_id = find_lemma_id(conn, word, entry.get("pos"))
            if lemma_id is None:
                stats["unmatched"] += 1
                continue
            stats["matched"] += 1
            added = store_descendants(conn, lemma_id, descs, source)
            if added:
                stats["lemmas"] += 1
            stats["descendants"] += added
            if stats["lines"] % 50000 == 0:
                conn.commit()
                print(f"  ...{stats['lines']} lines", file=sys.stderr)
    conn.commit()
    conn.close()
    return stats


def ingest_sense_tags_only(input_path: str, source: str, db_path: str, limit: int | None) -> dict:
    """Refresh ONLY the `tags` column of existing senses (merging in `topics`).

    For adding subject-domain labels to a DB built before topics were captured,
    without a full re-ingest (which would duplicate senses). Updates rows in place
    by (lemma_id, sense_index, source) — the same deterministic ordering used when
    the senses were first inserted. Run with the matching --source.
    """
    conn = init_db(db_path)
    stats = {"lines": 0, "matched": 0, "unmatched": 0, "senses_updated": 0, "skipped": 0}
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
            if not word or entry.get("lang_code") not in (None, "el") or is_form_of_entry(entry):
                stats["skipped"] += 1
                continue
            lemma_id = find_lemma_id(conn, word, entry.get("pos"))
            if lemma_id is None:
                stats["unmatched"] += 1
                continue
            stats["matched"] += 1
            for i, sense in enumerate(entry.get("senses", [])):
                glosses = sense.get("glosses") or sense.get("raw_glosses") or []
                if not glosses:
                    continue
                cur = conn.execute(
                    "UPDATE senses SET tags = ? WHERE lemma_id = ? AND sense_index = ? AND source = ?",
                    (json.dumps(sense_tags(sense), ensure_ascii=False), lemma_id, i, source),
                )
                stats["senses_updated"] += cur.rowcount
            if stats["lines"] % 50000 == 0:
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
    ap.add_argument("--etymology-only", action="store_true",
                    help="Only update etymology/etymons for existing lemmas (no full re-ingest).")
    ap.add_argument("--ipa-only", action="store_true",
                    help="Only update IPA pronunciations for existing lemmas (no full re-ingest).")
    ap.add_argument("--descendants-only", action="store_true",
                    help="Only update cross-language descendants for existing lemmas (no full re-ingest).")
    ap.add_argument("--sense-tags-only", action="store_true",
                    help="Only refresh sense tags (merge in subject `topics`) for existing senses.")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        sys.exit(f"Input not found: {args.input}\nRun pipelines/download_data.ps1 (or .sh) first.")

    if args.etymology_only:
        print(f"Etymology-only pass: {args.input} as {args.source} -> {args.db}", file=sys.stderr)
        stats = ingest_etymology_only(args.input, args.source, args.db, args.limit)
    elif args.ipa_only:
        print(f"IPA-only pass: {args.input} as {args.source} -> {args.db}", file=sys.stderr)
        stats = ingest_pronunciation_only(args.input, args.source, args.db, args.limit)
    elif args.descendants_only:
        print(f"Descendants-only pass: {args.input} as {args.source} -> {args.db}", file=sys.stderr)
        stats = ingest_descendants_only(args.input, args.source, args.db, args.limit)
    elif args.sense_tags_only:
        print(f"Sense-tags-only pass: {args.input} as {args.source} -> {args.db}", file=sys.stderr)
        stats = ingest_sense_tags_only(args.input, args.source, args.db, args.limit)
    else:
        print(f"Ingesting {args.input} as {args.source} -> {args.db}", file=sys.stderr)
        stats = ingest(args.input, args.source, args.db, args.limit)

    # Record what produced this data, so a later reader can tell whether the DB
    # matches the code (audit F18/F60/F63 — see pipelines/ingest/manifest.py).
    mode = next((m for m in ("etymology_only", "ipa_only", "descendants_only",
                             "sense_tags_only") if getattr(args, m)), "full")
    _conn = sqlite3.connect(args.db)
    manifest.record_build(
        _conn, "ingest_kaikki", version=f"{args.source}:{mode}",
        inputs=[args.input],
        params={"source": args.source, "mode": mode, "limit": args.limit},
        tables=["lemmas", "senses", "forms", "relations"],
    )
    _conn.close()
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
