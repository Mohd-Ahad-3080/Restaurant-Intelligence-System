"""Medium class: honest attempts to improve it, evidence for why it stays hard, and a separate
High-vs-Low model.

All tuning uses the TRAINING set only (5-fold stratified CV / out-of-fold predictions). Each approach is
then evaluated ONCE on the same untouched test set as the main model (80/20, random_state 42). The saved
main model is NOT replaced; this module only reports.

Approaches (same algorithm and hyper-parameters as the main model):
1. Before: the main model, predicted class = highest probability.
2. Class weights: Medium rows get weight w, the others 1. The classes are already balanced (thirds), so
   'balanced' weights would be about 1 and change nothing; w is tuned by CV macro-F1 on the training set.
3. Threshold tuning: a bias b is added to the Medium probability before taking the highest class. b is tuned
   on out-of-fold training predictions, then applied once to the test probabilities.
4. Ordinal (Frank and Hall, 2001, "A simple approach to ordinal classification"): two binary models estimate
   P(class > Low) and P(class > Medium); P(Low) = 1 - P1, P(Medium) = P1 - P2, P(High) = P2
   (negative values clipped to 0, rows renormalised).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from sklearn.base import clone
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support,
                             roc_auc_score)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split

from src import config
from src.eda import C, _save, _style
from src.features import assert_no_leakage
from src.model import CV_FOLDS, RANDOM_STATE, TEST_SIZE, _metrics
from src.target import LABELS

PRED_DIR = config.PREDICTIONS_DIR
MEDIUM_WEIGHTS = [1.0, 1.25, 1.5, 2.0, 3.0]
MEDIUM_BIASES = np.round(np.arange(-0.10, 0.3001, 0.01), 2)
BEFORE, WEIGHTS, THRESHOLD, ORDINAL = ("Before: main model (highest probability)", "Class weights (Medium up-weighted)",
                                       "Threshold tuning (Medium bias)", "Ordinal (Frank and Hall)")
NEAR_VOTES = 10  # "close to a cut-off" = within 10 votes of it (stated wherever the number is used)
DIST_BINS = [0, 0.05, 0.10, 1 / 6, 1 / 3 + 1e-9]
DIST_LABELS = ["0-5", "5-10", "10-16.7", "16.7-33.3"]  # percentile points to the nearest cut-off


# ------------------------------------------------------------------ pure helpers (unit-tested)
def apply_medium_bias(proba, bias: float) -> np.ndarray:
    """proba columns in LABELS order (Low, Medium, High). Adds `bias` to Medium, returns predicted labels."""
    p = np.asarray(proba, dtype=float).copy()
    p[:, 1] += bias
    return np.array(LABELS)[p.argmax(axis=1)]


def ordinal_proba(p_above_low, p_above_medium) -> np.ndarray:
    """Frank and Hall: combine P(class > Low) and P(class > Medium) into Low/Medium/High probabilities."""
    p1, p2 = np.asarray(p_above_low, float), np.asarray(p_above_medium, float)
    p = np.column_stack([1 - p1, p1 - p2, p2]).clip(min=0)
    return p / p.sum(axis=1, keepdims=True)


def class_cutoffs(rated: pd.DataFrame) -> pd.DataFrame:
    """Per country: vote range of each class and the cut-offs (midpoint between neighbouring classes)."""
    rows = []
    for country, d in rated.groupby("country"):
        g = d.groupby("popularity_class")["votes"]
        mn, mx, med = g.min(), g.max(), g.median()
        if not set(LABELS) <= set(mn.index):
            continue
        rows.append({"country": country, "rated": len(d),
                     "low_votes": f"{mn['Low']:.0f}-{mx['Low']:.0f}",
                     "medium_votes": f"{mn['Medium']:.0f}-{mx['Medium']:.0f}",
                     "high_votes": f"{mn['High']:.0f}-{mx['High']:.0f}",
                     "cut_low_medium": (mx["Low"] + mn["Medium"]) / 2,
                     "cut_medium_high": (mx["Medium"] + mn["High"]) / 2,
                     "medium_band_width_votes": mx["Medium"] - mn["Medium"],
                     "median_votes_low": med["Low"], "median_votes_medium": med["Medium"],
                     "median_votes_high": med["High"]})
    return pd.DataFrame(rows).sort_values("rated", ascending=False).reset_index(drop=True)


def distance_to_cutoffs(rated: pd.DataFrame, cuts: pd.DataFrame) -> pd.DataFrame:
    """Distance of each rated restaurant to its country's nearest class cut-off, in votes and in
    percentile points (the target is cut at the 1/3 and 2/3 within-country percentiles)."""
    d = rated.merge(cuts[["country", "cut_low_medium", "cut_medium_high"]], on="country", how="inner")
    d["votes_to_cutoff"] = np.minimum((d["votes"] - d["cut_low_medium"]).abs(),
                                      (d["votes"] - d["cut_medium_high"]).abs())
    d["pct_to_cutoff"] = np.minimum((d["votes_pct_in_country"] - 1 / 3).abs(),
                                    (d["votes_pct_in_country"] - 2 / 3).abs())
    d["distance_bin"] = pd.cut(d["pct_to_cutoff"], DIST_BINS, labels=DIST_LABELS, include_lowest=True)
    return d


# ------------------------------------------------------------------ training helpers
def _cv():
    return StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)


def _proba(est, X) -> np.ndarray:
    return pd.DataFrame(est.predict_proba(X), columns=est.classes_)[LABELS].values


def _weighted(base, w: float):
    def fit_predict(X_tr, y_tr, X_ev):
        if w == 1.0:
            return _proba(clone(base).fit(X_tr, y_tr), X_ev)
        sw = np.where(y_tr.eq("Medium"), w, 1.0)
        return _proba(clone(base).fit(X_tr, y_tr, model__sample_weight=sw), X_ev)
    return fit_predict


def _ordinal(base):
    def fit_predict(X_tr, y_tr, X_ev):
        rank = y_tr.map({c: i for i, c in enumerate(LABELS)})
        ps = [clone(base).fit(X_tr, (rank > k).astype(int)).predict_proba(X_ev)[:, 1] for k in (0, 1)]
        return ordinal_proba(*ps)
    return fit_predict


def _oof(fit_predict, X, y) -> np.ndarray:
    """Out-of-fold probabilities on the training set (each row predicted by a model that did not see it)."""
    folds = list(_cv().split(X, y))
    parts = Parallel(n_jobs=-1)(delayed(fit_predict)(X.iloc[tr], y.iloc[tr], X.iloc[va]) for tr, va in folds)
    out = np.zeros((len(y), len(LABELS)))
    for (_, va), p in zip(folds, parts):
        out[va] = p
    return out


def _f1(y, pred) -> float:
    return f1_score(y, pred, average="macro")


def _argmax(p) -> np.ndarray:
    return np.array(LABELS)[np.asarray(p).argmax(axis=1)]


# ------------------------------------------------------------------ 2a: improvement attempts
def improve_medium(res: dict) -> dict:
    base, X_tr, y_tr, X_te, y_te = res["best"], res["X_train"], res["y_train"], res["X_test"], res["y_test"]

    oof_w = {w: _oof(_weighted(base, w), X_tr, y_tr) for w in MEDIUM_WEIGHTS}
    cv_w = {w: _f1(y_tr, _argmax(p)) for w, p in oof_w.items()}
    best_w = max(MEDIUM_WEIGHTS, key=lambda w: (cv_w[w], -w))  # ties -> smaller weight
    cv_b = {b: _f1(y_tr, apply_medium_bias(oof_w[1.0], b)) for b in MEDIUM_BIASES}
    best_b = max(MEDIUM_BIASES, key=lambda b: (cv_b[b], -abs(b)))  # ties -> smaller change
    oof_ord = _oof(_ordinal(base), X_tr, y_tr)

    # one final fit per approach on the full training set, one evaluation on the test set
    p_before = _proba(base, X_te)  # the saved main model, already fitted on the training set
    p_w = _weighted(base, best_w)(X_tr, y_tr, X_te)
    p_ord = _ordinal(base)(X_tr, y_tr, X_te)
    runs = [
        (BEFORE, "-", cv_w[1.0], p_before, _argmax(p_before)),
        (WEIGHTS, f"Medium weight = {best_w:g} (grid {MEDIUM_WEIGHTS})", cv_w[best_w], p_w, _argmax(p_w)),
        (THRESHOLD, f"Medium bias = {best_b:+.2f} (grid {MEDIUM_BIASES[0]:+.2f} to {MEDIUM_BIASES[-1]:+.2f})",
         cv_b[best_b], p_before, apply_medium_bias(p_before, best_b)),
        (ORDINAL, "-", _f1(y_tr, _argmax(oof_ord)), p_ord, _argmax(p_ord)),
    ]
    rows, per_class = [], []
    for name, tuned, cv_f1, proba, pred in runs:
        m = _metrics(y_te, pred, proba, LABELS)
        rows.append({"method": name, "tuned_on_training_set": tuned, "cv_f1_macro_train": cv_f1,
                     **{f"test_{k}": v for k, v in m.items()}})
        p, r, f, s = precision_recall_fscore_support(y_te, pred, labels=LABELS, zero_division=0)
        per_class.append(pd.DataFrame({"method": name, "class": LABELS, "precision": p, "recall": r, "f1": f,
                                       "support": s}))
    tuning = pd.concat([pd.DataFrame({"parameter": "medium_weight", "value": list(cv_w), "cv_f1_macro_train":
                                      list(cv_w.values())}),
                        pd.DataFrame({"parameter": "medium_bias", "value": list(cv_b), "cv_f1_macro_train":
                                      list(cv_b.values())})], ignore_index=True)
    return {"methods": pd.DataFrame(rows), "per_class": pd.concat(per_class, ignore_index=True), "tuning": tuning}


# ------------------------------------------------------------------ 2b: evidence
def medium_evidence(res: dict, clean: pd.DataFrame) -> dict:
    rated = clean[clean["is_rated"] == 1].dropna(subset=["popularity_class"])
    cuts = class_cutoffs(rated)
    dist = distance_to_cutoffs(rated, cuts)
    by_class = (dist.groupby("popularity_class")
                .agg(restaurants=("votes", "size"), median_votes_to_cutoff=("votes_to_cutoff", "median"),
                     share_within_near_votes=("votes_to_cutoff", lambda s: (s <= NEAR_VOTES).mean()),
                     median_pct_points_to_cutoff=("pct_to_cutoff", lambda s: 100 * s.median()),
                     max_pct_points_to_cutoff=("pct_to_cutoff", lambda s: 100 * s.max()))
                .reindex(LABELS).rename_axis("class").reset_index())
    # main model's test predictions: is accuracy lower close to a cut-off?
    test = pd.DataFrame({"restaurant_id": res["X_test"].index, "predicted": res["best"].predict(res["X_test"])})
    t = dist.merge(test, on="restaurant_id")
    t["correct"] = (t["predicted"] == t["popularity_class"]).astype(int)
    by_dist = (t.groupby("distance_bin", observed=False)
               .agg(test_restaurants=("correct", "size"), test_accuracy=("correct", "mean"),
                    medium_share=("popularity_class", lambda s: (s == "Medium").mean()))
               .rename_axis("pct_points_to_nearest_cutoff").reset_index())
    return {"cutoffs": cuts, "by_class": by_class, "by_distance": by_dist, "distances": dist}


# ------------------------------------------------------------------ 2c: High vs Low (separate question)
def high_vs_low(res: dict) -> dict:
    keep = res["y"].isin(["Low", "High"])
    X, y = res["X"][keep], res["y"][keep]
    assert_no_leakage(X.columns)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE)
    est = clone(res["best"])
    cv_f1 = cross_val_score(est, X_tr, y_tr, cv=_cv(), scoring="f1_macro", n_jobs=-1).mean()
    est.fit(X_tr, y_tr)
    pred = est.predict(X_te)
    p_high = est.predict_proba(X_te)[:, list(est.classes_).index("High")]
    p, r, f, s = precision_recall_fscore_support(y_te, pred, labels=["Low", "High"], zero_division=0)
    summary = {"model": "High vs Low (2 classes, Medium excluded) - separate question", "rows": len(y),
               "n_train": len(y_tr), "n_test": len(y_te), "cv_f1_macro_train": cv_f1,
               "test_accuracy": accuracy_score(y_te, pred), "test_f1_macro": f1_score(y_te, pred, average="macro"),
               "test_roc_auc": roc_auc_score(y_te.eq("High"), p_high),
               "majority_baseline_accuracy": y_te.value_counts(normalize=True).max()}
    per_class = pd.DataFrame({"class": ["Low", "High"], "precision": p, "recall": r, "f1": f, "support": s})
    cm = confusion_matrix(y_te, pred, labels=["Low", "High"])
    conf = pd.DataFrame(cm, index=pd.Index(["Low", "High"], name="actual"), columns=["Low", "High"])
    return {"summary": pd.DataFrame([summary]), "per_class": per_class, "confusion": conf}


# ------------------------------------------------------------------ figures
def plot_methods(per_class: pd.DataFrame) -> Path:
    _style()
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
    methods = per_class["method"].unique()
    colours = [C["highlight"], C["accent"], C["light1"], C["text2"]]
    x, w = np.arange(len(LABELS)), 0.8 / len(methods)
    for ax, metric in zip(axes, ["precision", "recall"]):
        for i, (mth, col) in enumerate(zip(methods, colours)):
            v = per_class[per_class["method"] == mth].set_index("class").loc[LABELS, metric]
            bars = ax.bar(x + (i - (len(methods) - 1) / 2) * w, v, w, label=mth, color=col, edgecolor="white")
            for b, val in zip(bars, v):
                ax.text(b.get_x() + b.get_width() / 2, val + 0.01, f"{val:.2f}", ha="center", fontsize=6.5,
                        color=C["text2"])
        ax.set_xticks(x, LABELS)
        ax.set_ylim(0, 1)
        ax.grid(axis="x", visible=False)
        ax.set_title(f"{metric.capitalize()} by class (test set)")
    axes[0].legend(fontsize=7.5, loc="upper left")
    fig.suptitle("Medium class: before and after honest tuning (tuned on training set only)", fontsize=11)
    return _save(fig, "fig18_medium_class_methods")


def plot_boundaries(ev: dict) -> Path:
    _style()
    d = ev["distances"][ev["distances"]["country"] == "India"]
    cut = ev["cutoffs"].set_index("country").loc["India"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.6), gridspec_kw={"width_ratios": [1.5, 1]})
    bins = np.linspace(np.log10(d["votes"].clip(lower=1)).min(), np.log10(d["votes"].clip(lower=1)).max(), 50)
    for cls, col in zip(LABELS, [C["light1"], C["accent"], C["highlight"]]):
        a1.hist(np.log10(d.loc[d["popularity_class"] == cls, "votes"].clip(lower=1)), bins=bins, color=col,
                label=cls, alpha=0.9)
    for c in (cut["cut_low_medium"], cut["cut_medium_high"]):
        a1.axvline(np.log10(c), color=C["text"], ls="--", lw=1)
        a1.text(np.log10(c), a1.get_ylim()[1] * 0.95, f" cut-off ~{c:.0f} votes", fontsize=8, color=C["text"])
    ticks = [1, 3, 10, 30, 100, 300, 1000, 3000, 10000]
    a1.set_xticks(np.log10(ticks), [f"{t:,}" for t in ticks])
    a1.set_xlabel("Votes (log scale)")
    a1.set_ylabel("Rated restaurants")
    a1.grid(axis="x", visible=False)
    a1.legend()
    a1.set_title(f"India: Medium is a narrow band of votes ({cut['medium_votes']})")
    b = ev["by_distance"]
    bars = a2.bar(b["pct_points_to_nearest_cutoff"].astype(str), b["test_accuracy"], color=C["accent"])
    for bar, acc, n in zip(bars, b["test_accuracy"], b["test_restaurants"]):
        a2.text(bar.get_x() + bar.get_width() / 2, acc + 0.01, f"{acc:.2f}\n(n={n:,})", ha="center", fontsize=8,
                color=C["text2"])
    a2.set_ylim(0, 1)
    a2.grid(axis="x", visible=False)
    a2.set_xlabel("Percentile points to the nearest class cut-off")
    a2.set_ylabel("Main model accuracy (test set)")
    a2.set_title("Accuracy is lowest close to a cut-off")
    return _save(fig, "fig19_medium_boundaries")


# ------------------------------------------------------------------ orchestration
def run_medium(res: dict, clean: pd.DataFrame, verbose: bool = True) -> dict:
    out = {"improve": improve_medium(res), "evidence": medium_evidence(res, clean), "binary": high_vs_low(res)}
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    out["improve"]["methods"].to_csv(PRED_DIR / "medium_class_methods.csv", index=False)
    out["improve"]["per_class"].to_csv(PRED_DIR / "medium_class_per_class.csv", index=False)
    out["improve"]["tuning"].to_csv(PRED_DIR / "medium_class_tuning.csv", index=False)
    out["evidence"]["cutoffs"].to_csv(PRED_DIR / "medium_class_cutoffs.csv", index=False)
    out["evidence"]["by_class"].to_csv(PRED_DIR / "medium_class_distance_by_class.csv", index=False)
    out["evidence"]["by_distance"].to_csv(PRED_DIR / "medium_class_accuracy_by_distance.csv", index=False)
    out["binary"]["summary"].to_csv(PRED_DIR / "high_vs_low_model.csv", index=False)
    out["binary"]["per_class"].to_csv(PRED_DIR / "high_vs_low_per_class.csv", index=False)
    out["binary"]["confusion"].to_csv(PRED_DIR / "high_vs_low_confusion.csv")
    out["figures"] = [plot_methods(out["improve"]["per_class"]), plot_boundaries(out["evidence"])]
    if verbose:
        pc = out["improve"]["per_class"].set_index(["method", "class"])
        for r in out["improve"]["methods"].itertuples(index=False):
            med = pc.loc[(r.method, "Medium")]
            print(f"      medium: {r.method:<41} acc {r.test_accuracy:.3f}, macro-F1 {r.test_f1_macro:.3f} | "
                  f"Medium P {med.precision:.3f} R {med.recall:.3f}")
        b = out["binary"]["summary"].iloc[0]
        print(f"      separate question, High vs Low (Medium excluded): acc {b.test_accuracy:.3f}, "
              f"macro-F1 {b.test_f1_macro:.3f}, AUC {b.test_roc_auc:.3f} (baseline {b.majority_baseline_accuracy:.3f})")
    return out


def medium_markdown(out: dict) -> list[str]:
    m = out["improve"]["methods"]
    pc = out["improve"]["per_class"]
    lines = ["", "## Medium class: honest improvement attempts", "",
             "Tuned on the training set only (5-fold CV / out-of-fold predictions); each approach evaluated once on "
             "the same test set. The saved main model is not replaced.", "",
             "| method | tuned on training set | CV macro-F1 (train) | test accuracy | test macro-F1 | test ROC-AUC |",
             "|---|---|---|---|---|---|"]
    for r in m.itertuples(index=False):
        lines.append(f"| {r.method} | {r.tuned_on_training_set} | {r.cv_f1_macro_train:.3f} | {r.test_accuracy:.3f} | "
                     f"{r.test_f1_macro:.3f} | {r.test_roc_auc_ovr_macro:.3f} |")
    lines += ["", "Note: the CV score of threshold tuning is slightly optimistic, because the bias was chosen on the "
              "same out-of-fold predictions; its test score is not affected.", "",
              "Per-class precision and recall, before and after (test set):", "",
              "| method | class | precision | recall | F1 | support |", "|---|---|---|---|---|---|"]
    for r in pc.itertuples(index=False):
        lines.append(f"| {r.method} | {r[1]} | {r.precision:.3f} | {r.recall:.3f} | {r.f1:.3f} | {r.support:,} |")
    med = pc[pc["class"] == "Medium"].set_index("method")
    mi = m.set_index("method")
    cv_pick = mi["cv_f1_macro_train"].idxmax()  # selection uses the training CV score, never the test set
    test_top = med["f1"].idxmax()
    lines += ["", f"Medium F1 before: {med.loc[BEFORE, 'f1']:.3f} (recall {med.loc[BEFORE, 'recall']:.3f}). "
              f"Chosen by training CV macro-F1: {cv_pick} (CV {mi.loc[cv_pick, 'cv_f1_macro_train']:.3f} vs "
              f"{mi.loc[BEFORE, 'cv_f1_macro_train']:.3f} before), test Medium F1 {med.loc[cv_pick, 'f1']:.3f}. "
              f"Highest test Medium F1: {test_top} ({med.loc[test_top, 'f1']:.3f}); "
              + ("this is also the CV choice." if test_top == cv_pick else
                 "this was not the CV choice, so it is reported but not selected (choosing by test score would "
                 "overfit the test set).")]

    ev = out["evidence"]
    lines += ["", "## Why Medium is hard: it borders both other classes", "",
              "The target cuts each country's rated restaurants at the 1/3 and 2/3 percentiles of votes. Medium is "
              "the middle third, so every Medium restaurant is at most 16.7 percentile points from a cut-off, while "
              "Low and High restaurants can be up to 33.3 points away.", "",
              "Vote ranges per class and cut-offs (cut-off = midpoint between neighbouring classes):", "",
              "| country | rated | Low votes | Medium votes | High votes | cut-off Low/Medium | cut-off Medium/High |",
              "|---|---|---|---|---|---|---|"]
    for r in ev["cutoffs"].itertuples(index=False):
        lines.append(f"| {r.country} | {r.rated:,} | {r.low_votes} | {r.medium_votes} | {r.high_votes} | "
                     f"{r.cut_low_medium:g} | {r.cut_medium_high:g} |")
    lines += ["", f"Distance to the nearest cut-off, by class (all rated restaurants; 'near' = within {NEAR_VOTES} "
              "votes):", "",
              "| class | restaurants | median votes to cut-off | share within "
              f"{NEAR_VOTES} votes | median percentile points | max percentile points |", "|---|---|---|---|---|---|"]
    for r in ev["by_class"].itertuples(index=False):
        lines.append(f"| {r[0]} | {r.restaurants:,} | {r.median_votes_to_cutoff:g} | {r.share_within_near_votes:.1%} | "
                     f"{r.median_pct_points_to_cutoff:.1f} | {r.max_pct_points_to_cutoff:.1f} |")
    lines += ["", "Main model accuracy on the test set by distance to the nearest cut-off:", "",
              "| percentile points to cut-off | test restaurants | accuracy | share that is Medium |", "|---|---|---|---|"]
    for r in ev["by_distance"].itertuples(index=False):
        lines.append(f"| {r[0]} | {r.test_restaurants:,} | {r.test_accuracy:.3f} | {r.medium_share:.1%} |")

    b, bpc = out["binary"]["summary"].iloc[0], out["binary"]["per_class"]
    cm = out["binary"]["confusion"]
    lines += ["", "## Separate question: High vs Low only (2 classes, Medium excluded)", "",
              "**This is not the 3-class result.** It answers a different, easier question: can the model tell a "
              "clearly popular restaurant (top third) from a clearly unpopular one (bottom third)? Medium restaurants "
              "are removed before the split, so its accuracy must not be compared with the 3-class accuracy.", "",
              f"- Rows: {b.rows:,} (train {b.n_train:,}, test {b.n_test:,}); same features and hyper-parameters as the "
              "main model; stratified 80/20, random_state 42.",
              f"- CV macro-F1 (train): {b.cv_f1_macro_train:.3f}. Test accuracy {b.test_accuracy:.3f}, macro-F1 "
              f"{b.test_f1_macro:.3f}, ROC-AUC {b.test_roc_auc:.3f}. Majority baseline accuracy "
              f"{b.majority_baseline_accuracy:.3f}.", "",
              "| class | precision | recall | F1 | support |", "|---|---|---|---|---|"]
    lines += [f"| {r[0]} | {r.precision:.3f} | {r.recall:.3f} | {r.f1:.3f} | {r.support:,} |"
              for r in bpc.itertuples(index=False)]
    lines += ["", "| actual \\ predicted | Low | High |", "|---|---|---|"]
    lines += [f"| {a} | {cm.loc[a, 'Low']:,} | {cm.loc[a, 'High']:,} |" for a in ["Low", "High"]]
    return lines
