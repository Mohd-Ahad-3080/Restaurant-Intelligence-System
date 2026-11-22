"""Phase 4 tests: Power BI theme, data workbook and measures file."""
from __future__ import annotations

import json
import re

import pandas as pd
import pytest
from openpyxl import load_workbook

from src import config
from src.powerbi_export import PBI_DIR, PBI_XLSX, PRICE

THEME = PBI_DIR / "theme_b_slate_red.json"
DAX = PBI_DIR / "dax_measures.md"
GUIDE = PBI_DIR / "POWERBI_GUIDE.md"
P = config.DEFAULT_PATHS

# Theme B exactly as approved for the project (slate + brand red)
THEME_B = {"#1F2329", "#FFFFFF", "#CB202D", "#8E1520", "#E23744", "#E8838B", "#F5C6CA", "#F4F4F5",
           "#E4E4E7", "#18181B", "#5C5C66", "#EFEFF1"}
PRICE_SEQUENCE = ["#8E1520", "#CB202D", "#E8838B", "#F5C6CA"]
SHEETS = ["restaurants", "restaurant_cuisines", "model_comparison", "model_metrics_long", "confusion_matrix",
          "feature_importance", "predictions", "robustness_checks", "popularity_classes"]


def test_theme_is_valid_json_using_only_theme_b_colours():
    theme = json.loads(THEME.read_text(encoding="utf-8"))
    assert theme["name"] and theme["dataColors"]
    used = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}", THEME.read_text(encoding="utf-8"))}
    assert used <= THEME_B, f"Colours not in Theme B: {used - THEME_B}"
    assert theme["dataColors"][0].upper() == "#CB202D"  # primary accent first


def test_dashboard_generators_use_only_theme_b():
    """Power BI and Tableau generators and the India charts use only the approved Theme B colours."""
    from src import india, powerbi_pbip, tableau_twb
    pbi = {getattr(powerbi_pbip, k) for k in ("SLATE", "WHITE", "ACCENT", "HIGHLIGHT", "ACTIVE", "TEXT", "TEXT2",
                                               "BORDER", "PAGE_BG")}
    tab = {getattr(tableau_twb, k).upper() for k in ("SLATE", "WHITE", "ACCENT", "HIGHLIGHT", "ACTIVE", "LIGHT1",
                                                      "LIGHT2", "PAGE_BG", "BORDER", "TEXT", "TEXT2")}
    assert pbi <= THEME_B and tab <= THEME_B
    assert india.PRICE_COLOURS == PRICE_SEQUENCE


def test_price_colours_follow_approved_sequence():
    assert [PRICE[i][1] for i in (1, 2, 3, 4)] == PRICE_SEQUENCE


@pytest.fixture(scope="module")
def workbook():
    if not PBI_XLSX.exists():
        pytest.skip("Run `python run_pipeline.py` first")
    return {s: pd.read_excel(PBI_XLSX, sheet_name=s) for s in SHEETS}


def test_workbook_has_all_tables(workbook):
    wb = load_workbook(PBI_XLSX, read_only=True)
    assert wb.sheetnames == SHEETS
    wb.close()


def test_restaurants_table_matches_clean_data(workbook):
    clean = pd.read_csv(P.clean_csv)
    r = workbook["restaurants"]
    assert len(r) == len(clean) and not r["restaurant_id"].duplicated().any()
    assert r["aggregate_rating"].isna().sum() == (clean["is_rated"] == 0).sum()  # unrated stay blank
    assert r["votes"].sum() == clean["votes"].sum()
    assert set(r["price_color"].dropna()) <= set(PRICE_SEQUENCE)


def test_page4_tables_use_real_model_results(workbook):
    comp = pd.read_csv(config.PREDICTIONS_DIR / "model_comparison.csv")
    w = workbook["model_comparison"]
    assert w["is_best"].sum() == 1
    best = w[w["is_best"] == 1].iloc[0]
    assert best["test_accuracy"] == pytest.approx(comp.set_index("model").loc[best["model"], "test_accuracy"])
    assert len(workbook["predictions"]) == int(pd.read_csv(P.clean_csv)["is_rated"].sum())
    cm = workbook["confusion_matrix"]
    assert len(cm) == 9 and cm["count"].sum() == (workbook["predictions"]["split"] == "test").sum()


def test_guide_uses_only_defined_measures():
    defined = set(re.findall(r"`([A-Za-z][A-Za-z0-9 %()]+?) = ", DAX.read_text(encoding="utf-8")))
    guide = GUIDE.read_text(encoding="utf-8")
    used = set(re.findall(r"measure \*\*([^*]+)\*\*", guide))
    used |= {m for m in defined if f"**{m}**" in guide}
    assert used and used <= defined, f"Guide refers to undefined measures: {used - defined}"
