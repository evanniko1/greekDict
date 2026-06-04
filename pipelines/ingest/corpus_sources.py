"""Shared readers for dated corpora feeding the diachronic layers (B & C).

Two corpus shapes are supported, normalized to a common interface so the
frequency-timeseries and diachronic-embedding pipelines don't care where text
came from:

  • Leipzig (Wortschatz)  — one folder per (source, year), e.g. `ell_news_2020_1M`.
        *-sentences.txt : "id <TAB> sentence"   (one sentence per line)
        *-words.txt     : "id <TAB> word <TAB> freq"
        The YEAR is encoded in the folder name (…_YYYY_…).

  • Greek Parliament Proceedings (Zenodo) — a single big CSV, one row per speech.
        columns include `sitting_date` (a date) and `speech` (the text).
        The YEAR is parsed from the date column.

Everything is emitted in the ACCENT-PRESERVING key space via `tokenize()`
(`normalize_keep_accents`: fold case + final sigma, keep tonos). Accent is
phonemic in Greek, so the analysis layers must NOT fold it — otherwise distinct
lemmas that differ only by stress (νόμος/νομός, πότε/ποτέ) collapse into one
contaminated count/vector. Tokens resolve back to lemmas via the matching
accent-preserving key built from `search_index.surface` (see the ingest pipelines).
"""

from __future__ import annotations

import csv
import glob
import os
import re
import sys
from typing import Iterator

sys.path.insert(0, os.path.dirname(__file__))
from normalize_greek import normalize_keep_accents  # noqa: E402

# Big speeches blow past csv's default field limit; raise it once on import.
try:
    csv.field_size_limit(min(sys.maxsize, 2_147_483_647))
except OverflowError:  # pragma: no cover - platform dependent
    csv.field_size_limit(2_147_483_647)

EDGE_PUNCT = "«»\"'“”‘’()[]{}.,:;·…!?-–—/\\|<>*•%&@#~_=+"
_YEAR_RE = re.compile(r"(?:^|[^0-9])(\d{4})(?:[^0-9]|$)")


def tokenize(text: str) -> list[str]:
    """Accent-PRESERVING content tokens for a span of text (lowercased, final-sigma
    folded, tonos kept). Accent is phonemic, so the analysis layers keep it — see
    module docstring."""
    out: list[str] = []
    for raw in text.split():
        nrm = normalize_keep_accents(raw.strip(EDGE_PUNCT))
        if nrm:
            out.append(nrm)
    return out


def parse_year(value: str) -> int | None:
    """Pull a 4-digit year (1900–2099) from a date-ish string."""
    if not value:
        return None
    for m in _YEAR_RE.finditer(value):
        y = int(m.group(1))
        if 1900 <= y <= 2099:
            return y
    return None


# ── Leipzig ────────────────────────────────────────────────────────────────

# Leipzig (Wortschatz) folders are named <source>_<YYYY>_<size>, e.g.
# `ell_news_2020_1M`, `ell_wikipedia_2021_1M`, `ell-eu_web_2017_100K`. The SOURCE
# prefix (everything before the 4-digit year) identifies which corpus a folder
# belongs to. We map the raw prefix to a clean axis label so that several Leipzig
# corpora can live side-by-side under one directory yet stay on SEPARATE axes
# (the cardinal rule). Unknown prefixes fall back to the prefix with the leading
# `ell[-_]` language tag stripped.
_LEIPZIG_NAME_RE = re.compile(r"^(?P<src>.+?)_(?P<year>\d{4})(?:_.*)?$")
LEIPZIG_CORPUS_LABELS = {
    "ell_news": "news",
    "ell_newscrawl": "news",
    "ell_wikipedia": "wiki",
    "ell-eu_web": "web",
    "ell_web": "web",
    "ell_mixed": "mixed",
    "ell_literature": "literature",
}


def leipzig_year(folder: str) -> int | None:
    """Year encoded in a Leipzig corpus folder name (ell_news_2020_1M -> 2020)."""
    return parse_year(os.path.basename(folder.rstrip("/\\")))


def leipzig_source(folder: str) -> str | None:
    """Raw source prefix of a Leipzig folder name (ell_news_2020_1M -> 'ell_news').
    None if the name doesn't match the <source>_<YYYY>… shape."""
    m = _LEIPZIG_NAME_RE.match(os.path.basename(folder.rstrip("/\\")))
    return m.group("src") if m else None


def leipzig_corpus_label(folder: str) -> str | None:
    """Clean axis label for a Leipzig folder (ell_news_… -> 'news', ell_wikipedia_…
    -> 'wiki'). Known prefixes use LEIPZIG_CORPUS_LABELS; an unknown prefix has its
    leading `ell-`/`ell_` language tag stripped (ell-foo_… -> 'foo'). None when the
    folder name has no parseable source prefix."""
    src = leipzig_source(folder)
    if src is None:
        return None
    if src in LEIPZIG_CORPUS_LABELS:
        return LEIPZIG_CORPUS_LABELS[src]
    return re.sub(r"^ell[-_]", "", src) or src


def _leipzig_file(folder: str, suffix: str) -> str | None:
    hits = glob.glob(os.path.join(folder, f"*{suffix}"))
    return hits[0] if hits else None


def iter_leipzig_sentences(folder: str) -> Iterator[str]:
    """Yield raw sentence strings from a Leipzig corpus folder."""
    path = _leipzig_file(folder, "-sentences.txt")
    if not path:
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            tab = line.find("\t")
            yield (line[tab + 1:] if tab != -1 else line).strip()


def read_leipzig_words(folder: str) -> Iterator[tuple[str, int]]:
    """Yield (word, freq) from a Leipzig *-words.txt file."""
    path = _leipzig_file(folder, "-words.txt")
    if not path:
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            try:
                yield parts[1], int(parts[2])
            except ValueError:
                continue


def discover_leipzig_slices(root: str, source: str | None = None) -> list[tuple[int, str]]:
    """Find Leipzig corpus folders under `root`, returning (year, folder) sorted.
    A folder qualifies if its name has a year and it holds a *-sentences.txt.

    When `source` is given (a raw prefix like 'ell_news' or a clean label like
    'news'/'wiki'), ONLY folders of that corpus are returned. This is what keeps
    several Leipzig corpora that share one directory on SEPARATE axes — without it
    an `ell_wikipedia_*` folder dropped beside `ell_news_*` would be swept into the
    news axis and silently merged (a cardinal-rule violation)."""
    slices: list[tuple[int, str]] = []
    for entry in sorted(os.listdir(root)):
        folder = os.path.join(root, entry)
        if not os.path.isdir(folder):
            continue
        year = leipzig_year(folder)
        if year is None:
            continue
        if source is not None and source not in (
            leipzig_source(folder), leipzig_corpus_label(folder)
        ):
            continue
        if _leipzig_file(folder, "-sentences.txt"):
            slices.append((year, folder))
    return sorted(slices)


def discover_leipzig_sources(root: str) -> dict[str, list[int]]:
    """Map each Leipzig corpus label found under `root` to its sorted years. Lets a
    caller see what axes are available before committing to one (and warn when a
    directory unexpectedly holds more than one corpus)."""
    out: dict[str, list[int]] = {}
    for entry in sorted(os.listdir(root)):
        folder = os.path.join(root, entry)
        if not os.path.isdir(folder):
            continue
        year = leipzig_year(folder)
        label = leipzig_corpus_label(folder)
        if year is None or label is None:
            continue
        if _leipzig_file(folder, "-sentences.txt"):
            out.setdefault(label, []).append(year)
    return {k: sorted(v) for k, v in sorted(out.items())}


# ── Greek Parliament Proceedings (CSV) ───────────────────────────────────────

def iter_parliament_speeches(
    csv_path: str,
    text_col: str = "speech",
    date_col: str = "sitting_date",
) -> Iterator[tuple[int, str]]:
    """Yield (year, speech_text) from the Parliament Proceedings CSV.

    Robust to column-order changes (uses the header) and to oversized fields.
    Rows with no parseable year or empty speech are skipped.
    """
    with open(csv_path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return
        if text_col not in reader.fieldnames or date_col not in reader.fieldnames:
            raise ValueError(
                f"CSV is missing columns. Looked for text={text_col!r} date={date_col!r}; "
                f"found {reader.fieldnames}. Pass --text-col/--date-col to match."
            )
        for row in reader:
            text = (row.get(text_col) or "").strip()
            if not text:
                continue
            year = parse_year(row.get(date_col) or "")
            if year is None:
                continue
            yield year, text
