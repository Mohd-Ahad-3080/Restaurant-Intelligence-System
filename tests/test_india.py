"""India deep dive tables (outputs/india) recomputed independently from the cleaned data."""
import pandas as pd
import pytest

from src import config

OUT = config.ROOT / "outputs" / "india"


@pytest.fixture(scope="module")
def data():
    if not (OUT / "india_cities.csv").exists():
        pytest.skip("Run `python run_pipeline.py` first")
    clean = pd.read_csv(config.PROCESSED_DIR / "zomato_clean.csv")
    return clean[clean["country"] == "India"], {f.stem: pd.read_csv(f) for f in OUT.glob("*.csv")}


def test_city_table_covers_all_indian_restaurants(data):
    india, t = data
    c = t["india_cities"].set_index("city")
    assert c["restaurants"].sum() == len(india)
    assert set(c.index) == set(india["city"])
    nd = india[india["city"] == "New Delhi"]
    assert c.loc["New Delhi", "avg_rating"] == pytest.approx(nd["aggregate_rating"].mean())   # rated only
    rated = nd[nd["is_rated"] == 1]
    assert c.loc["New Delhi", "high_popularity_pct"] == pytest.approx(100 * (rated["popularity_class"] == "High").mean())
    assert c.loc["New Delhi", "avg_cost_usd"] == pytest.approx(nd["avg_cost_for_two_usd"].mean())


def test_price_mix_rows_sum_to_100(data):
    _, t = data
    m = t["india_price_mix_by_city"]
    pct = m[[c for c in m.columns if c.startswith("price_")]].fillna(0).sum(axis=1)
    assert (pct - 100).abs().max() < 1e-6


def test_cuisine_mix_only_big_cities(data):
    from src.india import BIG_CITY_MIN, TOP_CUISINES
    india, t = data
    cm = t["india_cuisine_mix_by_city"]
    assert (cm["restaurants_in_city"] >= BIG_CITY_MIN).all()
    assert cm.groupby("city")["rank"].max().le(TOP_CUISINES).all()


def test_india_doc_written():
    assert (config.DOCS_DIR / "india_deep_dive.md").exists()


def test_tableau_india_file_avoids_sql_reserved_column_names():
    """'primary' is a reserved word in Hyper SQL (the engine behind Tableau extracts); the India dashboard showed
    no data while the extract had a column with that name."""
    from src.india import TABLEAU_CSV
    cols = pd.read_csv(TABLEAU_CSV, nrows=1).columns.str.lower()
    assert not set(cols) & {"primary", "key", "order", "group", "select", "table", "user", "default"}


def test_services_insights_are_india_only():
    """Delivery exists only in India and the UAE, so F3/F4 use rated Indian restaurants (as the report does)."""
    f = pd.read_csv(OUT.parent / "insights" / "insights.csv").set_index("id")
    clean = pd.read_csv(config.PROCESSED_DIR / "zomato_clean.csv")
    r = clean[(clean["country"] == "India") & (clean["is_rated"] == 1)]
    d = r.groupby("has_online_delivery")["aggregate_rating"].mean()
    assert "India" in f.loc["F3", "finding"] and "India" in f.loc["F4", "finding"]
    assert f"{d[1]:.2f} vs {d[0]:.2f}" in f.loc["F4", "finding"]
