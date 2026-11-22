"""Medium class: unit tests of the decision rules on SYNTHETIC inputs, plus checks of the real outputs."""
import numpy as np
import pandas as pd
import pytest

from src import config
from src.features import assert_no_leakage
from src.model_medium import (BEFORE, ORDINAL, THRESHOLD, WEIGHTS, apply_medium_bias, class_cutoffs,
                              distance_to_cutoffs, ordinal_proba)

P = config.PREDICTIONS_DIR
FIX = config.ROOT / "tests" / "fixtures" / "SYNTHETIC_votes_classes.csv"


def test_medium_bias_rule():
    proba = np.array([[0.5, 0.3, 0.2], [0.2, 0.35, 0.45]])
    assert list(apply_medium_bias(proba, 0.0)) == ["Low", "High"]
    assert list(apply_medium_bias(proba, 0.25)) == ["Medium", "Medium"]
    assert "Medium" not in apply_medium_bias(proba, -1.0)


def test_ordinal_probabilities_are_valid():
    rng = np.random.default_rng(0)
    p1, p2 = rng.random(200), rng.random(200)  # includes rows where P(>Medium) > P(>Low)
    p = ordinal_proba(p1, p2)
    assert (p >= 0).all() and np.allclose(p.sum(axis=1), 1)
    assert np.allclose(ordinal_proba([0.0], [0.0]), [[1, 0, 0]])
    assert np.allclose(ordinal_proba([1.0], [1.0]), [[0, 0, 1]])


def test_cutoffs_on_synthetic_fixture():
    d = pd.read_csv(FIX)
    cuts = class_cutoffs(d).set_index("country")
    assert cuts.loc["Testland", "cut_low_medium"] == 2.5 and cuts.loc["Testland", "cut_medium_high"] == 4.5
    dist = distance_to_cutoffs(d, cuts.reset_index()).set_index("restaurant_id")
    assert dist.loc[900103, "votes_to_cutoff"] == 0.5
    assert dist["pct_to_cutoff"].max() <= 1 / 3 + 1e-9


@pytest.fixture(scope="module")
def outputs():
    if not (P / "medium_class_methods.csv").exists():
        pytest.skip("Run `python run_pipeline.py` first")
    return {f: pd.read_csv(P / f"{f}.csv") for f in
            ["medium_class_methods", "medium_class_per_class", "medium_class_distance_by_class",
             "high_vs_low_model", "model_comparison"]}


def test_methods_and_before_matches_main_model(outputs):
    m = outputs["medium_class_methods"].set_index("method")
    assert list(m.index) == [BEFORE, WEIGHTS, THRESHOLD, ORDINAL]
    main = outputs["model_comparison"].set_index("model").loc["Gradient Boosting"]
    assert m.loc[BEFORE, "test_accuracy"] == pytest.approx(main["test_accuracy"])
    pc = outputs["medium_class_per_class"]
    assert len(pc) == 12 and pc.groupby("method")["support"].sum().nunique() == 1


def test_medium_is_within_one_sixth_of_a_cutoff(outputs):
    by = outputs["medium_class_distance_by_class"].set_index("class")
    assert by.loc["Medium", "max_pct_points_to_cutoff"] <= 100 / 6 + 1e-6


def test_high_vs_low_excludes_medium():
    clean = pd.read_csv(config.PROCESSED_DIR / "zomato_clean.csv")
    path = P / "high_vs_low_model.csv"
    if not path.exists():
        pytest.skip("Run `python run_pipeline.py` first")
    b = pd.read_csv(path).iloc[0]
    assert b["rows"] == int(clean["popularity_class"].isin(["Low", "High"]).sum())
    assert "separate question" in b["model"]
    import json
    meta = json.loads((config.MODELS_DIR / "popularity_model_meta.json").read_text(encoding="utf-8"))
    assert_no_leakage(meta["features"])
