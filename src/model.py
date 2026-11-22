"""Popularity prediction model (Low / Medium / High), target Option B.

Design:
- Rated restaurants only (unrated are excluded from training and prediction).
- 80/20 stratified split, random_state=42.
- 4 algorithms (Logistic Regression, Decision Tree, Random Forest, Gradient Boosting) + a
  majority-class baseline. Small hyper-parameter grids tuned with 5-fold stratified CV on the
  TRAINING set only. The best model is chosen by mean CV macro-F1 (not by test score), then
  evaluated once on the untouched test set.
- Metrics: accuracy, precision/recall/F1 (macro and weighted), ROC-AUC one-vs-rest, confusion
  matrix, permutation feature importance (on the test set).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, precision_score, recall_score,
                             roc_auc_score)
from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

from src import config
from src.eda import C, _save, _style
from src.features import CATEGORICAL, NUMERIC, assert_no_leakage, build_features, cuisine_columns
from src.target import EXCLUDED_FEATURES_NOTE, LABELS, TARGET_DEFINITION

RANDOM_STATE = 42
TEST_SIZE = 0.20
CV_FOLDS = 5
MODEL_PATH = config.MODELS_DIR / "popularity_model.joblib"
MODEL_META = config.MODELS_DIR / "popularity_model_meta.json"
PRED_DIR = config.PREDICTIONS_DIR  # Power BI page 4 data
RESULTS_MD = config.DOCS_DIR / "model_results.md"


def _preprocessor(scale: bool, numeric: list[str], categorical: list[str], binary: list[str]) -> ColumnTransformer:
    num_steps = [("impute", SimpleImputer(strategy="median"))] + ([("scale", StandardScaler())] if scale else [])
    return ColumnTransformer([
        ("num", Pipeline(num_steps), numeric),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical),
        ("bin", "passthrough", binary),
    ], verbose_feature_names_out=False)


def candidate_models(numeric, categorical, binary) -> dict[str, tuple[Pipeline, dict]]:
    def pipe(est, scale=False):
        return Pipeline([("prep", _preprocessor(scale, numeric, categorical, binary)), ("model", est)])

    return {
        "Baseline (majority class)": (pipe(DummyClassifier(strategy="most_frequent")), {}),
        "Logistic Regression": (pipe(LogisticRegression(max_iter=3000, random_state=RANDOM_STATE), scale=True),
                                {"model__C": [0.1, 1.0, 10.0]}),
        "Decision Tree": (pipe(DecisionTreeClassifier(random_state=RANDOM_STATE)),
                          {"model__max_depth": [4, 6, 8, 12], "model__min_samples_leaf": [5, 20]}),
        "Random Forest": (pipe(RandomForestClassifier(n_estimators=300, random_state=RANDOM_STATE, n_jobs=-1)),
                          {"model__max_depth": [8, 16, None], "model__min_samples_leaf": [1, 5]}),
        "Gradient Boosting": (pipe(GradientBoostingClassifier(random_state=RANDOM_STATE)),
                              {"model__n_estimators": [150, 300], "model__learning_rate": [0.05, 0.1],
                               "model__max_depth": [2, 3]}),
    }


def _metrics(y_true, y_pred, proba, classes) -> dict:
    # roc_auc_score needs labels in sorted order; reorder the probability columns to match
    order = sorted(range(len(classes)), key=lambda i: classes[i])
    auc = roc_auc_score(y_true, np.asarray(proba)[:, order], multi_class="ovr", average="macro",
                        labels=[classes[i] for i in order])
    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision_macro": precision_score(y_true, y_pred, average="macro", zero_division=0),
        "recall_macro": recall_score(y_true, y_pred, average="macro", zero_division=0),
        "f1_macro": f1_score(y_true, y_pred, average="macro", zero_division=0),
        "precision_weighted": precision_score(y_true, y_pred, average="weighted", zero_division=0),
        "recall_weighted": recall_score(y_true, y_pred, average="weighted", zero_division=0),
        "f1_weighted": f1_score(y_true, y_pred, average="weighted", zero_division=0),
        "roc_auc_ovr_macro": auc,
    }


def prepare_data(clean: pd.DataFrame, pairs: pd.DataFrame):
    X_all = build_features(clean, pairs)
    target = clean.set_index("restaurant_id")["popularity_class"]
    rated = target.notna()
    X, y = X_all.loc[rated], target.loc[rated].astype(str)
    assert_no_leakage(X.columns)
    return X, y


def train_and_evaluate(clean: pd.DataFrame, pairs: pd.DataFrame, verbose: bool = True) -> dict:
    say = print if verbose else (lambda *a, **k: None)
    X, y = prepare_data(clean, pairs)
    binary = cuisine_columns(X)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE)
    cv = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    classes = LABELS  # Low, Medium, High

    rows, fitted = [], {}
    for name, (pipe, grid) in candidate_models(NUMERIC, CATEGORICAL, binary).items():
        t0 = time.time()
        gs = GridSearchCV(pipe, grid or {}, cv=cv, scoring="f1_macro", n_jobs=-1, refit=True)
        gs.fit(X_tr, y_tr)
        best = gs.best_estimator_
        cv_std = float(gs.cv_results_["std_test_score"][gs.best_index_])
        proba = pd.DataFrame(best.predict_proba(X_te), columns=best.classes_)[classes].values
        pred = best.predict(X_te)
        m = _metrics(y_te, pred, proba, classes)
        rows.append({"model": name, "cv_f1_macro_mean": gs.best_score_, "cv_f1_macro_std": cv_std,
                     **{f"test_{k}": v for k, v in m.items()},
                     "best_params": json.dumps({k.replace("model__", ""): v for k, v in gs.best_params_.items()}),
                     "fit_seconds": round(time.time() - t0, 1)})
        fitted[name] = best
        say(f"      {name:<26} CV macro-F1 {gs.best_score_:.3f} | test acc {m['accuracy']:.3f}, "
            f"macro-F1 {m['f1_macro']:.3f}, AUC {m['roc_auc_ovr_macro']:.3f}")

    comp = pd.DataFrame(rows)
    real = comp[~comp["model"].str.startswith("Baseline")]
    best_name = real.sort_values("cv_f1_macro_mean", ascending=False).iloc[0]["model"]
    best = fitted[best_name]
    return {"X": X, "y": y, "X_train": X_tr, "X_test": X_te, "y_train": y_tr, "y_test": y_te,
            "comparison": comp, "fitted": fitted, "best_name": best_name, "best": best, "cv": cv,
            "classes": classes}


LOCATION_FEATURES = ["country", "city_group", "latitude", "longitude", "has_valid_coords", "log_locality_size"]
NCR_CITIES = ["New Delhi", "Gurgaon", "Noida", "Faridabad", "Ghaziabad"]


def robustness_checks(res: dict, clean: pd.DataFrame) -> pd.DataFrame:
    """Re-fit the best algorithm (same hyper-parameters) on two variants to separate the effect of
    uneven sampling by location from what restaurant attributes alone can predict."""
    from sklearn.base import clone

    X, y = res["X"], res["y"]
    city = clean.set_index("restaurant_id")["city"].reindex(X.index)
    country = X["country"]
    variants = {
        "Main model (all rated, all features)": (X, y),
        "Delhi NCR only (consistent sampling)": (X[(country == "India") & city.isin(NCR_CITIES)],
                                                 y[(country == "India") & city.isin(NCR_CITIES)]),
        "All rated, location features removed": (X.drop(columns=LOCATION_FEATURES), y),
    }
    rows = []
    for name, (Xv, yv) in variants.items():
        num = [c for c in NUMERIC if c in Xv.columns]
        cat = [c for c in CATEGORICAL if c in Xv.columns]
        pipe = Pipeline([("prep", _preprocessor(False, num, cat, cuisine_columns(Xv))),
                         ("model", clone(res["best"].named_steps["model"]))])
        X_tr, X_te, y_tr, y_te = train_test_split(Xv, yv, test_size=TEST_SIZE, stratify=yv,
                                                  random_state=RANDOM_STATE)
        pipe.fit(X_tr, y_tr)
        proba = pd.DataFrame(pipe.predict_proba(X_te), columns=pipe.classes_)[res["classes"]].values
        m = _metrics(y_te, pipe.predict(X_te), proba, res["classes"])
        rows.append({"variant": name, "rows": len(yv), "features": Xv.shape[1],
                     "test_accuracy": m["accuracy"], "test_f1_macro": m["f1_macro"],
                     "test_roc_auc_ovr_macro": m["roc_auc_ovr_macro"],
                     "majority_baseline_accuracy": y_te.value_counts(normalize=True).max()})
    return pd.DataFrame(rows)


LEAKY_FEATURES = ["votes", "aggregate_rating"]


def leakage_demo(res: dict, clean: pd.DataFrame) -> pd.DataFrame:
    """ILLUSTRATION ONLY - shows what data leakage would do; this model is never saved or used.

    Gradient Boosting with the same hyper-parameters as the tuned model, the same 80/20 split
    (random_state 42), the same 34 features PLUS votes and aggregate_rating. The target is built from
    votes, so these columns contain the answer; the leakage guard is deliberately not applied here.
    """
    from sklearn.base import clone

    gb = res["fitted"]["Gradient Boosting"]
    leak = clean.set_index("restaurant_id")[LEAKY_FEATURES].astype(float)
    X_tr, X_te = res["X_train"].join(leak), res["X_test"].join(leak)
    pipe = Pipeline([("prep", _preprocessor(False, NUMERIC + LEAKY_FEATURES, CATEGORICAL, cuisine_columns(X_tr))),
                     ("model", clone(gb.named_steps["model"]))])
    pipe.fit(X_tr, res["y_train"])
    proba = pd.DataFrame(pipe.predict_proba(X_te), columns=pipe.classes_)[res["classes"]].values
    m = _metrics(res["y_test"], pipe.predict(X_te), proba, res["classes"])
    honest = res["comparison"].set_index("model").loc["Gradient Boosting"]
    return pd.DataFrame([
        {"model": "Gradient Boosting (honest, 34 features)", "features": X_tr.shape[1] - len(LEAKY_FEATURES),
         "test_accuracy": honest["test_accuracy"], "test_f1_macro": honest["test_f1_macro"],
         "test_roc_auc_ovr_macro": honest["test_roc_auc_ovr_macro"]},
        {"model": "Leaky model (illustration only): + votes, aggregate_rating", "features": X_tr.shape[1],
         "test_accuracy": m["accuracy"], "test_f1_macro": m["f1_macro"],
         "test_roc_auc_ovr_macro": m["roc_auc_ovr_macro"]},
    ])


def sampling_by_zone(clean: pd.DataFrame) -> pd.DataFrame:
    r = clean[clean["is_rated"] == 1]
    zone = np.where(r["country"] != "India", "Outside India",
                    np.where(r["city"].isin(NCR_CITIES), "India: Delhi NCR", "India: other cities"))
    t = pd.crosstab(zone, r["popularity_class"], normalize="index")[LABELS] * 100
    t["rated_restaurants"] = pd.Series(zone).value_counts()
    t["median_votes"] = r.groupby(zone)["votes"].median()
    return t.rename_axis("zone").reset_index()


def feature_importance(res: dict, n_repeats: int = 10) -> pd.DataFrame:
    """Permutation importance of the best model on the TEST set (drop in macro-F1 when a feature is shuffled)."""
    pi = permutation_importance(res["best"], res["X_test"], res["y_test"], scoring="f1_macro",
                                n_repeats=n_repeats, random_state=RANDOM_STATE, n_jobs=-1)
    return (pd.DataFrame({"feature": res["X_test"].columns, "importance_mean": pi.importances_mean,
                          "importance_std": pi.importances_std})
            .sort_values("importance_mean", ascending=False).reset_index(drop=True))


def predictions_table(res: dict, clean: pd.DataFrame) -> pd.DataFrame:
    """Predictions for every rated restaurant. Test rows: best model fitted on train. Train rows:
    out-of-fold predictions (5-fold CV on train), so no row is predicted by a model that saw it."""
    best, classes = res["best"], res["classes"]
    oof = cross_val_predict(best, res["X_train"], res["y_train"], cv=res["cv"], method="predict_proba", n_jobs=-1)
    oof_classes = sorted(res["y_train"].unique())  # cross_val_predict column order = sorted labels
    p_tr = pd.DataFrame(oof, index=res["X_train"].index, columns=oof_classes)[classes]
    p_te = pd.DataFrame(best.predict_proba(res["X_test"]), index=res["X_test"].index, columns=best.classes_)[classes]
    probs = pd.concat([p_tr.assign(split="train (out-of-fold)"), p_te.assign(split="test")])
    probs["predicted_class"] = probs[classes].idxmax(axis=1)
    info = clean.set_index("restaurant_id")[["restaurant_name", "country", "city", "locality", "price_range",
                                             "has_online_delivery", "has_table_booking", "popularity_class"]]
    out = info.join(probs, how="inner").rename(columns={"popularity_class": "actual_class",
                                                        "Low": "prob_low", "Medium": "prob_medium",
                                                        "High": "prob_high"})
    out["correct"] = (out["actual_class"] == out["predicted_class"]).astype(int)
    out["model"] = res["best_name"]
    return out.reset_index()


# ------------------------------------------------------------------ figures
def plot_comparison(comp: pd.DataFrame) -> Path:
    _style()
    d = comp.set_index("model")[["test_accuracy", "test_f1_macro", "test_roc_auc_ovr_macro"]]
    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    x = np.arange(len(d))
    w = 0.26
    for i, (col, lab, colr) in enumerate([("test_accuracy", "Accuracy", C["highlight"]),
                                          ("test_f1_macro", "Macro F1", C["accent"]),
                                          ("test_roc_auc_ovr_macro", "ROC-AUC (OvR)", C["light1"])]):
        bars = ax.bar(x + (i - 1) * w, d[col], w, label=lab, color=colr, edgecolor="white", linewidth=1)
        for b, v in zip(bars, d[col]):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.01, f"{v:.2f}", ha="center", fontsize=7, color=C["text2"])
    ax.set_xticks(x, [m.replace(" (majority class)", "\n(majority class)") for m in d.index], fontsize=9)
    ax.set_ylim(0, 1)
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("Score on test set")
    ax.set_title("Model comparison on the held-out test set (20%)")
    ax.legend(ncol=3, loc="upper left")
    return _save(fig, "fig13_model_comparison")


def plot_confusion(cm: np.ndarray, classes, name: str) -> Path:
    _style()
    fig, ax = plt.subplots(figsize=(5.2, 4.4))
    pct = cm / cm.sum(axis=1, keepdims=True)
    ax.imshow(pct, cmap=matplotlib.colors.LinearSegmentedColormap.from_list("b", ["#FFFFFF", C["highlight"]]),
              vmin=0, vmax=1)
    for i in range(len(classes)):
        for j in range(len(classes)):
            ax.text(j, i, f"{cm[i, j]:,}\n({100 * pct[i, j]:.0f}%)", ha="center", va="center", fontsize=9,
                    color="white" if pct[i, j] > 0.5 else C["text"])
    ax.set_xticks(range(len(classes)), classes)
    ax.set_yticks(range(len(classes)), classes)
    ax.set_xlabel("Predicted class")
    ax.set_ylabel("Actual class")
    ax.grid(False)
    ax.set_title(f"Confusion matrix (test set)\n{name}", fontsize=11)
    return _save(fig, "fig14_confusion_matrix")


def plot_importance(imp: pd.DataFrame, name: str, top: int = 15) -> Path:
    _style()
    d = imp.head(top)
    fig, ax = plt.subplots(figsize=(8, 5))
    y = np.arange(len(d))
    ax.barh(y, d["importance_mean"], xerr=d["importance_std"], color=C["accent"], height=0.65,
            error_kw={"ecolor": C["text2"], "elinewidth": 0.8, "capsize": 2})
    ax.set_yticks(y, d["feature"])
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Drop in macro-F1 when the feature is shuffled (test set)")
    ax.set_title(f"Top {top} features by permutation importance: {name}")
    return _save(fig, "fig15_feature_importance")


# ------------------------------------------------------------------ orchestration
def _fmt(v):
    return f"{v:.3f}" if isinstance(v, (float, np.floating)) else str(v)


def write_results_md(res: dict, cm: np.ndarray, imp: pd.DataFrame, preds: pd.DataFrame, figs: list[Path],
                     extra: list[str] | None = None) -> None:
    comp, classes = res["comparison"], res["classes"]
    best = comp[comp["model"] == res["best_name"]].iloc[0]
    base = comp[comp["model"].str.startswith("Baseline")].iloc[0]
    cols = ["model", "cv_f1_macro_mean", "cv_f1_macro_std", "test_accuracy", "test_precision_macro",
            "test_recall_macro", "test_f1_macro", "test_f1_weighted", "test_roc_auc_ovr_macro"]
    lines = [
        "# Popularity Model Results",
        "",
        "*Generated by `src/model.py`. All numbers come from the run; nothing is typed in.*",
        "",
        "## Target definition",
        "",
        f"**{TARGET_DEFINITION}** {EXCLUDED_FEATURES_NOTE}",
        "",
        "## Setup",
        "",
        f"- Target: `popularity_class` (Option B: within-country tertiles of votes), rated restaurants only "
        f"(n = {len(res['y']):,}). Unrated restaurants are excluded.",
        f"- Split: {int((1 - TEST_SIZE) * 100)}/{int(TEST_SIZE * 100)} stratified, random_state = {RANDOM_STATE} "
        f"(train {len(res['y_train']):,}, test {len(res['y_test']):,}).",
        f"- Tuning: {CV_FOLDS}-fold stratified CV on the training set, scored by macro-F1. Best model chosen by CV "
        "score, then evaluated once on the test set.",
        f"- Features ({res['X'].shape[1]}): {', '.join(res['X'].columns)}.",
        "- **Excluded (leakage):** votes, aggregate_rating, rating_text, rating_color, is_rated, votes_pct_in_country "
        "and any aggregate of votes or rating. Checked in code by `assert_no_leakage`.",
        "",
        "## Model comparison",
        "",
        "| " + " | ".join(cols) + " |",
        "|" + "---|" * len(cols),
    ]
    for r in comp[cols].itertuples(index=False):
        lines.append("| " + " | ".join(_fmt(v) for v in r) + " |")
    lines += [
        "",
        f"**Best model (by CV macro-F1): {res['best_name']}**, with test accuracy {best['test_accuracy']:.3f}, "
        f"macro-F1 {best['test_f1_macro']:.3f} and ROC-AUC {best['test_roc_auc_ovr_macro']:.3f}. The majority-class "
        f"baseline scores accuracy {base['test_accuracy']:.3f}. For comparison, a model that is allowed to see "
        "votes and rating scores much higher (see *Leakage demonstration* below), but that score is not valid.",
        "",
        "Hyper-parameters chosen:",
        "",
    ]
    lines += [f"- {r.model}: `{r.best_params}`" for r in comp.itertuples(index=False)]
    lines += ["", "## Confusion matrix (best model, test set)", "",
              "| actual \\ predicted | " + " | ".join(classes) + " |", "|---|" + "---|" * len(classes)]
    for i, c in enumerate(classes):
        lines.append(f"| {c} | " + " | ".join(f"{v:,}" for v in cm[i]) + " |")
    per_class = {c: cm[i, i] / cm[i].sum() for i, c in enumerate(classes)}
    lines += ["", "Recall by class: " + ", ".join(f"{c} {v:.1%}" for c, v in per_class.items()) + ".", "",
              "## Feature importance (permutation, best model, test set)", "",
              "| rank | feature | importance (mean drop in macro-F1) | std |", "|---|---|---|---|"]
    for i, r in enumerate(imp.head(15).itertuples(index=False), start=1):
        lines.append(f"| {i} | {r.feature} | {r.importance_mean:.4f} | {r.importance_std:.4f} |")
    zone, rob = res["sampling_by_zone"], res["robustness"]
    lines += ["", "## Important caveat: uneven sampling by location", "",
              "Location features rank highest. The share of each popularity class differs strongly by zone:", "",
              "| zone | Low % | Medium % | High % | rated restaurants | median votes |", "|---|---|---|---|---|---|"]
    for r in zone.itertuples(index=False):
        lines.append(f"| {r.zone} | {r.Low:.1f} | {r.Medium:.1f} | {r.High:.1f} | {r.rated_restaurants:,} | "
                     f"{r.median_votes:.0f} |")
    lines += ["",
              "Outside Delhi NCR, Zomato appears to list only a small set of well-known (highly voted) restaurants "
              "per Indian city, so the model can partly learn *where* a restaurant was sampled. This is not leakage "
              "(location is a legitimate input), but it could inflate the score. Robustness checks with the same "
              "algorithm and hyper-parameters:", "",
              "| variant | rows | features | test accuracy | test macro-F1 | test ROC-AUC | majority baseline accuracy |",
              "|---|---|---|---|---|---|---|"]
    for r in rob.itertuples(index=False):
        lines.append(f"| {r.variant} | {r.rows:,} | {r.features} | {r.test_accuracy:.3f} | {r.test_f1_macro:.3f} | "
                     f"{r.test_roc_auc_ovr_macro:.3f} | {r.majority_baseline_accuracy:.3f} |")
    main_f1, ncr_f1, noloc_f1 = rob["test_f1_macro"].tolist()[:3]
    ncr_txt = ("about the same as" if abs(ncr_f1 - main_f1) <= 0.02 else
               "higher than" if ncr_f1 > main_f1 else "lower than")
    lines += ["",
              f"Interpretation: within Delhi NCR alone, where sampling is consistent, macro-F1 is {ncr_f1:.3f}, "
              f"{ncr_txt} the main model ({main_f1:.3f}), so the main result is "
              f"{'not mainly' if ncr_txt != 'lower than' else 'partly'} explained by the sampling pattern. "
              f"Removing all location features lowers macro-F1 to {noloc_f1:.3f} (still above the baseline), so "
              "*where* a restaurant is (down to locality) carries real signal, and price, services, cuisines and "
              "chain status add signal of their own."]
    leak = res["leakage_demo"]
    honest, leaky = leak.iloc[0], leak.iloc[1]
    lines += ["", "## Leakage demonstration (illustration only)", "",
              "Same Gradient Boosting hyper-parameters and the same 80/20 split (random_state = 42), but with "
              "`votes` and `aggregate_rating` added to the 34 features. This model is **not valid** and is never "
              "saved or used: the target is built from votes, so the inputs already contain the answer, which "
              "would not be known for a new restaurant.", "",
              "| model | features | test accuracy | test macro-F1 | test ROC-AUC |", "|---|---|---|---|---|"]
    for r in leak.itertuples(index=False):
        lines.append(f"| {r.model} | {r.features} | {r.test_accuracy:.3f} | {r.test_f1_macro:.3f} | "
                     f"{r.test_roc_auc_ovr_macro:.3f} |")
    lines += ["", f"Adding the two leaked columns raises test accuracy from {honest.test_accuracy:.1%} to "
              f"{leaky.test_accuracy:.1%} (macro-F1 {honest.test_f1_macro:.3f} -> {leaky.test_f1_macro:.3f}). "
              "The jump measures the leak, not real predictive skill."]
    lines += ["", "## Predictions file (Power BI page 4)", "",
              f"`outputs/predictions/popularity_predictions.csv`: {len(preds):,} rated restaurants. Test rows are "
              "predicted by the final model; training rows use out-of-fold (cross-validated) predictions, so no "
              f"restaurant is predicted by a model that was trained on it. Overall agreement: "
              f"{preds['correct'].mean():.1%}."]
    lines += (extra or []) + ["", "## Figures", ""]
    lines += [f"- `{p.relative_to(config.ROOT).as_posix()}`" for p in figs]
    lines.append("")
    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")


def run_model(clean: pd.DataFrame, pairs: pd.DataFrame, verbose: bool = True) -> dict:
    res = train_and_evaluate(clean, pairs, verbose)
    best, classes = res["best"], res["classes"]
    pred_te = best.predict(res["X_test"])
    cm = confusion_matrix(res["y_test"], pred_te, labels=classes)
    imp = feature_importance(res)
    preds = predictions_table(res, clean)
    res["sampling_by_zone"] = sampling_by_zone(clean)
    res["robustness"] = robustness_checks(res, clean)
    for r in res["robustness"].itertuples(index=False):
        (print if verbose else (lambda *a: None))(
            f"      check: {r.variant:<40} acc {r.test_accuracy:.3f}, macro-F1 {r.test_f1_macro:.3f}, "
            f"AUC {r.test_roc_auc_ovr_macro:.3f} (baseline {r.majority_baseline_accuracy:.3f})")
    res["leakage_demo"] = leakage_demo(res, clean)
    lk = res["leakage_demo"].iloc[1]
    (print if verbose else (lambda *a: None))(
        f"      leakage demo (illustration only, + votes & rating): acc {lk.test_accuracy:.3f}, "
        f"macro-F1 {lk.test_f1_macro:.3f}, AUC {lk.test_roc_auc_ovr_macro:.3f}")

    PRED_DIR.mkdir(parents=True, exist_ok=True)
    res["comparison"].to_csv(PRED_DIR / "model_comparison.csv", index=False)
    pd.DataFrame(cm, index=pd.Index(classes, name="actual"), columns=classes).to_csv(PRED_DIR / "confusion_matrix.csv")
    imp.to_csv(PRED_DIR / "feature_importance.csv", index=False)
    res["robustness"].to_csv(PRED_DIR / "robustness_checks.csv", index=False)
    res["leakage_demo"].to_csv(PRED_DIR / "leakage_demo.csv", index=False)
    preds.to_csv(PRED_DIR / "popularity_predictions.csv", index=False)

    figs = [plot_comparison(res["comparison"]), plot_confusion(cm, classes, res["best_name"]),
            plot_importance(imp, res["best_name"])]
    from src.model_variants import run_variants, variants_markdown  # local import: avoids a circular import
    res["variants"] = run_variants(res, clean, verbose)
    figs += res["variants"]["figures"]
    from src.model_medium import medium_markdown, run_medium
    res["medium"] = run_medium(res, clean, verbose)
    figs += res["medium"]["figures"]

    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(best, MODEL_PATH, compress=3)
    meta = {"best_model": res["best_name"], "selected_by": "mean 5-fold CV macro-F1 on training set",
            "random_state": RANDOM_STATE, "test_size": TEST_SIZE, "features": list(res["X"].columns),
            "classes": classes, "n_train": len(res["y_train"]), "n_test": len(res["y_test"]),
            "test_metrics": {k: float(v) for k, v in res["comparison"].set_index("model").loc[res["best_name"]].items()
                             if k.startswith("test_")}}
    MODEL_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    write_results_md(res, cm, imp, preds, figs,
                     extra=variants_markdown(res["variants"]) + medium_markdown(res["medium"]))
    res.update({"confusion": cm, "importance": imp, "predictions": preds, "figures": figs, "meta": meta})
    return res
