"""Greek text normalization — the cornerstone used by ingest, indexing, and search.

The search key for any surface form is produced by `normalize()`. Two surfaces
that a Greek user would consider "the same word modulo accents/case/sigma"
MUST map to the same normalized key. Keep this function pure and total.

Folding applied (in order):
  1. Unicode NFC (canonical compose) on input.
  2. Lowercase.
  3. Strip combining marks (tonos, dialytika, polytonic breathings/iota subscript)
     via NFD decomposition.
  4. Fold final sigma ς -> σ.
  5. Collapse internal whitespace, trim.

This deliberately discards accent and case. Accent IS phonemic in Greek
(πότε "when" vs ποτέ "ever"), so the *display* lemma keeps its accents — only
the *search key* is folded. Disambiguation between accent-distinct homographs
is handled at the result-ranking layer, not here.
"""

from __future__ import annotations

import itertools
import unicodedata

__all__ = [
    "normalize", "normalize_keep_accents", "strip_accents", "fold_final_sigma",
    "greeklish_to_greek", "greeklish_candidates",
]


def strip_accents(text: str) -> str:
    """Remove all combining marks (Mn): tonos, dialytika, polytonic diacritics."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def fold_final_sigma(text: str) -> str:
    """Fold word-final sigma (ς) to medial sigma (σ) so they share a key."""
    return text.replace("ς", "σ")


def normalize(text: str) -> str:
    """Produce the canonical search key for a Greek surface form."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.lower()
    text = strip_accents(text)
    text = fold_final_sigma(text)
    text = " ".join(text.split())
    return text


def normalize_keep_accents(text: str) -> str:
    """Accent-PRESERVING canonical key: fold only case + final sigma, keep tonos
    and dialytika. The *analysis* layers (frequency timeseries, diachronic drift,
    domain attribution) must key on this — accent is phonemic in Greek, so the
    accent-folding `normalize()` merges genuinely distinct lemmas that differ only
    by stress (νόμος "law" / νομός "prefecture", πότε "when" / ποτέ "ever",
    γέρος "old man" / γερός "sturdy"). Those share one `normalize()` key, which
    blends their corpus counts and embeddings into one contaminated vector/series.
    Keying on the accented form keeps them apart. (Search still uses the looser
    `normalize()` so a user typing without accents still finds the word.)

    NFC so a single combining tonos and its precomposed form agree; lowercase and
    final-sigma fold so Νόμος/νόμος. and word-final ς still collapse correctly."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.lower()
    text = fold_final_sigma(text)
    # Re-NFC after lowercasing (Greek final-sigma lowercasing can shift forms).
    text = unicodedata.normalize("NFC", text)
    text = " ".join(text.split())
    return text


# --- Greeklish fallback (M1) -------------------------------------------------
# A deliberately small, deterministic Latin->Greek table for the case where the
# GR-NLP-TOOLKIT transliterator is unavailable. This is a *candidate generator*,
# not ground truth — its output is fed back through normalize() and matched
# against the index. Digraphs first, longest-match.
_GREEKLISH_DIGRAPHS = [
    ("th", "θ"), ("ch", "χ"), ("ps", "ψ"), ("ks", "ξ"), ("ou", "ου"),
    ("ai", "αι"), ("ei", "ει"), ("oi", "οι"), ("gg", "γγ"), ("gk", "γκ"),
    ("mp", "μπ"), ("nt", "ντ"), ("ts", "τσ"), ("tz", "τζ"),
]
_GREEKLISH_SINGLE = {
    "a": "α", "b": "β", "g": "γ", "d": "δ", "e": "ε", "z": "ζ", "h": "η",
    "i": "ι", "k": "κ", "l": "λ", "m": "μ", "n": "ν", "x": "ξ", "o": "ο",
    "p": "π", "r": "ρ", "s": "σ", "t": "τ", "y": "υ", "u": "υ", "f": "φ",
    "w": "ω", "c": "κ", "j": "ι", "h": "η",
}


def greeklish_to_greek(text: str) -> str:
    """Best-effort Latin->Greek transliteration for a single candidate.

    Not authoritative: many-to-one ambiguity (η/ι/υ, ο/ω) is unavoidable here.
    Used only to widen the search candidate set. For the full ambiguity fan-out
    see `greeklish_candidates`; this returns just the most-likely transliteration.
    """
    s = text.lower()
    out: list[str] = []
    i = 0
    while i < len(s):
        matched = False
        for latin, greek in _GREEKLISH_DIGRAPHS:
            if s.startswith(latin, i):
                out.append(greek)
                i += len(latin)
                matched = True
                break
        if matched:
            continue
        out.append(_GREEKLISH_SINGLE.get(s[i], s[i]))
        i += 1
    return "".join(out)


# --- Greeklish vowel-expansion (multi-candidate) -----------------------------
# A single Latin spelling is genuinely ambiguous in Greek: the sound /i/ is
# written ι/η/υ/ει/οι, /o/ is ο/ω, /e/ is ε/αι. `greeklish_to_greek` picks one
# arm and silently misses words spelled with the others (γη, ζωή, παίζω…). The
# fan-out below enumerates the plausible spellings per ambiguous unit and yields
# the Cartesian product, most-likely arm first (each alternatives list is
# primary-first), capped to keep the candidate set bounded. Consumers rank the
# resulting hits by lemma frequency. Digraphs are matched longest-first.
_GREEKLISH_DIGRAPH_ALTS: list[tuple[str, list[str]]] = [
    ("th", ["θ"]), ("ch", ["χ"]), ("ps", ["ψ"]), ("ks", ["ξ"]),
    # Vowel digraphs carry both the diphthong reading AND the likely two-vowel
    # splits, since e.g. ζωή is typed "zoi" (ω+η, not the οι diphthong).
    ("ou", ["ου"]), ("ai", ["αι", "ε", "αη"]),
    ("ei", ["ει", "ι", "η", "εη"]), ("oi", ["οι", "ι", "ωη", "οη", "ωι"]),
    ("gg", ["γγ"]), ("gk", ["γκ"]), ("mp", ["μπ"]),
    ("nt", ["ντ"]), ("ts", ["τσ"]), ("tz", ["τζ"]),
]
# Single-char alternatives where the Latin letter is vowel-ambiguous. Anything
# absent here falls back to the deterministic _GREEKLISH_SINGLE mapping.
_GREEKLISH_VOWEL_ALTS: dict[str, list[str]] = {
    "i": ["ι", "η", "υ"],
    "h": ["η", "ι"],
    "y": ["υ", "ι"],
    "o": ["ο", "ω"],
    "e": ["ε", "αι"],
    "w": ["ω", "ο"],
    "u": ["υ", "ου"],
}


def greeklish_candidates(text: str, max_candidates: int = 64) -> list[str]:
    """Enumerate plausible Greek transliterations of a Greeklish surface.

    Returns raw Greek strings (NOT normalized) in likelihood order — the first
    element equals `greeklish_to_greek(text)`. Bounded to `max_candidates` so a
    very vowel-heavy word can't blow up the candidate set. Callers normalize each
    and probe the search index, ranking hits by lemma frequency.
    """
    s = text.lower()
    units: list[list[str]] = []
    i = 0
    while i < len(s):
        matched = False
        for latin, alts in _GREEKLISH_DIGRAPH_ALTS:
            if s.startswith(latin, i):
                units.append(alts)
                i += len(latin)
                matched = True
                break
        if matched:
            continue
        ch = s[i]
        if ch in _GREEKLISH_VOWEL_ALTS:
            units.append(_GREEKLISH_VOWEL_ALTS[ch])
        else:
            units.append([_GREEKLISH_SINGLE.get(ch, ch)])
        i += 1

    out: list[str] = []
    seen: set[str] = set()
    for combo in itertools.product(*units):
        cand = "".join(combo)
        if cand not in seen:
            seen.add(cand)
            out.append(cand)
        if len(out) >= max_candidates:
            break
    return out


if __name__ == "__main__":
    import sys

    for arg in sys.argv[1:]:
        print(f"{arg!r} -> key={normalize(arg)!r}  greeklish={greeklish_to_greek(arg)!r}")
