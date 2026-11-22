"""Phase 3 tests: recommendation engine and popularity model.

Model tests read the outputs written by `python run_pipeline.py` (skipped if they do not exist yet).
"""
from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd
import pytest

from src import config
from src.features import assert_no_leakage, build_features
from src.model import MODEL_META, MODEL_PATH, PRED_DIR, TEST_SIZE, prepare_data
from src.recommender import SCENARIOS, WEIGHTS, Request, _budget_score, recommend
from src.target import FORBIDDEN_FEATURES, LABELS

P = config.DEFAULT_PATHS


@pytest.fixture(scope="module")
def clean():
    return pd.read_csv(P.clean_csv)


@pytest.fixture(scope="module")
def pairs():
    return pd.read_csv(P.cuisines_csv)


def _need(path):
    if not path.exists():
        pytest.skip(f"{path.name} missing - run `python run_pipeline.py` first")


# ================================================================ recommendation engine
def test_weights_match_specification():
    assert WEIGHTS == {"rating": 0.40, "popularity": 0.25, "budget": 0.20, "cuisine": 0.15}
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)


@pytest.mark.parametrize("sid", list(SCENARIOS))
def test_scenario_results_obey_rules(clean, sid):
    req = SCENARIOS[sid]
    res = recommend(clean, req)
    assert 0 < len(res) <= req.top_n
    assert (res["city"].str.lower() == req.city.lower()).all()
    assert (res["aggregate_rating"] >= req.min_rating).all()
    if req.delivery == "required":
        assert (res["has_online_delivery"] == 1).all()
    if req.locality:
        assert res["locality"].str.lower().str.contains(req.locality.lower()).all()
    for k in WEIGHTS:
        assert res[f"{k}_score"].between(0, 1).all()
        assert np.allclose(res[f"{k}_points"], WEIGHTS[k] * res[f"{k}_score"])
    assert np.allclose(res["total_score"], res[[f"{k}_points" for k in WEIGHTS]].sum(axis=1))
    assert res["total_score"].is_monotonic_decreasing
    assert list(res["rank"]) == list(range(1, len(res) + 1))


def test_cuisine_match_score(clean):
    res = recommend(clean, Request("New Delhi", ["Chinese"], top_n=50))
    offers = res["cuisines"].str.split(", ").map(lambda c: "Chinese" in c)
    assert (res.loc[offers, "cuisine_score"] == 1).all()
    assert (res.loc[~offers, "cuisine_score"] == 0).all()


def test_budget_score_rules(clean):
    cost = clean["avg_cost_for_two"].dropna().head(200)
    budget = float(cost.median())
    s = _budget_score(cost, budget)
    assert (s[cost <= budget] == 1).all()
    assert (s[cost >= 2 * budget] == 0).all()
    assert s.between(0, 1).all()
    assert _budget_score(pd.Series([np.nan]), budget).iloc[0] == 0.5


def test_every_city_has_one_local_currency(clean):
    from src.recommender import city_candidates
    for city in clean["city"].unique():
        assert city_candidates(clean, Request(city))["currency"].nunique() == 1, city


@pytest.mark.parametrize("city, budget, expected", [
    ("London", 60, "Pounds(£)"),
    ("New Delhi", 800, "Indian Rupees(Rs.)"),
    ("Makati City", 1500, "Philippine Peso(P)"),
])
def test_budget_is_in_local_currency(clean, city, budget, expected):
    """Budget and the costs it is compared with are in the city's own currency (no conversion)."""
    res = recommend(clean, Request(city, budget=budget, top_n=50))
    assert (res["budget_currency"] == expected).all()
    assert (res["currency"] == expected).all()
    assert (res["budget"] == budget).all()
    assert np.allclose(res["budget_score"], _budget_score(res["avg_cost_for_two"], budget))


def test_same_number_means_different_money_in_different_cities(clean):
    """A budget of 60 is generous in London (GBP) but below every restaurant's cost in New Delhi (INR)."""
    london = recommend(clean, Request("London", budget=60, top_n=50))
    delhi = recommend(clean, Request("New Delhi", budget=60, top_n=50))
    assert london["budget_score"].mean() > delhi["budget_score"].mean()
    known = delhi["avg_cost_for_two"].notna()
    assert (delhi.loc[known & (delhi["avg_cost_for_two"] >= 120), "budget_score"] == 0).all()


def test_city_with_two_currencies_requires_country():
    two = pd.read_csv(config.FIXTURES_DIR / "SYNTHETIC_same_city_two_currencies.csv")
    with pytest.raises(ValueError, match="several currencies"):
        recommend(two, Request("Springfield", budget=50))
    res = recommend(two, Request("Springfield", budget=50, country="United Kingdom"))
    assert set(res["budget_currency"]) == {"Pounds(£)"} and set(res["country"] if "country" in res else
                                                                 ["United Kingdom"]) == {"United Kingdom"}
    assert len(res) == 2


def test_unknown_inputs_give_clear_errors(clean):
    with pytest.raises(ValueError, match="not found"):
        recommend(clean, Request("Atlantis"))
    with pytest.raises(ValueError, match="Unknown cuisine"):
        recommend(clean, Request("New Delhi", ["Martian"]))


def test_impossible_filters_return_empty(clean):
    assert recommend(clean, Request("New Delhi", min_rating=5.0)).empty


# ================================================================ features / leakage
def test_features_contain_no_forbidden_columns(clean, pairs):
    X = build_features(clean, pairs)
    assert not set(X.columns) & set(FORBIDDEN_FEATURES)
    assert not [c for c in X.columns if "vote" in c or "rating" in c]


def test_leakage_guard_rejects_forbidden_feature():
    with pytest.raises(ValueError, match="Leakage"):
        assert_no_leakage(["price_range", "votes"])
    with pytest.raises(ValueError, match="Leakage"):
        assert_no_leakage(["aggregate_rating"])


def test_training_data_is_rated_only(clean, pairs):
    X, y = prepare_data(clean, pairs)
    assert len(y) == int(clean["is_rated"].sum())
    assert set(y.unique()) == set(LABELS)
    unrated_ids = set(clean.loc[clean["is_rated"] == 0, "restaurant_id"])
    assert not unrated_ids & set(X.index)


# ================================================================ model outputs
def test_model_comparison_table():
    _need(PRED_DIR / "model_comparison.csv")
    comp = pd.read_csv(PRED_DIR / "model_comparison.csv")
    assert {"Logistic Regression", "Decision Tree", "Random Forest", "Gradient Boosting"} <= set(comp["model"])
    metric_cols = [c for c in comp.columns if c.startswith("test_") or c.startswith("cv_f1_macro_mean")]
    assert comp[metric_cols].apply(lambda s: s.between(0, 1)).all().all()


def test_best_model_chosen_by_cv_not_test():
    _need(MODEL_META)
    comp = pd.read_csv(PRED_DIR / "model_comparison.csv")
    meta = json.loads(MODEL_META.read_text())
    real = comp[~comp["model"].str.startswith("Baseline")]
    assert meta["best_model"] == real.loc[real["cv_f1_macro_mean"].idxmax(), "model"]
    assert meta["random_state"] == 42 and meta["test_size"] == TEST_SIZE
    base = comp[comp["model"].str.startswith("Baseline")].iloc[0]
    assert meta["test_metrics"]["test_f1_macro"] > base["test_f1_macro"]


def test_saved_model_loads_and_predicts(clean, pairs):
    _need(MODEL_PATH)
    model = joblib.load(MODEL_PATH)
    meta = json.loads(MODEL_META.read_text())
    X, _ = prepare_data(clean, pairs)
    assert list(X.columns) == meta["features"]
    pred = model.predict(X.head(50))
    assert set(pred) <= set(LABELS)
    proba = model.predict_proba(X.head(50))
    assert np.allclose(proba.sum(axis=1), 1)


def test_predictions_file_for_power_bi(clean):
    _need(PRED_DIR / "popularity_predictions.csv")
    p = pd.read_csv(PRED_DIR / "popularity_predictions.csv")
    rated = clean[clean["is_rated"] == 1]
    assert len(p) == len(rated) and not p["restaurant_id"].duplicated().any()
    assert set(p["restaurant_id"]) == set(rated["restaurant_id"])
    assert np.allclose(p[["prob_low", "prob_medium", "prob_high"]].sum(axis=1), 1, atol=1e-6)
    argmax = p[["prob_low", "prob_medium", "prob_high"]].idxmax(axis=1).map(
        {"prob_low": "Low", "prob_medium": "Medium", "prob_high": "High"})
    assert (argmax == p["predicted_class"]).all()
    actual = rated.set_index("restaurant_id")["popularity_class"]
    assert (p.set_index("restaurant_id")["actual_class"] == actual.reindex(p["restaurant_id"]).values).all()
    assert (p["split"] == "test").sum() == pytest.approx(TEST_SIZE * len(p), abs=1)


def test_report_outputs_exist():
    for name in ["fig13_model_comparison", "fig14_confusion_matrix", "fig15_feature_importance"]:
        assert (config.FIGURES_DIR / f"{name}.png").exists()
    for f in ["confusion_matrix.csv", "feature_importance.csv", "robustness_checks.csv"]:
        assert (PRED_DIR / f).exists()
    assert (config.DOCS_DIR / "model_results.md").exists()
    assert (config.DOCS_DIR / "recommendation_examples.md").exists()


def test_leakage_demo_is_illustration_only():
    """The leaky model (votes + rating added) must score far higher than the honest model, and must never be
    the saved model: the saved model's features contain no forbidden column."""
    import json
    from src.features import assert_no_leakage
    path = config.PREDICTIONS_DIR / "leakage_demo.csv"
    if not path.exists():
        pytest.skip("leakage_demo.csv missing - run `python run_pipeline.py` first")
    demo = pd.read_csv(path)
    honest, leaky = demo.iloc[0], demo.iloc[1]
    assert leaky["features"] == honest["features"] + 2
    assert leaky["test_accuracy"] > honest["test_accuracy"] + 0.2
    meta = json.loads((config.MODELS_DIR / "popularity_model_meta.json").read_text(encoding="utf-8"))
    assert_no_leakage(meta["features"])
    assert abs(meta["test_metrics"]["test_accuracy"] - honest["test_accuracy"]) < 1e-12
