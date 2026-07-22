"""Supervised domain attribution (#38): predict a subject field for every content
lemma from its corpus embedding, trained on Wiktionary's clean single-domain tags.

The "ανά πεδίο" exploration used to assign a lemma to a field (ιατρική, νομική,
πληροφορική …) purely by intersecting `senses.tags` with a fixed field list. That
is only as good as Wiktionary's topic-tagging: ~15k lemmas carry such a tag, and
the vast majority of content words get no field at all. This pipeline is the
distant-supervision upgrade the backlog asked for — a defensible, usage-based
classifier instead of a lexicon lookup:

  1. Train a word2vec model over ALL materialized diachronic slices, pooled across
     corpora. A word's subject field is a STATIC lexical property (αρτηρία is
     medical in 1989 and in 2024), so — unlike drift work, where each slice must
     stay a single consistent corpus — pooling every year of every corpus into one
     embedding is exactly right here: we want maximal contextual coverage.
  2. Gold labels = lemmas Wiktionary tags with EXACTLY ONE of our fields. A single
     unambiguous tag is clean supervision; multi-tag lemmas are kept as gold at
     write time but excluded from TRAINING so the classifier learns crisp fields.
  3. X = the lemma's L2-normalized embedding vector, y = its field. Train a
     class-balanced multinomial logistic-regression classifier. Isotonic calibration
     (CalibratedClassifierCV) is applied ONLY IF it lowers held-out ECE — on this small
     multiclass data the base model is already well-calibrated (~0.04) and forcing
     isotonic overfits and hurts, so it is not applied blindly (#47). Report held-out
     accuracy / macro-F1, the ECE of both, and the precision+coverage of the DEPLOYED
     rule — honestly: raw accuracy is only ~0.56 on 18 fields, so the abstention, not the
     point estimate, is what makes the inferences usable.
  4. Predict a top field for every CONTENT lemma (noun/adj/verb) with a vector and no
     gold tag — but ABSTAIN (store nothing) unless the probability clears that field's OWN
     threshold (tuned to `target_precision`) and beats the runner-up by ≥ MARGIN_FLOOR. A
     single absolute gate is meaningless once class_weight skews the posteriors (F17), so
     thresholds are per-class.

Provenance is preserved end to end ("sources define, AI explains"): gold tags are
written verbatim (source='wiktionary-tag', score=1.0); classifier guesses are
written as source='classifier' with their confidence, and the API/UI gate and
label them as inferred. Nothing silently overwrites a Wiktionary tag.

Idempotent: clears and rewrites `lemma_domain_pred`. Requires gensim + scikit-learn.

Run (STOP the API first — this writes the WAL DB):
    PYTHONIOENCODING=utf-8 python pipelines/ingest/classify_domains.py \
        --db data/db/lexorama.sqlite
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipelines", "ingest"))
from ingest_kaikki import init_db  # noqa: E402
from normalize_greek import normalize_keep_accents  # noqa: E402

# Must match _FIELD_DOMAINS in services/api/app/main.py — the fields surfaced on
# the "ανά πεδίο" exploration. Broad, well-populated subject areas only.
FIELD_DOMAINS = [
    "medicine", "law", "politics", "economics", "computing", "technology",
    "military", "religion", "philosophy", "music", "sports", "physics",
    "chemistry", "biology", "mathematics", "history", "linguistics", "nautical",
]

CONTENT_POS = ("noun", "adj", "verb")
SLICE_GLOB = os.path.join("data", "processed", "diachronic", "*", "*.txt")

# Abstention (#47). A prediction is stored only when its CALIBRATED probability clears
# that field's OWN tuned threshold (tune_class_thresholds, for `target_precision`) AND
# beats the runner-up by ≥ MARGIN_FLOOR; otherwise the word is left unlabelled. A single
# absolute floor across 18 class-weight-skewed fields is meaningless (F17), so the
# per-class thresholds replace the old CONF_FLOOR=0.50 gate.
MARGIN_FLOOR = 0.10


class SliceReader:
    """Re-iterable token stream over every diachronic slice of every corpus,
    pooled. Slices are already accent-preservingly normalized (cs.tokenize →
    normalize_keep_accents), space-separated, one sentence per line, so
    tokenization is a bare split. Pooling all years/corpora is correct here because
    domain is a static lexical property (see module docstring)."""

    def __init__(self, paths: list[str]):
        self.paths = paths

    def __iter__(self):
        for path in self.paths:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    toks = line.split()
                    if toks:
                        yield toks


def _gold_domains(conn) -> dict[int, set[str]]:
    """lemma_id → set of field tags (senses.tags ∩ FIELD_DOMAINS). Includes
    multi-tag lemmas; the caller filters to single-tag for training."""
    wanted = set(FIELD_DOMAINS)
    out: dict[int, set[str]] = {}
    rows = conn.execute(
        "SELECT lemma_id, tags FROM senses "
        "WHERE tags IS NOT NULL AND tags != '' AND tags != '[]'"
    ).fetchall()
    for lemma_id, tags in rows:
        try:
            parsed = json.loads(tags)
        except (ValueError, TypeError):
            continue
        for t in parsed:
            tl = str(t).lower()
            if tl in wanted:
                out.setdefault(lemma_id, set()).add(tl)
    return out


def classify_domains(
    db_path: str,
    vector_size: int = 150,
    window: int = 5,
    min_count: int = 3,
    epochs: int = 5,
    sg: int = 1,
    test_size: float = 0.2,
    target_precision: float = 0.70,
    seed: int = 0,
) -> dict:
    import numpy as np
    from collections import Counter
    from gensim.models import Word2Vec
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.model_selection import train_test_split

    sys.path.insert(0, os.path.join(ROOT, "pipelines", "analysis"))
    from calibration import (  # noqa: E402
        expected_calibration_error, tune_class_thresholds, decide_with_abstain,
        precision_coverage_report,
    )

    def _fit(estimator_data, xx, yy, cv):
        """Isotonic-calibrated classifier when the smallest class supports the CV folds,
        else the raw estimator — so the rebuild never crashes on a thin field (#47).
        Returns (fitted, calibrated?)."""
        base = LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced", n_jobs=-1)
        if cv >= 2:
            try:
                return CalibratedClassifierCV(base, method="isotonic", cv=cv).fit(xx, yy), True
            except Exception as exc:  # tiny class / fold failure → fall back, don't crash
                print(f"  calibration fell back to raw ({type(exc).__name__}: {exc})",
                      file=sys.stderr)
        return LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced",
                                  n_jobs=-1).fit(xx, yy), False

    paths = sorted(glob.glob(os.path.join(ROOT, SLICE_GLOB)))
    if not paths:
        sys.exit(f"No diachronic slices under {SLICE_GLOB}")
    print(f"Pooling {len(paths)} slice files into one embedding…", file=sys.stderr)

    model = Word2Vec(
        sentences=SliceReader(paths),
        vector_size=vector_size,
        window=window,
        min_count=min_count,
        workers=os.cpu_count() or 4,
        sg=sg,           # skip-gram (1) — better vectors for the rare technical
                         # vocabulary that dominates subject domains than CBOW (0)
        epochs=epochs,
        seed=seed,
    )
    wv = model.wv
    print(f"Embedding vocab: {len(wv.index_to_key)} tokens.", file=sys.stderr)

    conn = init_db(db_path)
    conn.row_factory = __import__("sqlite3").Row

    gold = _gold_domains(conn)

    # lemma_id → (display, embedding_key, pos) for content lemmas only. The
    # embedding is trained on ACCENT-PRESERVING tokens (cs.tokenize), so the lookup
    # key is normalize_keep_accents(lemma), NOT the accent-folded normalized_lemma —
    # otherwise νόμος/νομός would share one (blended) vector and one predicted field.
    lemmas: dict[int, tuple[str, str, str]] = {}
    for r in conn.execute(
        "SELECT id, lemma, pos FROM lemmas WHERE pos IN (?,?,?)",
        CONTENT_POS,
    ):
        lemmas[r["id"]] = (r["lemma"], normalize_keep_accents(r["lemma"]), r["pos"])

    def vec(nlemma: str):
        return wv[nlemma] if nlemma in wv else None

    # ── Build training set: single-domain lemmas that have a vector ───────────
    X, y, train_ids = [], [], []
    for lid, doms in gold.items():
        if len(doms) != 1:
            continue
        meta = lemmas.get(lid)
        # gold tags exist on lemmas of any POS; train on content lemmas w/ a vector
        nlemma = meta[1] if meta else None
        v = vec(nlemma) if nlemma else None
        if v is None:
            continue
        X.append(v)
        y.append(next(iter(doms)))
        train_ids.append(lid)
    X = np.asarray(X, dtype="float32")
    # L2-normalize → logistic regression operates on cosine geometry
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    X = X / norms
    y = np.asarray(y)
    print(f"Training examples: {len(y)} across {len(set(y))} fields.", file=sys.stderr)

    # Held-out evaluation. Calibrate ONLY IF isotonic improves held-out ECE. On this small
    # multiclass data the base logistic regression is already well-calibrated (ECE ~0.04),
    # and forcing isotonic overfits the per-class calibration map and DEGRADES ECE (measured
    # 0.042→0.118). The real #47 fix is the per-class abstain thresholds (F16/F17); the
    # calibration step earns its place only when it lowers ECE, else we deploy raw probs.
    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=test_size, random_state=seed, stratify=y
    )
    cv = max(2, min(5, min(Counter(ytr).values())))
    raw_eval = LogisticRegression(
        max_iter=2000, C=4.0, class_weight="balanced", n_jobs=-1).fit(Xtr, ytr)
    cal_eval, cal_ok = _fit(None, Xtr, ytr, cv)   # isotonic when the folds allow

    def _ece_of(model):
        cls = list(model.classes_)
        P = model.predict_proba(Xte)
        correct = [1.0 if cls[j] == yy else 0.0 for j, yy in zip(P.argmax(axis=1), yte)]
        return round(expected_calibration_error(P.max(axis=1), correct), 4)

    ece_raw = _ece_of(raw_eval)
    ece_cal = _ece_of(cal_eval) if cal_ok else ece_raw
    use_cal = bool(cal_ok and ece_cal < ece_raw)
    clf_eval = cal_eval if use_cal else raw_eval
    classes = list(clf_eval.classes_)
    probs_te = clf_eval.predict_proba(Xte)
    pred_te = [classes[i] for i in probs_te.argmax(axis=1)]
    acc = float(accuracy_score(yte, pred_te))
    macro_f1 = float(f1_score(yte, pred_te, average="macro"))

    # Per-class abstain thresholds tuned for a precision target (#47/F17): one absolute
    # gate is meaningless once class_weight skews posteriors. Tuned on the training probs
    # of the deployed model; reported honestly on the held-out test set (F45).
    thresholds = tune_class_thresholds(
        clf_eval.predict_proba(Xtr), ytr, classes,
        target_precision=target_precision, min_threshold=0.30,
    )
    deployed = precision_coverage_report(probs_te, yte, classes, thresholds, MARGIN_FLOOR)
    print(f"Held-out accuracy={acc:.3f}  macro-F1={macro_f1:.3f}  "
          f"ECE raw={ece_raw} cal={ece_cal} → {'calibrated' if use_cal else 'uncalibrated'}; "
          f"deployed-precision={deployed['precision_on_labeled']} @ coverage={deployed['coverage']}",
          file=sys.stderr)

    # Production model: the SAME choice (calibrated iff it helped), refit on ALL gold.
    cv_prod = max(2, min(5, min(Counter(y).values())))
    if use_cal:
        clf, calibrated = _fit(None, X, y, cv_prod)
    else:
        clf = LogisticRegression(
            max_iter=2000, C=4.0, class_weight="balanced", n_jobs=-1).fit(X, y)
        calibrated = False
    classes = list(clf.classes_)
    cls_index = {c: i for i, c in enumerate(classes)}

    # ── Write predictions ─────────────────────────────────────────────────────
    conn.execute("DELETE FROM lemma_domain_pred")

    gold_rows = 0
    # Gold tags (single AND multi) — verbatim, authoritative, full provenance.
    for lid, doms in gold.items():
        for d in sorted(doms):
            conn.execute(
                "INSERT INTO lemma_domain_pred (lemma_id, domain, score, rank, source) "
                "VALUES (?,?,?,?,?)",
                (lid, d, 1.0, 1, "wiktionary-tag"),
            )
            gold_rows += 1

    # Classifier predictions for content lemmas that have a vector and NO gold tag.
    pred_ids, pred_vecs = [], []
    for lid, (_disp, nlemma, _pos) in lemmas.items():
        if lid in gold:
            continue
        v = vec(nlemma)
        if v is None:
            continue
        pred_ids.append(lid)
        pred_vecs.append(v)
    pred_rows = 0
    abstained = 0
    if pred_ids:
        P = np.asarray(pred_vecs, dtype="float32")
        pn = np.linalg.norm(P, axis=1, keepdims=True)
        pn[pn == 0] = 1.0
        P = P / pn
        probs = clf.predict_proba(P)
        # Abstain option (#47/F17): assign a field only when the CALIBRATED probability
        # clears that field's OWN tuned threshold and beats the runner-up by ≥ MARGIN_FLOOR.
        # A low-evidence word and a confident-but-ambiguous word are both left unlabelled.
        for i, lid in enumerate(pred_ids):
            pred = decide_with_abstain(probs[i], classes, thresholds, MARGIN_FLOOR)
            if pred is None:
                abstained += 1
                continue
            conn.execute(
                "INSERT INTO lemma_domain_pred (lemma_id, domain, score, rank, source) "
                "VALUES (?,?,?,?,?)",
                (lid, pred, round(float(probs[i, cls_index[pred]]), 4), 1, "classifier"),
            )
            pred_rows += 1

    conn.commit()
    # Per-field count of stored classifier rows, for the report.
    by_field = {
        row["domain"]: row["n"] for row in conn.execute(
            "SELECT domain, COUNT(*) n FROM lemma_domain_pred "
            "WHERE source='classifier' GROUP BY domain ORDER BY n DESC"
        )
    }
    import manifest as _mf
    _mf.record_build(conn, "classify_domains",
                     version=f"cal={'isotonic' if calibrated else 'none'}",
                     params={"calibrated": calibrated, "target_precision": target_precision,
                             "ece_raw": ece_raw, "ece_calibrated": ece_cal},
                     tables=["lemma_domain_pred"])
    conn.close()

    return {
        "embedding_vocab": len(wv.index_to_key),
        "training_examples": int(len(y)),
        "fields": len(set(y.tolist())),
        "held_out_accuracy": round(acc, 4),
        "held_out_macro_f1": round(macro_f1, 4),
        "calibration": "isotonic (improved ECE)" if calibrated else "none (raw already well-calibrated)",
        "ece_raw": ece_raw,
        "ece_calibrated": ece_cal,
        "target_precision": target_precision,
        "deployed_precision_on_labeled": deployed["precision_on_labeled"],
        "deployed_coverage": deployed["coverage"],
        "deployed_precision_by_field": {c: v["precision"] for c, v in deployed["per_field"].items()},
        "per_class_thresholds": {c: round(t, 4) for c, t in thresholds.items()},
        "margin_floor": MARGIN_FLOOR,
        "gold_rows": gold_rows,
        "classifier_rows": pred_rows,
        "classifier_abstained": abstained,
        "classifier_rows_by_field": by_field,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Supervised domain attribution (#38).")
    ap.add_argument("--db", default="data/db/lexorama.sqlite")
    ap.add_argument("--vector-size", type=int, default=150)
    ap.add_argument("--min-count", type=int, default=3)
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--sg", type=int, default=1, choices=(0, 1),
                    help="1=skip-gram (default, better for rare domain terms), 0=CBOW")
    ap.add_argument("--target-precision", type=float, default=0.70,
                    help="per-field precision target the abstain thresholds are tuned to (#47)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    if not os.path.exists(args.db):
        sys.exit(f"DB not found: {args.db}")
    print(json.dumps(
        classify_domains(
            args.db, vector_size=args.vector_size,
            min_count=args.min_count, epochs=args.epochs, sg=args.sg,
            target_precision=args.target_precision, seed=args.seed,
        ),
        indent=2, ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
