"""Model variants: feature selection rules (unit) and the generated comparison table (real outputs)."""
import pandas as pd
import pytest

from src import config
from src.features import assert_no_leakage
from src.model import LOCATION_FEATURES
from src.model_variants import BASELINE, HONEST, INDIA_LOC, INDIA_NO_LOC, LEAKY, MAIN, NO_LOC, select_features

P = config.PREDICTIONS_DIR


def test_select_features_rules():
    cols = ["country", "city_group", "latitude", "longitude", "has_valid_coords", "log_locality_size",
            "price_range", "cuisine_cafe"]
    assert select_features(cols, drop_location=True, india_only=False) == ["price_range", "cuisine_cafe"]
    assert select_features(cols, drop_location=False, india_only=True) == cols[1:]
    assert select_features(cols, drop_location=True, india_only=True) == ["price_range", "cuisine_cafe"]


@pytest.fixture(scope="module")
def variants():
    if not (P / "model_variants.csv").exists():
        pytest.skip("Run `python run_pipeline.py` first")
    return {k: pd.read_csv(P / f"model_variants{k}.csv") for k in ["", "_per_class", "_confusion", "_importance"]}


def test_all_six_variants_present(variants):
    s = variants[""]
    assert list(s["variant"]) == list(HONEST) + [BASELINE, LEAKY]
    assert (s["valid"] == "yes").sum() == 5 and s.set_index("variant").loc[LEAKY, "valid"].startswith("NO")


def test_honest_variants_are_leak_free_and_location_rules_hold(variants):
    s = variants[""].set_index("variant")
    for v in HONEST:
        assert_no_leakage(s.loc[v, "features_used"].split("; "))
    for v in [NO_LOC, INDIA_NO_LOC]:
        assert not set(s.loc[v, "features_used"].split("; ")) & set(LOCATION_FEATURES)
    assert "votes" in s.loc[LEAKY, "features_used"].split("; ")


def test_india_variants_use_rated_indian_restaurants_only(variants):
    clean = pd.read_csv(config.PROCESSED_DIR / "zomato_clean.csv")
    n = int(((clean["country"] == "India") & (clean["is_rated"] == 1)).sum())
    s = variants[""].set_index("variant")
    assert s.loc[INDIA_LOC, "rows"] == n and s.loc[INDIA_NO_LOC, "rows"] == n


def test_variants_reproduce_existing_results(variants):
    """Main, no-location and leaky rows must equal the numbers already reported elsewhere."""
    s = variants[""].set_index("variant")
    comp = pd.read_csv(P / "model_comparison.csv").set_index("model")
    rob = pd.read_csv(P / "robustness_checks.csv").set_index("variant")
    leak = pd.read_csv(P / "leakage_demo.csv")
    assert s.loc[MAIN, "test_accuracy"] == pytest.approx(comp.loc["Gradient Boosting", "test_accuracy"])
    assert s.loc[BASELINE, "test_accuracy"] == pytest.approx(comp.loc["Baseline (majority class)", "test_accuracy"])
    assert s.loc[NO_LOC, "test_f1_macro"] == pytest.approx(
        rob.loc["All rated, location features removed", "test_f1_macro"])
    assert s.loc[LEAKY, "test_accuracy"] == pytest.approx(leak.iloc[1]["test_accuracy"])


def test_confusion_and_per_class_consistent(variants):
    s = variants[""].set_index("variant")
    conf, pc = variants["_confusion"], variants["_per_class"]
    for v in s.index:
        assert conf.query("variant == @v")["count"].sum() == s.loc[v, "n_test"]
        assert pc.query("variant == @v")["support"].sum() == s.loc[v, "n_test"]
        assert len(pc.query("variant == @v")) == 3
