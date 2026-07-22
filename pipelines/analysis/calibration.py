"""Probability calibration + principled abstention for the domain classifier.

Methodology wave #47 (audit F16/F17/F45). Pure functions, unit-testable without the
embedding, validated offline before wiring into `classify_domains` (which only runs at
the Tier B rebuild).

The shipped classifier:
  · reports raw softmax as "confidence" though it is explicitly uncalibrated;
  · gates every one of 18 fields at a SINGLE absolute threshold (CONF_FLOOR=0.50), but
    `class_weight='balanced'` skews the posteriors so 0.50 means p≈0.076 for economics
    and p≈0.881 for medicine (F17) — one threshold cannot mean the same thing across
    classes;
  · has no reject class in EVALUATION: held-out accuracy is measured on words that have
    a field, while the model is deployed on ~93k words that mostly do not (F16), and the
    reported metric describes the split model, not the deployed abstain rule (F45).

This module provides: calibration (per-class isotonic), calibration diagnostics (ECE,
Brier, reliability curve), per-class abstain thresholds tuned to a precision target, the
deployed abstain decision, and a precision/coverage report computed under THAT rule so
the reported number matches what ships.
"""

from __future__ import annotations


# ── calibration diagnostics ──────────────────────────────────────────────────

def expected_calibration_error(confidences, correct, n_bins: int = 10) -> float:
    """ECE: average |accuracy − confidence| over confidence bins, weighted by bin size.
    `confidences` = top predicted probability per sample; `correct` = 0/1 whether that
    top prediction was right. 0 = perfectly calibrated."""
    import numpy as np
    conf = np.asarray(confidences, dtype=float)
    corr = np.asarray(correct, dtype=float)
    if conf.size == 0:
        return 0.0
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = conf.size
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        m = (conf > lo) & (conf <= hi) if i > 0 else (conf >= lo) & (conf <= hi)
        if not m.any():
            continue
        ece += (m.sum() / n) * abs(float(corr[m].mean()) - float(conf[m].mean()))
    return float(ece)


def brier_score(probs, y_true, classes) -> float:
    """Multiclass Brier score: mean squared error between the predicted probability
    vector and the one-hot truth. Lower is better; a proper scoring rule."""
    import numpy as np
    idx = {c: i for i, c in enumerate(classes)}
    P = np.asarray(probs, dtype=float)
    total = 0.0
    for row, y in zip(P, y_true):
        oh = np.zeros(len(classes))
        oh[idx[y]] = 1.0
        total += float(((row - oh) ** 2).sum())
    return total / len(y_true) if len(y_true) else 0.0


def reliability_curve(confidences, correct, n_bins: int = 10):
    """(bin_confidence, bin_accuracy, bin_count) per bin — the reliability diagram."""
    import numpy as np
    conf = np.asarray(confidences, dtype=float)
    corr = np.asarray(correct, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    out = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        m = (conf > lo) & (conf <= hi) if i > 0 else (conf >= lo) & (conf <= hi)
        if m.any():
            out.append((float(conf[m].mean()), float(corr[m].mean()), int(m.sum())))
    return out


# ── per-class isotonic calibration ───────────────────────────────────────────

class IsotonicCalibrator:
    """Per-class one-vs-rest isotonic calibration of a classifier's probability matrix.

    Isotonic regression maps each class's raw scores to empirical frequencies
    monotonically (Zadrozny & Elkan 2002; more flexible than Platt when the miscalibration
    is not sigmoidal, at the cost of needing more data — fine here, thousands of gold
    examples). Calibrated rows are renormalized to sum to 1 so they remain a distribution."""

    def __init__(self):
        self._models: dict = {}
        self.classes: list = []

    def fit(self, probs, y_true, classes):
        from sklearn.isotonic import IsotonicRegression
        import numpy as np
        self.classes = list(classes)
        P = np.asarray(probs, dtype=float)
        y = list(y_true)
        for j, c in enumerate(self.classes):
            target = np.asarray([1.0 if yy == c else 0.0 for yy in y])
            ir = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            ir.fit(P[:, j], target)
            self._models[c] = ir
        return self

    def transform(self, probs):
        import numpy as np
        P = np.asarray(probs, dtype=float)
        out = np.zeros_like(P)
        for j, c in enumerate(self.classes):
            out[:, j] = self._models[c].predict(P[:, j])
        rs = out.sum(axis=1, keepdims=True)
        rs[rs == 0] = 1.0
        return out / rs


# ── principled abstention ────────────────────────────────────────────────────

def tune_class_thresholds(probs, y_true, classes, target_precision: float = 0.70,
                          min_threshold: float = 0.30) -> dict:
    """Per-class probability threshold that achieves `target_precision` on held-out data
    (F17: a single absolute gate is meaningless once posteriors are class-skewed).

    For each class c, among the samples where c is the argmax, sort by p_c descending and
    take the LOWEST threshold whose accepted set still meets the precision target — most
    coverage at the required precision. If even the single most-confident prediction can't
    reach the target, the threshold is set to 1.01 (the class effectively abstains
    always). Never drops below `min_threshold`."""
    import numpy as np
    P = np.asarray(probs, dtype=float)
    y = np.asarray(list(y_true))
    cls_idx = {c: j for j, c in enumerate(classes)}
    argmax = P.argmax(axis=1)
    thresholds: dict = {}
    for c in classes:
        j = cls_idx[c]
        mask = argmax == j
        if not mask.any():
            thresholds[c] = 1.01
            continue
        scores = P[mask, j]
        correct = (y[mask] == c).astype(float)
        order = np.argsort(-scores)
        s_sorted, c_sorted = scores[order], correct[order]
        cum_correct = np.cumsum(c_sorted)
        cum_n = np.arange(1, len(c_sorted) + 1)
        prec = cum_correct / cum_n
        ok = np.where(prec >= target_precision)[0]
        if ok.size == 0:
            thresholds[c] = 1.01
        else:
            # lowest score among the largest accepted prefix that still meets precision
            k = ok.max()
            thresholds[c] = max(float(s_sorted[k]), min_threshold)
    return thresholds


def decide_with_abstain(prob_row, classes, thresholds: dict, margin: float = 0.10):
    """The deployed decision: predict the top class, or ABSTAIN (None) when its calibrated
    probability is below that class's tuned threshold, or the top-2 margin is thin."""
    import numpy as np
    row = np.asarray(prob_row, dtype=float)
    order = np.argsort(-row)
    top = int(order[0])
    top_c = classes[top]
    top_p = float(row[top])
    second_p = float(row[order[1]]) if len(order) > 1 else 0.0
    if top_p < thresholds.get(top_c, 1.01):
        return None
    if (top_p - second_p) < margin:
        return None
    return top_c


def precision_coverage_report(probs, y_true, classes, thresholds: dict,
                              margin: float = 0.10) -> dict:
    """Per-field precision + coverage UNDER THE DEPLOYED ABSTAIN RULE (fixes F45: the
    reported metric now describes the model+rule that actually ships, not the raw split).
    Coverage = share of samples given any label; precision is over non-abstained rows."""
    from collections import defaultdict
    P = list(probs)
    preds = [decide_with_abstain(row, classes, thresholds, margin) for row in P]
    tp = defaultdict(int)
    fp = defaultdict(int)
    support = defaultdict(int)
    for pred, y in zip(preds, y_true):
        support[y] += 1
        if pred is None:
            continue
        if pred == y:
            tp[pred] += 1
        else:
            fp[pred] += 1
    per_field = {}
    for c in classes:
        assigned = tp[c] + fp[c]
        per_field[c] = {
            "precision": round(tp[c] / assigned, 4) if assigned else None,
            "assigned": assigned,
            "support": support.get(c, 0),
        }
    n = len(y_true)
    labeled = sum(1 for p in preds if p is not None)
    correct = sum(1 for p, y in zip(preds, y_true) if p is not None and p == y)
    return {
        "coverage": round(labeled / n, 4) if n else 0.0,
        "precision_on_labeled": round(correct / labeled, 4) if labeled else None,
        "abstained": n - labeled,
        "per_field": per_field,
    }
