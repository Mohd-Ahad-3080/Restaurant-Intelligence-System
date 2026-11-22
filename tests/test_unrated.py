"""Unrated restaurants: counts, treatment rules and saved-model predictions (real outputs)."""
import pandas as pd
import pytest

from src import config
from src.target import LABELS

OUT = config.ROOT / "outputs" / "unrated"


@pytest.fixture(scope="module")
def clean():
    return pd.read_csv(config.PROCESSED_DIR / "zomato_clean.csv")


@pytest.fixture(scope="module")
def out():
    if not (OUT / "unrated_predictions.csv").exists():
        pytest.skip("Run `python run_pipeline.py` first")
    return {f.stem: pd.read_csv(f) for f in OUT.glob("*.csv")}


def test_unrated_are_missing_not_zero(clean):
    u = clean[clean["is_rated"] == 0]
    assert u["aggregate_rating"].isna().all()
    assert u["popularity_class"].isna().all()
    assert clean.loc[clean["is_rated"] == 1, "popularity_class"].notna().all()


def test_predictions_cover_every_unrated_restaurant(clean, out):
    p = out["unrated_predictions"]
    assert set(p["restaurant_id"]) == set(clean.loc[clean["is_rated"] == 0, "restaurant_id"])
    assert set(p["predicted_class"]) <= set(LABELS)
    assert (p["actual_class"] == "none (unrated)").all()
    assert (p[["prob_low", "prob_medium", "prob_high"]].sum(axis=1) - 1).abs().max() < 1e-6


def test_profile_tables_consistent(clean, out):
    s = out["unrated_services"].set_index("group")
    assert s.loc["Unrated", "restaurants"] == (clean["is_rated"] == 0).sum()
    assert s.loc["Rated", "restaurants"] == (clean["is_rated"] == 1).sum()
    pr = out["unrated_price_range"]
    assert pr["Rated"].sum() == pytest.approx(100) and pr["Unrated"].sum() == pytest.approx(100)
    c = out["unrated_by_country"]
    assert c["unrated"].sum() == (clean["is_rated"] == 0).sum()


def test_doc_written():
    assert (config.DOCS_DIR / "unrated_restaurants.md").exists()
