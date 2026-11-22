"""Cost in USD: rate table from the stored World Bank file, conversion rule (unit), clean data (real outputs)."""
import pandas as pd
import pytest

from src import config
from src.currency import COUNTRY_CODES, add_cost_usd, load_rates


def test_rates_cover_every_country_and_are_positive():
    r = load_rates()
    assert set(r["country"]) == set(COUNTRY_CODES)
    assert (r["lcu_per_usd"] > 0).all()
    assert r.set_index("country").loc["United States", "lcu_per_usd"] == 1.0
    assert (r["year"] == 2017).all() and r["source"].str.contains("World Bank").all()


def test_conversion_rule_on_synthetic_rows():
    """SYNTHETIC rows and a made-up rate: 100 local units at 50 per US$ = 2.00 US$; unknown country -> blank."""
    rates = pd.DataFrame({"country": ["Testland"], "lcu_per_usd": [50.0]})
    df = pd.DataFrame({"country": ["Testland", "Nowhere"], "avg_cost_for_two": [100.0, 100.0]})
    out = add_cost_usd(df, rates)
    assert out.loc[0, "avg_cost_for_two_usd"] == 2.0
    assert pd.isna(out.loc[1, "avg_cost_for_two_usd"])


def test_clean_data_has_usd_for_every_cost():
    clean = pd.read_csv(config.PROCESSED_DIR / "zomato_clean.csv")
    assert "avg_cost_for_two_usd" in clean.columns
    has_cost = clean["avg_cost_for_two"].notna()
    assert clean.loc[has_cost, "avg_cost_for_two_usd"].notna().all()
    assert clean.loc[~has_cost, "avg_cost_for_two_usd"].isna().all()
    rate = clean["country"].map(load_rates().set_index("country")["lcu_per_usd"])
    diff = (clean["avg_cost_for_two"] / rate - clean["avg_cost_for_two_usd"]).abs()
    assert diff[has_cost].max() <= 0.005 + 1e-9


def test_currency_doc_written():
    doc = config.DOCS_DIR / "currency_and_costs.md"
    if not doc.exists():
        pytest.skip("Run `python run_pipeline.py` first")
    text = doc.read_text(encoding="utf-8")
    assert "approximate" in text.lower() and "PA.NUS.FCRF" in text
