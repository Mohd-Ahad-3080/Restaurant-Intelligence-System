"""Model variants: every variant fully reported (metrics, per-class precision/recall, confusion matrix,
permutation feature importance) and compared in one table.

Target (all variants): src.target.TARGET_DEFINITION. Honest variants never see votes, aggregate_rating,
rating_text, rating_color or is_rated (checked by assert_no_leakage). The leaky row breaks this rule on
purpose, as an illustration only; it is never saved or used.

Controlled comparison: every honest variant uses the main model's algorithm and hyper-parameters (chosen by
5-fold CV on the main training set). Only the rows (all countries / India) and the feature set (with /
without location) change. Each variant gets its own stratified 80/20 split (random_state 42) and a 5-fold
CV macro-F1 on its own training set; the test set is used once.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline

from src import config
from src.eda import C, _save, _style
from src.features import CATEGORICAL, NUMERIC, assert_no_leakage
from src.model import CV_FOLDS, LEAKY_FEATURES, LOCATION_FEATURES, RANDOM_STATE, TEST_SIZE, _metrics, _preprocessor
from src.target import LABELS

PRED_DIR = config.PREDICTIONS_DIR
MAIN, NO_LOC = "Main (all countries, all features)", "No location (all countries)"
INDIA_LOC, INDIA_NO_LOC = "India, with city/locality", "India, without city/locality"
BASELINE, LEAKY = "Baseline (majority class)", "Leaky: + votes and rating (INVALID)"
HONEST = {MAIN: (False, False), NO_LOC: (True, False), INDIA_LOC: (False, True), INDIA_NO_LOC: (True, True)}


def select_features(columns, drop_location: bool, india_only: bool) -> list[str]:
    """Feature columns for a variant. India-only also drops `country` (constant there)."""
    drop = set(LOCATION_FEATURES) if drop_location else set()
    if india_only:
        drop.add("country")
    return [c for c in columns if c not in drop]


def _pipeline(model_step, columns) -> Pipeline:
    num = [c for c in NUMERIC + LEAKY_FEATURES if c in columns]
    cat = [c for c in CATEGORICAL if c in columns]
    binary = [c for c in columns if c.startswith("cuisine_")]
    scale = isinstance(model_step, LogisticRegression)
    return Pipeline([("prep", _preprocessor(scale, num, cat, binary)), ("model", clone(model_step))])


def _evaluate(name: str, est: Pipeline, X: pd.DataFrame, y: pd.Series, valid: bool, removed: str) -> dict:
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE)
    cv = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    cv_f1 = cross_val_score(est, X_tr, y_tr, cv=cv, scoring="f1_macro", n_jobs=-1).mean()
    est.fit(X_tr, y_tr)
    pred = est.predict(X_te)
    proba = pd.DataFrame(est.predict_proba(X_te), columns=est.classes_)[LABELS].values
    m = _metrics(y_te, pred, proba, LABELS)
    p, r, f, s = precision_recall_fscore_support(y_te, pred, labels=LABELS, zero_division=0)
    per_class = pd.DataFrame({"variant": name, "class": LABELS, "precision": p, "recall": r, "f1": f, "support": s})
    cm = confusion_matrix(y_te, pred, labels=LABELS)
    conf = pd.DataFrame([{"variant": name, "actual": a, "predicted": b, "count": int(cm[i, j])}
                         for i, a in enumerate(LABELS) for j, b in enumerate(LABELS)])
    if name == BASELINE:  # a constant prediction has no feature importance
        imp = pd.DataFrame({"feature": X.columns, "importance_mean": 0.0, "importance_std": 0.0})
    else:
        pi = permutation_importance(est, X_te, y_te, scoring="f1_macro", n_repeats=10,
                                    random_state=RANDOM_STATE, n_jobs=-1)
        imp = (pd.DataFrame({"feature": X.columns, "importance_mean": pi.importances_mean,
                             "importance_std": pi.importances_std})
               .sort_values("importance_mean", ascending=False))
    imp = imp.reset_index(drop=True).assign(variant=name, rank=lambda d: d.index + 1)
    top = "" if name == BASELINE else "; ".join(f"{t.feature} ({t.importance_mean:.3f})"
                                                for t in imp.head(3).itertuples())
    row = {"variant": name, "valid": "yes" if valid else "NO (leakage)", "rows": len(y), "n_train": len(y_tr),
           "n_test": len(y_te), "n_features": X.shape[1], "features_removed": removed, "cv_f1_macro": cv_f1,
           **{f"test_{k}": v for k, v in m.items()},
           "majority_baseline_accuracy": y_te.value_counts(normalize=True).max(),
           "top_features": top, "features_used": "; ".join(X.columns)}
    return {"row": row, "per_class": per_class, "confusion": conf, "importance": imp}


def run_variants(res: dict, clean: pd.DataFrame, verbose: bool = True) -> dict:
    X, y = res["X"], res["y"]
    step = res["best"].named_steps["model"]
    india = X["country"].eq("India")
    out = []
    for name, (drop_loc, india_only) in HONEST.items():
        cols = select_features(X.columns, drop_loc, india_only)
        Xv, yv = (X.loc[india, cols], y[india]) if india_only else (X[cols], y)
        assert_no_leakage(Xv.columns)
        removed = ", ".join(c for c in X.columns if c not in cols) or "none"
        out.append(_evaluate(name, _pipeline(step, cols), Xv, yv, True, removed))
    out.append(_evaluate(BASELINE, _pipeline(DummyClassifier(strategy="most_frequent"), list(X.columns)),
                         X, y, True, "n/a (always predicts the most common class)"))
    leak = X.join(clean.set_index("restaurant_id")[LEAKY_FEATURES].astype(float))
    out.append(_evaluate(LEAKY, _pipeline(step, list(leak.columns)), leak, y, False,
                         "none; votes and aggregate_rating ADDED"))

    tables = {"summary": pd.DataFrame([o["row"] for o in out]),
              "per_class": pd.concat([o["per_class"] for o in out], ignore_index=True),
              "confusion": pd.concat([o["confusion"] for o in out], ignore_index=True),
              "importance": pd.concat([o["importance"] for o in out], ignore_index=True)}
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    for key, df in tables.items():
        df.to_csv(PRED_DIR / f"model_variants{'' if key == 'summary' else '_' + key}.csv", index=False)
    if verbose:
        for r in tables["summary"].itertuples(index=False):
            print(f"      variant: {r.variant:<38} rows {r.rows:>5,} | acc {r.test_accuracy:.3f}, "
                  f"macro-F1 {r.test_f1_macro:.3f}, AUC {r.test_roc_auc_ovr_macro:.3f}")
    tables["figures"] = [plot_variants(tables["summary"]), plot_no_location(tables)]
    return tables


def plot_variants(summary: pd.DataFrame) -> Path:
    _style()
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    x, w = np.arange(len(summary)), 0.38
    for i, (col, lab, colr) in enumerate([("test_accuracy", "Accuracy", C["highlight"]),
                                          ("test_f1_macro", "Macro F1", C["accent"])]):
        bars = ax.bar(x + (i - 0.5) * w, summary[col], w, label=lab, color=colr, edgecolor="white")
        for b, v, ok in zip(bars, summary[col], summary["valid"].eq("yes")):
            if not ok:
                b.set_hatch("///")
            ax.text(b.get_x() + b.get_width() / 2, v + 0.01, f"{v:.2f}", ha="center", fontsize=7, color=C["text2"])
    ax.set_xticks(x, [v.replace(", ", ",\n").replace(" (", "\n(").replace(": ", ":\n") for v in summary["variant"]],
                  fontsize=8)
    ax.set_ylim(0, 1.08)
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("Score on each variant's test set")
    ax.set_title("Model variants (hatched = leaky, invalid)")
    ax.legend(ncol=2, loc="upper left")
    return _save(fig, "fig16_model_variants")


def plot_no_location(tables: dict) -> Path:
    _style()
    conf = tables["confusion"].query("variant == @NO_LOC")
    cm = conf.pivot(index="actual", columns="predicted", values="count").loc[LABELS, LABELS].values
    imp = tables["importance"].query("variant == @NO_LOC").head(12)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.8), gridspec_kw={"width_ratios": [1, 1.5]})
    pct = cm / cm.sum(axis=1, keepdims=True)
    a1.imshow(pct, cmap=matplotlib.colors.LinearSegmentedColormap.from_list("b", ["#FFFFFF", C["highlight"]]),
              vmin=0, vmax=1)
    for i in range(3):
        for j in range(3):
            a1.text(j, i, f"{cm[i, j]:,}\n({100 * pct[i, j]:.0f}%)", ha="center", va="center", fontsize=9,
                    color="white" if pct[i, j] > 0.5 else C["text"])
    a1.set_xticks(range(3), LABELS)
    a1.set_yticks(range(3), LABELS)
    a1.set_xlabel("Predicted class")
    a1.set_ylabel("Actual class")
    a1.grid(False)
    a1.set_title("Confusion matrix (test set)")
    yy = np.arange(len(imp))
    a2.barh(yy, imp["importance_mean"], xerr=imp["importance_std"], color=C["accent"], height=0.65,
            error_kw={"ecolor": C["text2"], "elinewidth": 0.8, "capsize": 2})
    a2.set_yticks(yy, imp["feature"])
    a2.invert_yaxis()
    a2.grid(axis="y", visible=False)
    a2.set_xlabel("Drop in macro-F1 when shuffled (test set)")
    a2.set_title("Top 12 features (permutation importance)")
    fig.suptitle(f"{NO_LOC}: no country, city, coordinates or locality size", fontsize=11)
    return _save(fig, "fig17_no_location_model")


def variants_markdown(tables: dict) -> list[str]:
    s = tables["summary"].set_index("variant")
    lines = ["", "## Model variants (one comparison table)", "",
             "Same algorithm and hyper-parameters as the main model; only rows and features change. "
             "Each variant has its own stratified 80/20 split (random_state 42).", "",
             "| variant | valid | rows | features | CV macro-F1 (train) | test accuracy | test macro-F1 | "
             "test ROC-AUC | majority baseline acc. | top 3 features (drop in macro-F1) |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for v, r in s.iterrows():
        lines.append(f"| {v} | {r.valid} | {r.rows:,} | {r.n_features} | {r.cv_f1_macro:.3f} | "
                     f"{r.test_accuracy:.3f} | {r.test_f1_macro:.3f} | {r.test_roc_auc_ovr_macro:.3f} | "
                     f"{r.majority_baseline_accuracy:.3f} | {r.top_features or '-'} |")
    lines += ["", "Features removed per variant:", ""]
    lines += [f"- **{v}**: {r.features_removed}" for v, r in s.iterrows()]
    f1 = s["test_f1_macro"]
    lines += ["", f"Removing location lowers macro-F1 from {f1[MAIN]:.3f} to {f1[NO_LOC]:.3f} (all countries) and "
              f"from {f1[INDIA_LOC]:.3f} to {f1[INDIA_NO_LOC]:.3f} (India only). The leaky variant reaches "
              f"{s.loc[LEAKY, 'test_accuracy']:.1%} accuracy only because votes are both input and target; it is "
              "not a valid result.", "", "### Per-class precision and recall (test sets)", "",
              "| variant | class | precision | recall | F1 | support |", "|---|---|---|---|---|---|"]
    for r in tables["per_class"].itertuples(index=False):
        lines.append(f"| {r.variant} | {r[1]} | {r.precision:.3f} | {r.recall:.3f} | {r.f1:.3f} | {r.support:,} |")
    lines += ["", "### Confusion matrices (test sets, rows = actual, columns = predicted)", ""]
    for v in s.index:
        cm = tables["confusion"].query("variant == @v").pivot(index="actual", columns="predicted",
                                                               values="count").loc[LABELS, LABELS]
        lines += [f"**{v}**", "", "| actual \\ predicted | " + " | ".join(LABELS) + " |", "|---|---|---|---|"]
        lines += [f"| {a} | " + " | ".join(f"{cm.loc[a, b]:,}" for b in LABELS) + " |" for a in LABELS]
        lines.append("")
    return lines
