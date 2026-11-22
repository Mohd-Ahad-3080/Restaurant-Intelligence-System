"""Commands used in docs/HOW_TO_RUN.md: recommend / predict scripts and `run_pipeline.py --input`.

The sample file data/samples/zomato_sample_india_3cities.csv contains REAL Kaggle rows (every restaurant
in Ghaziabad, Amritsar and Agra), not synthetic data.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from src import config
from src.data_loading import load_validated

ROOT = config.ROOT
SAMPLE = ROOT / "data" / "samples" / "zomato_sample_india_3cities.csv"
PREDICTIONS = config.PREDICTIONS_DIR / "popularity_predictions.csv"


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def needs_outputs():
    if not (config.MODELS_DIR / "popularity_model.joblib").exists() or not PREDICTIONS.exists():
        pytest.skip("Run `python run_pipeline.py` first")


def test_recommend_script_reproduces_report_example(needs_outputs, capsys):
    rc = _script("recommend").main(["--city", "New Delhi", "--cuisine", "North Indian", "--budget", "800",
                                    "--min-rating", "3.5", "--delivery", "required", "--top", "5"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "in city: 5,473 -> rating >= 3.5: 1,456 -> offers online delivery: 670" in out
    first = next(l for l in out.splitlines() if l.strip().startswith("1 "))
    assert "QD's Restaurant" in first and first.rstrip().endswith("0.882")


def test_recommend_script_unknown_city(needs_outputs, capsys):
    assert _script("recommend").main(["--city", "Atlantis"]) == 1
    assert "not found" in capsys.readouterr().err


def test_predict_script_runs(needs_outputs, capsys):
    rc = _script("predict").main(["--city", "New Delhi", "--locality", "Connaught Place", "--cuisines",
                                  "North Indian, Chinese", "--price-range", "2", "--cost", "600",
                                  "--delivery", "yes", "--booking", "no"])
    out = capsys.readouterr().out
    assert rc == 0 and "PREDICTED POPULARITY:" in out
    pcts = [float(l.split()[1].rstrip("%")) for l in out.splitlines() if l.strip().startswith(("High ", "Medium ", "Low "))]
    assert len(pcts) == 3 and abs(sum(pcts) - 100) < 0.5


def test_prediction_ignores_votes_and_rating(needs_outputs):
    """Leakage rule: the same restaurant with very different votes/rating must get identical probabilities."""
    from src.scoring import new_restaurant_raw, predict_raw
    row, _ = new_restaurant_raw("Gurgaon", ["Italian"], 3, 1500, True, True, locality="Sector 29")
    a = predict_raw(row)
    row2 = row.assign(**{"Votes": 5000, "Aggregate rating": 4.9, "Rating text": "Excellent"})
    b = predict_raw(row2)
    cols = ["prob_low", "prob_medium", "prob_high"]
    assert (a[cols].values == b[cols].values).all()


def test_scoring_known_rows_matches_training(needs_outputs):
    """Rows already in the Kaggle file get exactly the probabilities the model gave in Phase 3 (test rows)."""
    from src.scoring import predict_raw
    new = predict_raw(load_validated(SAMPLE).df)
    orig = pd.read_csv(PREDICTIONS)
    m = new.merge(orig[orig["split"] == "test"], on="restaurant_id", suffixes=("", "_orig"))
    assert len(m) > 0
    for c in ("prob_low", "prob_medium", "prob_high"):
        assert (m[c] - m[f"{c}_orig"]).abs().max() < 1e-9


def test_sample_file_is_real_kaggle_rows():
    sample = pd.read_csv(SAMPLE, encoding="latin-1", dtype=str, keep_default_na=False)
    raw = pd.read_csv(config.RAW_ZOMATO_CSV, encoding="latin-1", dtype=str, keep_default_na=False)
    assert list(sample.columns) == list(raw.columns)
    assert sample["City"].value_counts().to_dict() == {"Ghaziabad": 25, "Amritsar": 21, "Agra": 20}
    merged = sample.merge(raw, how="left", indicator=True)
    assert (merged["_merge"] == "both").all()


def test_pipeline_input_runs_recommend_and_predict(needs_outputs, tmp_path):
    import run_pipeline
    official = config.PROCESSED_DIR / "zomato_clean.csv"
    before = official.stat().st_mtime
    res = run_pipeline.run_new_file(SAMPLE, excel=True, out_dir=tmp_path, verbose=False)
    for f in ("processed/zomato_clean.csv", "processed/restaurant_cuisines.csv", "processed/cleaning_log.csv",
              "docs/data_dictionary.md", "docs/data_quality_report.md", "excel/zomato_phase1_analysis.xlsx",
              "recommendations.csv", "predictions.csv"):
        assert (tmp_path / f).exists(), f
    assert len(res["clean"]) == 66
    preds = pd.read_csv(tmp_path / "predictions.csv")
    assert len(preds) == 66 and set(preds["predicted_class"]) <= {"Low", "Medium", "High"}
    recs = pd.read_csv(tmp_path / "recommendations.csv")
    assert sorted(recs["city"].unique()) == ["Agra", "Amritsar", "Ghaziabad"]
    assert official.stat().st_mtime == before          # official Kaggle outputs untouched
