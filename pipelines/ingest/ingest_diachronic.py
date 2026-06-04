"""Layer C — diachronic semantic drift within ONE consistent corpus.

We follow Hamilton et al. (2016): train a word2vec model per time slice, align
each slice's vector space to a reference slice with orthogonal Procrustes (a pure
rotation/reflection — it can't distort distances, only re-orient axes that two
independent trainings place arbitrarily), then read meaning change off the aligned
space:

  • drift  = cosine distance between a lemma's vector in the FIRST vs LAST slice,
             after alignment. High drift = the word's contexts changed the most.
  • era-neighbors = a lemma's nearest words within the first and last slice, so
             the UI can show "then vs now" company a word kept.

CARDINAL RULE (same as Layer B): one corpus per axis. A slice is one (corpus,
year); we never mix Parliament and news into one aligned space, because Procrustes
would then align register differences and report them as semantic change.

Slices come from either Leipzig year-folders (corpus=news) or the Parliament CSV
(corpus=parliament). To keep gensim's multi-pass training off a 2GB CSV, we first
materialize one normalized, one-sentence-per-line file per slice under
data/processed/diachronic/<corpus>/<year>.txt, then train from those.

Idempotent: clears diachronic_drift + diachronic_neighbors for the chosen corpus.

Requires gensim, scipy, numpy.

Examples:
    # News axis from Leipzig year-folders (needs ≥2 years for drift)
    python pipelines/ingest/ingest_diachronic.py \
        --leipzig-dir data/raw --db data/db/lexorama.sqlite

    # Parliament axis from the Zenodo CSV
    python pipelines/ingest/ingest_diachronic.py \
        --parliament-csv data/raw/Greek_Parliament_Proceedings_1989_2020.csv \
        --db data/db/lexorama.sqlite
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipelines", "ingest"))
from ingest_kaikki import init_db, record_attribution  # noqa: E402
from ingest_collocations import STOPWORDS  # noqa: E402
from normalize_greek import normalize_keep_accents  # noqa: E402
import corpus_sources as cs  # noqa: E402

DEFAULT_TOP_N = 8
MIN_NEIGHBOR_LEN = 3
CANDIDATE_POOL = 40
PROCESSED = os.path.join(ROOT, "data", "processed", "diachronic")


# ── materialize one normalized file per slice ────────────────────────────────

def materialize_leipzig(leipzig_dir: str, corpus: str = "news",
                        source: str | None = None) -> list[tuple[int, str]]:
    """Write data/processed/diachronic/<corpus>/<year>.txt from Leipzig folders.
    `source` (raw prefix or clean label) restricts discovery to one corpus, so
    co-located Leipzig corpora materialize into SEPARATE axis directories.
    Returns [(year, path)] sorted by year."""
    out_dir = os.path.join(PROCESSED, corpus)
    os.makedirs(out_dir, exist_ok=True)
    discovered = cs.discover_leipzig_slices(leipzig_dir, source)
    if not discovered:
        avail = cs.discover_leipzig_sources(leipzig_dir)
        hint = f" Available: {avail}." if avail else ""
        sys.exit(f"No Leipzig corpus folders (…_YYYY_…) found under {leipzig_dir}"
                 f"{f' for source={source!r}' if source else ''}.{hint}")
    slices: list[tuple[int, str]] = []
    for year, folder in discovered:
        path = os.path.join(out_dir, f"{year}.txt")
        n = 0
        with open(path, "w", encoding="utf-8") as out:
            for sent in cs.iter_leipzig_sentences(folder):
                toks = cs.tokenize(sent)
                if toks:
                    out.write(" ".join(toks) + "\n")
                    n += 1
        print(f"  · {corpus}/{year}: {n} sentences ({os.path.basename(folder)})", file=sys.stderr)
        slices.append((year, path))
    return slices


def materialize_parliament(csv_path: str, text_col: str, date_col: str) -> list[tuple[int, str]]:
    """Write data/processed/diachronic/parliament/<year>.txt by streaming the CSV
    once, fanning each speech into its year's file. Returns [(year, path)] sorted."""
    out_dir = os.path.join(PROCESSED, "parliament")
    os.makedirs(out_dir, exist_ok=True)
    handles: dict[int, "object"] = {}
    counts: dict[int, int] = {}
    try:
        for year, text in cs.iter_parliament_speeches(csv_path, text_col, date_col):
            toks = cs.tokenize(text)
            if not toks:
                continue
            fh = handles.get(year)
            if fh is None:
                fh = open(os.path.join(out_dir, f"{year}.txt"), "w", encoding="utf-8")
                handles[year] = fh
            fh.write(" ".join(toks) + "\n")
            counts[year] = counts.get(year, 0) + 1
    finally:
        for fh in handles.values():
            fh.close()
    for year in sorted(counts):
        print(f"  · parliament/{year}: {counts[year]} speeches", file=sys.stderr)
    return sorted((year, os.path.join(out_dir, f"{year}.txt")) for year in counts)


def existing_slices(corpus: str) -> list[tuple[int, str]]:
    """Already-materialized <year>.txt files for a corpus, sorted by year. Lets a
    re-run redo just the (re-anchored) modeling without re-streaming the source."""
    out_dir = os.path.join(PROCESSED, corpus)
    if not os.path.isdir(out_dir):
        return []
    found: list[tuple[int, str]] = []
    for name in os.listdir(out_dir):
        if name.endswith(".txt") and name[:-4].isdigit():
            found.append((int(name[:-4]), os.path.join(out_dir, name)))
    return sorted(found)


# ── train + align + drift ─────────────────────────────────────────────────────

def _train(path: str, vector_size: int, window: int, min_count: int, epochs: int):
    from gensim.models import Word2Vec
    return Word2Vec(
        corpus_file=path,
        vector_size=vector_size,
        window=window,
        min_count=min_count,
        workers=os.cpu_count() or 4,
        sg=0,
        epochs=epochs,
    )


# ── pooled (multi-year) training (#37) ───────────────────────────────────────
# Per-year models are thin in low-volume years, so rare words get noisy vectors
# (the frequency gate just hides them). Following the standard diachronic binning
# (Hamilton 2016 / Kim 2014), we OPTIONALLY pool a ±window band of adjacent years
# into each slice's training data. The model is still LABELED by its CENTRE year,
# so drift/trajectory semantics are unchanged; it just sees more sentences. The
# cardinal rule holds — every member year is the SAME corpus/axis.

def _pool_members(center: int, years: list[int], window: int) -> list[int]:
    """Years within ±window of `center` (inclusive), sorted. window=0 → [center]."""
    return sorted(y for y in years if abs(y - center) <= window)


def _adaptive_members(center: int, years: list[int], line_count: dict[int, int],
                      target: int, max_window: int) -> list[int]:
    """Smallest ±window band around `center` (0…max_window) whose pooled line count
    reaches `target` (#49). A FIXED ±window over-blurs already-dense years — it smears
    a sharp shift across the whole window even where there were plenty of sentences to
    estimate the year on its own. Adaptive pooling expands the window only as far as a
    thin year actually needs: dense years stay at window 0 (full temporal resolution),
    sparse years borrow just enough neighbours to hit `target`, capped at max_window.
    Returns the member-year list (sorted)."""
    if max_window <= 0 or target <= 0:
        return [center]
    for w in range(0, max_window + 1):
        members = _pool_members(center, years, w)
        if sum(line_count.get(y, 0) for y in members) >= target:
            return members
    return _pool_members(center, years, max_window)  # never reached target → widest band


def _pooled_to_tempfile(member_paths: list[str], cap: int, tmp_dir: str) -> str:
    """Concatenate member slice files into one temp training file. When `cap`>0 and
    the pooled corpus exceeds it, keep a uniform RESERVOIR sample of `cap` lines.

    Rationale for the cap: pooling helps THIN years (which stay well under the cap
    and so keep every sentence); the cap only ever bites on already-dense years
    (e.g. news 2024 ≈ 1M lines × a 5-yr band), which were stable without pooling
    anyway — so bounding their training set trades nothing real for tractable
    runtime. Returns the temp path; caller deletes it."""
    fd, path = tempfile.mkstemp(suffix=".txt", dir=tmp_dir)
    if cap and cap > 0:
        reservoir: list[str] = []
        n = 0
        for mp in member_paths:
            with open(mp, encoding="utf-8") as fh:
                for line in fh:
                    n += 1
                    if len(reservoir) < cap:
                        reservoir.append(line)
                    else:
                        j = random.randint(0, n - 1)
                        if j < cap:
                            reservoir[j] = line
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.writelines(reservoir)
    else:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            for mp in member_paths:
                with open(mp, encoding="utf-8") as fh:
                    for line in fh:
                        out.write(line)
    return path


def _cos_dist(a, b) -> float:
    """Cosine distance (1 − cosine similarity) between two vectors; 0 if either
    is the zero vector. Used for both endpoint drift and per-slice trajectory."""
    import numpy as np
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(1.0 - (a @ b) / (na * nb))


def change_point_year(series: list[tuple[int, float]], min_z: float = 2.0):
    """(year, confidence) of the steepest single-step rise in a distance-from-reference
    trajectory — or (None, score) when that rise is not a clear outlier (#44).

    `series` is [(year, distance)] sorted by year; the first element is the reference
    slice (distance 0). We deliberately skip the reference→first step: distance jumps
    from 0 (self) to ~0.3+ purely from independent-model variance, so that step would
    always win. Scanning consecutive steps from the first comparison slice onward
    (series[1:]) isolates real change.

    The old version returned the argmax step unconditionally — presenting a year as
    fact even when several steps were near-equal noise. We now SCORE the winning step
    against the robust spread (median/MAD) of the OTHER steps and report a year only
    when that z-score ≥ min_z; otherwise the change point is suppressed (None) because
    it's indistinguishable from the surrounding wobble. The score is returned in both
    cases so callers can persist/flag it. Needs ≥2 comparison steps (≥4 points)."""
    import numpy as np

    steps = [(y1, d1 - d0) for (_, d0), (y1, d1) in zip(series[1:], series[2:])]
    if len(steps) < 2:
        return None, None
    years = [y for y, _ in steps]
    vals = np.asarray([s for _, s in steps], dtype=float)
    i_max = int(np.argmax(vals))
    biggest = float(vals[i_max])
    if biggest <= 0:
        return None, 0.0  # trajectory only ever falls among comparison slices
    others = np.delete(vals, i_max)
    med = float(np.median(others))
    mad_sigma = 1.4826 * float(np.median(np.abs(others - med)))  # robust σ from MAD
    sigma = mad_sigma if mad_sigma > 1e-9 else float(np.std(others))
    # Absolute floor: adjacent-slice cosine steps carry ~0.05 of independent-model
    # noise, so we never divide by a spuriously tiny spread (and a flat baseline with
    # one true spike scores as strongly confident rather than collapsing to 0/0).
    scale = max(sigma, 0.05)
    score = (biggest - med) / scale
    cp_year = years[i_max] if score >= min_z else None
    return cp_year, round(float(score), 2)


def _align(base_wv, other_wv, anchor_top: int = 5000,
           prune_iters: int = 2, prune_frac: float = 0.25):
    """Rotate other_wv into base_wv's frame via orthogonal Procrustes (#48).

    The rotation is fit ONLY on stable anchor words, not the whole shared vocabulary.
    If every shared word votes on the rotation, the very words that drifted pull the
    frame toward themselves and inflate (or mask) everyone else's measured drift —
    the alignment is contaminated by the signal we're trying to measure. So we:
      1. restrict candidate anchors to the high-frequency core present in BOTH slices
         (gensim orders index_to_key by descending count, so rank < anchor_top picks
         the frequent words, whose vectors are well-estimated and individually stable);
      2. iteratively drop the highest-residual anchors — the ones that actually moved —
         and refit, so the final frame is defined by words that genuinely held still.
    Returns (aligned_matrix, key_index) covering ALL of other_wv's keys (the fitted
    rotation is applied to every vector, not just the anchors)."""
    import numpy as np
    from scipy.linalg import orthogonal_procrustes

    base_rank = {w: i for i, w in enumerate(base_wv.index_to_key)}
    # Candidate anchors: shared words inside the top-`anchor_top` frequency core of both.
    anchors = [w for i, w in enumerate(other_wv.index_to_key)
               if i < anchor_top and base_rank.get(w, anchor_top) < anchor_top]
    if len(anchors) < 10:  # frequent core too sparse → fall back to full shared vocab
        anchors = [w for w in other_wv.index_to_key if w in base_rank]
    if len(anchors) < 10:
        return None, None

    A = np.vstack([other_wv[w] for w in anchors])   # to be rotated
    B = np.vstack([base_wv[w] for w in anchors])     # target frame
    R, _ = orthogonal_procrustes(A, B)
    # Iteratively prune drifted anchors (highest alignment residual) and refit.
    for _ in range(max(0, prune_iters)):
        if len(A) < 20:
            break
        resid = np.linalg.norm(A @ R - B, axis=1)
        thresh = np.quantile(resid, 1.0 - prune_frac)
        keep = resid <= thresh
        if keep.all() or int(keep.sum()) < 10:
            break
        A, B = A[keep], B[keep]
        R, _ = orthogonal_procrustes(A, B)

    # Apply the fitted rotation to *all* of other_wv's vectors, not just the anchors.
    full = np.vstack([other_wv[w] for w in other_wv.index_to_key])
    aligned = full @ R
    return aligned, {w: i for i, w in enumerate(other_wv.index_to_key)}


def ingest_diachronic(
    db_path: str,
    corpus: str,
    slices: list[tuple[int, str]],
    source: str,
    top_n: int = DEFAULT_TOP_N,
    vector_size: int = 100,
    window: int = 5,
    min_count: int = 10,
    epochs: int = 5,
    min_vocab_frac: float = 0.4,
    overlap_k: int = 150,
    overlap_restrict_vocab: int = 10000,
    pool_window: int = 0,
    pool_cap: int = 500_000,
    pool_adaptive: bool = False,
    pool_target: int = 200_000,
    seed: int = 0,
    neighbor_min_count: int = 50,
) -> dict:
    import numpy as np

    if not slices:
        sys.exit("No slices to process.")
    random.seed(seed)  # makes the pooled-reservoir sampling reproducible
    years = [y for y, _ in slices]

    conn = init_db(db_path)
    record_attribution(conn, source)
    # Forward-compat: older DBs lack the neighbor_overlap column (added with the
    # Gonen 2020 measure). ALTER ADD COLUMN is idempotent-guarded here.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(diachronic_drift)")}
    if "neighbor_overlap" not in cols:
        conn.execute("ALTER TABLE diachronic_drift ADD COLUMN neighbor_overlap REAL")
    if "change_point_year" not in cols:
        conn.execute("ALTER TABLE diachronic_drift ADD COLUMN change_point_year INTEGER")
    if "change_point_score" not in cols:  # #44: robust z of the winning step (incl. suppressed)
        conn.execute("ALTER TABLE diachronic_drift ADD COLUMN change_point_score REAL")
    # Forward-compat: the trajectory table (#35) may not exist on older DBs.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS diachronic_trajectory ("
        "id INTEGER PRIMARY KEY, lemma_id INTEGER NOT NULL, corpus TEXT NOT NULL, "
        "year INTEGER NOT NULL, distance_from_ref REAL NOT NULL, source TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_diac_traj_lemma "
        "ON diachronic_trajectory (lemma_id, corpus, year)"
    )
    conn.execute("DELETE FROM diachronic_drift WHERE corpus = ?", (corpus,))
    conn.execute("DELETE FROM diachronic_neighbors WHERE corpus = ?", (corpus,))
    conn.execute("DELETE FROM diachronic_trajectory WHERE corpus = ?", (corpus,))

    # lemma maps for resolving vector keys back to word pages. Vectors are now keyed
    # on the ACCENT-PRESERVING token (cs.tokenize → normalize_keep_accents), so both
    # the surface→lemma map and the lemma's own vector key must use the same fold;
    # otherwise accent homographs (νόμος/νομός) would collide on one blended vector.
    surface_to_lemma: dict[str, int] = {}
    for surface, lemma_id in conn.execute("SELECT surface, lemma_id FROM search_index"):
        key = normalize_keep_accents(surface)
        if key:
            surface_to_lemma.setdefault(key, lemma_id)
    lemma_disp: dict[int, str] = {}
    lemma_norm: dict[int, str] = {}
    for lid, lemma in conn.execute("SELECT id, lemma FROM lemmas"):
        lemma_disp[lid] = lemma
        lemma_norm[lid] = normalize_keep_accents(lemma)

    # Train one model per slice. With --pool-window>0 each model trains on a ±window
    # band of adjacent years (#37) — still labeled by its centre year — so thin years
    # borrow data from their neighbors and rare-word vectors stabilize.
    path_by_year = {y: p for y, p in slices}
    pool_tmp_dir = None
    line_count: dict[int, int] = {}
    if pool_window > 0:
        pool_tmp_dir = os.path.join(PROCESSED, corpus, "_pool_tmp")
        os.makedirs(pool_tmp_dir, exist_ok=True)
        if pool_adaptive:
            # one cheap pass to size each slice; the adaptive window needs per-year counts
            for y, p in slices:
                with open(p, encoding="utf-8") as fh:
                    line_count[y] = sum(1 for _ in fh)
            print(f"Training {len(slices)} adaptively-pooled word2vec model(s) for "
                  f"corpus={corpus} (target {pool_target} lines, ≤±{pool_window} yr, "
                  f"cap {pool_cap}/slice)…", file=sys.stderr)
        else:
            print(f"Training {len(slices)} pooled word2vec model(s) for corpus={corpus} "
                  f"(±{pool_window}-yr band, cap {pool_cap}/slice)…", file=sys.stderr)
    else:
        print(f"Training {len(slices)} word2vec model(s) for corpus={corpus}…", file=sys.stderr)
    wvs: dict[int, object] = {}
    for year, path in slices:
        if pool_window > 0:
            members = (_adaptive_members(year, years, line_count, pool_target, pool_window)
                       if pool_adaptive else _pool_members(year, years, pool_window))
            mpaths = [path_by_year[m] for m in members]
            ppath = _pooled_to_tempfile(mpaths, pool_cap, pool_tmp_dir)
            try:
                wvs[year] = _train(ppath, vector_size, window, min_count, epochs).wv
            finally:
                try:
                    os.remove(ppath)
                except OSError:
                    pass
            print(f"  · {corpus}/{year}: vocab {len(wvs[year].index_to_key)} "
                  f"(pooled {members[0]}–{members[-1]}, {len(members)} yr)", file=sys.stderr)
        else:
            wvs[year] = _train(path, vector_size, window, min_count, epochs).wv
            print(f"  · {corpus}/{year}: vocab {len(wvs[year].index_to_key)}", file=sys.stderr)
    if pool_tmp_dir:
        try:
            os.rmdir(pool_tmp_dir)
        except OSError:
            pass

    # Re-anchor the endpoints to DENSE slices. A thin early slice (e.g. parliament
    # 1989, with few digitized speeches) yields a tiny vocabulary, so most common
    # words never get a vector there and fall out of both drift and 'then'
    # neighbors. We skip slices whose vocab is below `min_vocab_frac` of the
    # densest slice, so the anchors are the first/last *substantial* years. This
    # only moves the endpoints; the cardinal rule (one corpus per axis) is intact.
    vocab_sizes = {y: len(wvs[y].index_to_key) for y in years}
    max_vocab = max(vocab_sizes.values()) if vocab_sizes else 0
    threshold = max_vocab * min_vocab_frac
    dense = [y for y in years if vocab_sizes[y] >= threshold]
    if not dense:
        dense = years
    first_y, last_y = dense[0], dense[-1]
    skipped = [y for y in years if y not in dense]
    if skipped:
        print(f"  · anchoring drift to dense slices {first_y}…{last_y} "
              f"(skipped sparse: {skipped})", file=sys.stderr)

    # ── era-neighbors: within-slice nearest words for the anchored first & last ──
    # Frequency floor (#51): a word seen only a handful of times IN THAT ERA has a
    # vector estimated from too few contexts, so its "nearest neighbours" are mostly
    # noise — yet they'd be shown with the same authority as a common word's. The
    # word2vec min_count (10) is far too low a bar for a trustworthy neighbour list, so
    # we SUPPRESS the list for any lemma whose per-era training count is below
    # `neighbor_min_count`; the word still gets drift/trajectory, just no era-neighbours.
    neighbor_rows = 0
    suppressed_neighbors = 0
    era_years = sorted({first_y, last_y})
    for year in era_years:
        wv = wvs[year]
        for lid, nlemma in lemma_norm.items():
            if nlemma not in wv:
                continue
            if wv.get_vecattr(nlemma, "count") < neighbor_min_count:
                suppressed_neighbors += 1  # too rare this era → neighbours are noise
                continue
            try:
                cands = wv.most_similar(nlemma, topn=CANDIDATE_POOL)
            except KeyError:
                continue
            chosen: list[tuple[str, float, int]] = []
            seen: set[int] = set()
            for token, score in cands:
                if len(token) < MIN_NEIGHBOR_LEN or token in STOPWORDS:
                    continue
                nb_lid = surface_to_lemma.get(token)
                if nb_lid is None or nb_lid == lid or nb_lid in seen:
                    continue
                seen.add(nb_lid)
                chosen.append((lemma_disp.get(nb_lid, token), round(float(score), 4), nb_lid))
                if len(chosen) >= top_n:
                    break
            for seq, (disp, score, nb_lid) in enumerate(chosen):
                conn.execute(
                    "INSERT INTO diachronic_neighbors "
                    "(lemma_id, corpus, year, neighbor, neighbor_lemma_id, score, source, seq) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (lid, corpus, year, disp, nb_lid, score, source, seq),
                )
                neighbor_rows += 1

    # ── trajectory (#35): the SHAPE of change across ALL dense slices ──
    # Align EVERY dense slice to the reference (first dense) slice and record each
    # lemma's cosine distance from its reference vector. Endpoint-only drift hides
    # words that drifted then reverted (low first↔last, high mid-series bump); the
    # full trajectory exposes that, and the change-point is the steepest single
    # step. The reference slice maps to itself (distance 0).
    traj_rows = 0
    change_point: dict[int, int] = {}
    change_point_score: dict[int, float] = {}  # #44: kept for every lemma, incl. suppressed
    base_traj_wv = wvs[first_y]
    if len(dense) >= 2:
        aligned_by_year: dict[int, tuple] = {}
        for y in dense:
            if y == first_y:
                continue
            al, ki = _align(base_traj_wv, wvs[y])
            if al is not None:
                aligned_by_year[y] = (al, ki)
        for lid, nlemma in lemma_norm.items():
            if nlemma not in base_traj_wv:
                continue
            v_ref = base_traj_wv[nlemma]
            series: list[tuple[int, float]] = []
            for y in dense:
                if y == first_y:
                    series.append((y, 0.0))
                elif y in aligned_by_year:
                    al, ki = aligned_by_year[y]
                    if nlemma in ki:
                        series.append((y, round(_cos_dist(v_ref, al[ki[nlemma]]), 4)))
            if len(series) < 2:
                continue
            for y, dist in series:
                conn.execute(
                    "INSERT INTO diachronic_trajectory "
                    "(lemma_id, corpus, year, distance_from_ref, source) VALUES (?,?,?,?,?)",
                    (lid, corpus, y, dist, source),
                )
                traj_rows += 1
            cp_year, cp_score = change_point_year(series)
            if cp_score is not None:
                change_point_score[lid] = cp_score
            if cp_year is not None:
                change_point[lid] = cp_year

    # ── drift: cosine distance first vs last (anchored), in a shared frame ──
    # Plus a SECOND, frequency-robust change measure (Gonen et al. 2020): the
    # neighbor-set overlap. cosine drift is sensitive to a word's frequency
    # (Dubossarsky 2017); the share of a word's top-k nearest neighbors that
    # survive from the first slice to the last is far more stable and directly
    # interpretable ("it used to sit near X, now near Y"). Cosine neighbours are
    # invariant under the orthogonal alignment rotation, so we read them straight
    # from each slice's own model — no alignment needed for this measure.
    drift_rows = 0
    if first_y != last_y:
        base_wv, other_wv = wvs[first_y], wvs[last_y]
        aligned, key_index = _align(base_wv, other_wv)
        if aligned is not None:
            def _overlap_change(nlemma: str):
                """1 − Jaccard of top-k neighbor word-sets (first vs last slice).
                None when the word lacks enough neighbors in either slice.

                Neighbours are drawn from a SHARED frequent vocabulary
                (``restrict_vocab``) and at a large k. Without this the metric
                saturates: two independently-trained slice models share almost
                none of their raw top-50 neighbours because each slice carries a
                different tail of rare surface forms. Restricting the candidate
                pool to the N most frequent words — present in both slices — and
                widening k makes the neighbour sets comparable, which is the
                setup Gonen et al. (2020) rely on."""
                try:
                    a = {t for t, _ in base_wv.most_similar(
                        nlemma, topn=overlap_k, restrict_vocab=overlap_restrict_vocab)}
                    b = {t for t, _ in other_wv.most_similar(
                        nlemma, topn=overlap_k, restrict_vocab=overlap_restrict_vocab)}
                except KeyError:
                    return None
                union = a | b
                if not union:
                    return None
                return round(1.0 - len(a & b) / len(union), 4)

            for lid, nlemma in lemma_norm.items():
                if nlemma not in base_wv or nlemma not in key_index:
                    continue
                v_first = base_wv[nlemma]
                v_last = aligned[key_index[nlemma]]
                drift = round(_cos_dist(v_first, v_last), 4)
                overlap = _overlap_change(nlemma) if nlemma in other_wv else None
                conn.execute(
                    "INSERT INTO diachronic_drift "
                    "(lemma_id, corpus, drift_score, neighbor_overlap, first_year, "
                    "last_year, n_slices, change_point_year, change_point_score, source) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (lid, corpus, drift, overlap, first_y, last_y, len(dense),
                     change_point.get(lid), change_point_score.get(lid), source),
                )
                drift_rows += 1
        else:
            print("  ! too little shared vocab to align; skipping drift.", file=sys.stderr)
    else:
        print("  · only one dense slice — drift needs ≥2, skipping (era-neighbors still stored).",
              file=sys.stderr)

    conn.commit()
    conn.close()
    return {
        "corpus": corpus,
        "years": years,
        "n_slices": len(slices),
        "drift_first_year": first_y,
        "drift_last_year": last_y,
        "pool_window": pool_window,
        "pool_adaptive": pool_adaptive,
        "pool_target": pool_target if (pool_window > 0 and pool_adaptive) else None,
        "pool_cap": pool_cap if pool_window > 0 else None,
        "dense_slices": len(dense),
        "skipped_sparse": skipped,
        "drift_rows": drift_rows,
        "trajectory_rows": traj_rows,
        "lemmas_with_change_point": len(change_point),
        "era_neighbor_rows": neighbor_rows,
        "neighbors_suppressed_low_freq": suppressed_neighbors,
        "neighbor_min_count": neighbor_min_count,
        "era_years": era_years,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Layer C: diachronic semantic drift within one corpus.")
    ap.add_argument("--db", default="data/db/lexorama.sqlite")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--leipzig-dir", help="Directory holding Leipzig year-folders.")
    src.add_argument("--parliament-csv", help="Greek Parliament Proceedings CSV (corpus=parliament).")
    ap.add_argument("--leipzig-source",
                    help="When several Leipzig corpora share --leipzig-dir, pick ONE by its "
                         "source prefix ('ell_news', 'ell_wikipedia') or clean label "
                         "('news', 'wiki'). The corpus axis label defaults from it.")
    ap.add_argument("--corpus", help="Override the corpus label.")
    ap.add_argument("--text-col", default="speech")
    ap.add_argument("--date-col", default="sitting_date")
    ap.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    ap.add_argument("--vector-size", type=int, default=100)
    ap.add_argument("--min-count", type=int, default=10)
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--min-vocab-frac", type=float, default=0.4,
                    help="Skip slices whose vocab is below this fraction of the densest "
                         "slice when choosing the drift endpoints (re-anchors sparse early years).")
    ap.add_argument("--overlap-k", type=int, default=150,
                    help="Top-k neighbors used for the Gonen 2020 neighbor-overlap drift measure.")
    ap.add_argument("--overlap-restrict-vocab", type=int, default=10000,
                    help="Restrict Gonen neighbor candidates to the N most frequent words "
                         "(shared pool across slices) so the overlap measure stops saturating.")
    ap.add_argument("--pool-window", type=int, default=0,
                    help="Pool a ±N-year band of adjacent slices into each model's training "
                         "data (#37: stabilizes rare-word vectors in thin years). 0 = per-year.")
    ap.add_argument("--pool-cap", type=int, default=500_000,
                    help="Max sentences per pooled slice (uniform reservoir); bounds runtime on "
                         "already-dense years. Ignored when --pool-window 0.")
    ap.add_argument("--pool-adaptive", action="store_true",
                    help="#49: grow each slice's window only until it reaches --pool-target "
                         "lines (≤ --pool-window), so dense years keep full temporal resolution "
                         "and only thin years borrow neighbours. Treats --pool-window as the MAX.")
    ap.add_argument("--pool-target", type=int, default=200_000,
                    help="Target lines per slice for --pool-adaptive (expand window until met).")
    ap.add_argument("--seed", type=int, default=0, help="Seed for pooled-reservoir sampling.")
    ap.add_argument("--neighbor-min-count", type=int, default=50,
                    help="Suppress era-neighbours for a lemma whose per-era training count is "
                         "below this (#51: rare-word neighbours are noise). 0 disables the floor.")
    ap.add_argument("--skip-materialize", action="store_true",
                    help="Reuse already-materialized data/processed/diachronic/<corpus>/*.txt "
                         "instead of re-reading the source (fast re-runs of just the modeling).")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        sys.exit(f"DB not found: {args.db} (build the lexical store first).")

    if args.leipzig_dir:
        avail = cs.discover_leipzig_sources(args.leipzig_dir)
        if args.leipzig_source is None and len(avail) > 1:
            sys.exit(f"--leipzig-dir holds multiple corpora {avail}; pass --leipzig-source "
                     "to pick one (each stays on its own axis — never merged).")
        label = cs.LEIPZIG_CORPUS_LABELS.get(args.leipzig_source or "", args.leipzig_source)
        if label is None and avail:
            label = next(iter(avail))
        corpus = args.corpus or label or "news"
    else:
        corpus = args.corpus or "parliament"
    source = "leipzig-diachronic" if args.leipzig_dir else "parliament-diachronic"

    if args.skip_materialize:
        slices = existing_slices(corpus)
        if not slices:
            sys.exit(f"--skip-materialize set but no files under {os.path.join(PROCESSED, corpus)}.")
        print(f"Reusing {len(slices)} materialized slice(s) for corpus={corpus}.", file=sys.stderr)
    elif args.leipzig_dir:
        slices = materialize_leipzig(args.leipzig_dir, corpus, args.leipzig_source)
    else:
        slices = materialize_parliament(args.parliament_csv, args.text_col, args.date_col)

    import json
    print(json.dumps(
        ingest_diachronic(
            args.db, corpus, slices, source, args.top_n,
            args.vector_size, min_count=args.min_count, epochs=args.epochs,
            min_vocab_frac=args.min_vocab_frac, overlap_k=args.overlap_k,
            overlap_restrict_vocab=args.overlap_restrict_vocab,
            pool_window=args.pool_window, pool_cap=args.pool_cap,
            pool_adaptive=args.pool_adaptive, pool_target=args.pool_target,
            seed=args.seed, neighbor_min_count=args.neighbor_min_count,
        ),
        indent=2, ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
