"""Phase 1 tests.

Rule checks (columns exist, ratings 0-5, IDs unique, log consistency ...) run on the official
Kaggle outputs. The same rules, plus exact expected results, are unit-tested on a small hand-made
SYNTHETIC fixture (tests/fixtures/) whose deliberate problems are known in advance.
"""
from __future__ import annotations

import pandas as pd
import pytest
from openpyxl import load_workbook

from src import config
from src.cleaning import RENAME, clean
from src.data_loading import load_raw_zomato, load_validated
from src.excel_report import SHEETS, build_workbook
from src.kpis import headline_kpis
from src.schema import REQUIRED_COLUMNS, SchemaError, validate
from src.target import LABELS

FIXTURE = config.FIXTURES_DIR / "SYNTHETIC_sample_zomato.csv"
EXPECTED_CLEAN_COLUMNS = list(RENAME.values()) + [
    "n_cuisines", "is_rated", "is_cost_outlier", "avg_cost_for_two_usd", "has_valid_coords", "votes_pct_in_country",
    "popularity_class"]


# ----------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def fixture_run(tmp_path_factory):
    """Load + clean the synthetic sample and build its workbook in a temp folder."""
    out = tmp_path_factory.mktemp("fixture_run")
    paths = config.RunPaths(out, out, out)
    res = load_validated(FIXTURE)
    cleaned, pairs, log = clean(res.df)
    build_workbook(load_raw_zomato(FIXTURE), pd.DataFrame(), pd.DataFrame(), log, cleaned, pairs,
                   paths.excel_report)
    return {"paths": paths, "clean": cleaned, "pairs": pairs, "log": log,
            "kpis": headline_kpis(cleaned, pairs), "warnings": res.warnings}


@pytest.fixture(scope="module")
def kaggle_outputs():
    """Official outputs produced by `python run_pipeline.py` on the Kaggle file."""
    p = config.DEFAULT_PATHS
    if not p.clean_csv.exists():
        pytest.skip("Run `python run_pipeline.py` first to create the official outputs.")
    return {
        "paths": p,
        "clean": pd.read_csv(p.clean_csv),
        "pairs": pd.read_csv(p.cuisines_csv),
        "log": pd.read_csv(p.cleaning_log_csv),
    }


def _outputs(request, which):
    return request.getfixturevalue("fixture_run" if which == "fixture" else "kaggle_outputs")


BOTH = pytest.mark.parametrize("which", ["fixture", "kaggle"])


# ----------------------------------------------------------------------------- input files
def test_raw_files_exist():
    assert config.RAW_ZOMATO_CSV.exists(), "data/raw/zomato.csv is missing"
    assert config.RAW_COUNTRY_XLSX.exists(), "data/raw/Country-Code.xlsx is missing"


def test_raw_file_has_required_columns():
    raw = load_raw_zomato()
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    assert not missing, f"Missing columns: {missing}"


def test_kaggle_file_passes_schema_validation():
    res = load_validated()
    assert len(res.df) > 0
    assert "Country" in res.df.columns


# ----------------------------------------------------------------------------- schema errors
def test_schema_reports_missing_column():
    df = pd.read_csv(FIXTURE).drop(columns=["Votes", "City"])
    with pytest.raises(SchemaError) as e:
        validate(df)
    assert "'Votes'" in str(e.value) and "'City'" in str(e.value)


def test_schema_reports_wrongly_typed_column():
    df = pd.read_csv(FIXTURE)
    df["Aggregate rating"] = "very good"
    with pytest.raises(SchemaError) as e:
        validate(df)
    assert "Aggregate rating" in str(e.value)


# ----------------------------------------------------------------------------- clean-data rules (both datasets)
@BOTH
def test_clean_has_expected_columns(request, which):
    clean = _outputs(request, which)["clean"]
    assert list(clean.columns) == EXPECTED_CLEAN_COLUMNS


@BOTH
def test_no_duplicate_ids(request, which):
    clean = _outputs(request, which)["clean"]
    assert clean["restaurant_id"].notna().all()
    assert not clean["restaurant_id"].duplicated().any()


@BOTH
def test_ratings_within_0_to_5_and_zero_means_missing(request, which):
    clean = _outputs(request, which)["clean"]
    r = clean["aggregate_rating"].dropna()
    assert r.between(0, 5).all()
    assert (r > 0).all(), "rating 0 must have been converted to missing"
    assert ((clean["aggregate_rating"].notna()).astype(int) == clean["is_rated"]).all()


@BOTH
def test_row_count_matches_cleaning_log(request, which):
    o = _outputs(request, which)
    log = o["log"]
    assert int(log.iloc[-1]["rows_after"]) == len(o["clean"])
    dropped = log.loc[log["step"].str.startswith("Drop"), "rows_affected"].sum()
    assert int(log.iloc[0]["rows_after"]) - dropped == len(o["clean"])


@BOTH
def test_value_rules(request, which):
    c = _outputs(request, which)["clean"]
    for col in ["has_table_booking", "has_online_delivery", "is_delivering_now", "switch_to_order_menu",
                "is_rated", "is_cost_outlier", "has_valid_coords"]:
        assert c[col].dropna().isin([0, 1]).all(), col
    assert c["price_range"].dropna().isin([1, 2, 3, 4]).all()
    assert (c["avg_cost_for_two"].dropna() > 0).all()
    assert (c["votes"].dropna() >= 0).all()
    valid = c[c["has_valid_coords"] == 1]
    assert valid["latitude"].between(-90, 90).all() and valid["longitude"].between(-180, 180).all()
    assert ((valid["latitude"] != 0) & (valid["longitude"] != 0)).all()
    assert c.loc[c["has_valid_coords"] == 0, ["latitude", "longitude"]].isna().all().all()


@BOTH
def test_no_invisible_control_characters(request, which):
    c = _outputs(request, which)["clean"]
    for col in c.select_dtypes(exclude="number").columns:
        assert not c[col].dropna().astype(str).str.contains(r"[\x80-\x9f]", regex=True).any(), col


@BOTH
def test_popularity_class_rules(request, which):
    c = _outputs(request, which)["clean"]
    assert set(c["popularity_class"].dropna().unique()) <= set(LABELS)
    # classes only for rated restaurants, and every rated restaurant gets one
    assert (c["popularity_class"].notna() == (c["is_rated"] == 1)).all()


@BOTH
def test_cuisine_pairs_rules(request, which):
    o = _outputs(request, which)
    pairs, clean = o["pairs"], o["clean"]
    assert set(pairs["restaurant_id"]) <= set(clean["restaurant_id"])
    assert not pairs.duplicated().any()
    assert "Unknown" not in set(pairs["cuisine"])
    assert (pairs["cuisine"] == pairs["cuisine"].str.strip()).all()


@BOTH
def test_excel_opens_with_all_sheets(request, which):
    path = _outputs(request, which)["paths"].excel_report
    assert path.exists()
    wb = load_workbook(path, read_only=True)
    assert wb.sheetnames == SHEETS
    wb.close()


# ----------------------------------------------------------------------------- fixture: known expected results
def test_fixture_expected_cleaning_results(fixture_run):
    c = fixture_run["clean"].set_index("restaurant_id")
    assert len(c) == 14                                         # 16 - 1 exact dup - 1 dup ID
    assert c.loc[900001, "restaurant_name"] == "TEST Synthetic 01"  # first copy kept
    assert pd.isna(c.loc[900004, "longitude"]) and c.loc[900004, "has_valid_coords"] == 0
    assert c.loc[900004, "has_online_delivery"] == 1             # lowercase 'yes'
    assert c.loc[900004, "is_rated"] == 0 and pd.isna(c.loc[900004, "popularity_class"])
    assert pd.isna(c.loc[900005, "avg_cost_for_two"])
    assert c.loc[900006, "cuisines"] == "Unknown" and c.loc[900006, "n_cuisines"] == 0
    assert c.loc[900011, "country"] == "Philippines"
    assert c.loc[900011, "currency"] == "Philippine Peso(P)"
    assert c.loc[900013, "country"] == "Unknown"
    assert c.loc[900014, "restaurant_name"] == "TEST Synthetic 14 extra spaces"
    assert c.loc[900014, "cuisines"] == "Mughlai, North Indian"


def test_fixture_kpis_match_clean_data(fixture_run):
    k, c = fixture_run["kpis"], fixture_run["clean"]
    assert k["restaurants"] == len(c)
    assert k["rated_restaurants"] == int(c["is_rated"].sum())
    assert k["total_votes"] == int(c["votes"].sum())
    assert k["unique_individual_cuisines"] == fixture_run["pairs"]["cuisine"].nunique()


def test_fixture_unknown_country_warning(fixture_run):
    assert any("not in the lookup" in w for w in fixture_run["warnings"])


def test_currency_spelling_fixed_and_logged():
    """Source typo 'Emirati Diram(AED)' is relabelled to 'Emirati Dirham (AED)' and the fix is in the cleaning log."""
    clean = pd.read_csv(config.PROCESSED_DIR / "zomato_clean.csv", encoding="utf-8")
    assert "Emirati Diram(AED)" not in set(clean["currency"])
    assert set(clean.loc[clean["country"] == "UAE", "currency"]) == {"Emirati Dirham (AED)"}
    log = pd.read_csv(config.PROCESSED_DIR / "cleaning_log.csv", encoding="utf-8")
    row = log[log["step"].str.contains("Emirati Dirham")]
    assert len(row) == 1 and row.iloc[0]["rows_affected"] == (clean["country"] == "UAE").sum()
