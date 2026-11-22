"""Phase 2 tests: MySQL schema and data, analytical queries, Python-MySQL link, EDA outputs.

Database tests are skipped (not failed) if MySQL is not reachable, e.g. on a machine without MySQL.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats
from sqlalchemy import text

from src import config
from src.db import DatabaseError, check_connection, get_engine, read_sql, split_statements
from src.eda import FIG_DIR, STATS_CSV
from src.sql_runner import SQL_RESULTS_DIR, SQL_RESULTS_MD, parse_queries

P = config.DEFAULT_PATHS
EXPECTED_TABLES = {"countries", "restaurants", "restaurant_cuisines"}
EXPECTED_VIEWS = {"v_restaurants", "v_restaurant_branches", "v_country_summary", "v_city_summary",
                  "v_locality_summary", "v_cuisine_summary", "v_price_summary"}


@pytest.fixture(scope="module")
def engine():
    try:
        eng = get_engine()
        check_connection(eng)
    except DatabaseError as e:
        pytest.skip(f"MySQL not available: {e}")
    return eng


@pytest.fixture(scope="module")
def clean():
    return pd.read_csv(P.clean_csv)


@pytest.fixture(scope="module")
def pairs():
    return pd.read_csv(P.cuisines_csv)


def scalar(engine, sql):
    with engine.connect() as cn:
        return cn.execute(text(sql)).scalar()


# ---------------------------------------------------------------- no database needed
def test_split_statements_ignores_comments():
    sql = "-- header; with semicolon\nCREATE TABLE a (x INT);\n\n-- only a comment\nSELECT 1;\n"
    stmts = split_statements(sql)
    assert len(stmts) == 2 and stmts[1].endswith("SELECT 1")


def test_query_file_has_20_to_30_unique_queries():
    qs = parse_queries()
    assert 20 <= len(qs) <= 30
    ids = [q.qid for q in qs]
    assert len(set(ids)) == len(ids)
    assert all(q.question and q.sql.upper().lstrip().startswith(("SELECT", "WITH")) for q in qs)


def test_env_file_is_git_ignored():
    assert ".env" in (config.ROOT / ".gitignore").read_text().splitlines()


# ---------------------------------------------------------------- schema and data
def test_tables_and_views_exist(engine):
    rows = read_sql(engine, "SELECT table_name AS t, table_type AS k FROM information_schema.tables "
                            "WHERE table_schema = DATABASE()")
    tables = set(rows.loc[rows["k"] == "BASE TABLE", "t"])
    views = set(rows.loc[rows["k"] == "VIEW", "t"])
    assert EXPECTED_TABLES <= tables
    assert EXPECTED_VIEWS <= views


def test_row_counts_match_clean_files(engine, clean, pairs):
    assert scalar(engine, "SELECT COUNT(*) FROM restaurants") == len(clean)
    assert scalar(engine, "SELECT COUNT(*) FROM restaurant_cuisines") == len(pairs)
    assert scalar(engine, "SELECT COUNT(*) FROM countries") == clean["country_code"].nunique()


def test_no_duplicate_ids_and_valid_ranges(engine):
    assert scalar(engine, "SELECT COUNT(*) - COUNT(DISTINCT restaurant_id) FROM restaurants") == 0
    assert scalar(engine, "SELECT COUNT(*) FROM restaurants WHERE aggregate_rating NOT BETWEEN 0 AND 5") == 0
    assert scalar(engine, "SELECT COUNT(*) FROM restaurants WHERE price_range NOT BETWEEN 1 AND 4") == 0
    assert scalar(engine, "SELECT COUNT(*) FROM restaurants WHERE "
                          "(is_rated = 1) <> (popularity_class IS NOT NULL)") == 0


def test_referential_integrity(engine):
    assert scalar(engine, "SELECT COUNT(*) FROM restaurant_cuisines rc LEFT JOIN restaurants r "
                          "USING (restaurant_id) WHERE r.restaurant_id IS NULL") == 0
    assert scalar(engine, "SELECT COUNT(*) FROM restaurants r LEFT JOIN countries c "
                          "USING (country_code) WHERE c.country_code IS NULL") == 0


@pytest.mark.parametrize("bad_sql", [
    "UPDATE restaurants SET aggregate_rating = 6 WHERE is_rated = 1 LIMIT 1",
    "UPDATE restaurants SET price_range = 9 LIMIT 1",
    "UPDATE restaurants SET country_code = 9999 LIMIT 1",
    "UPDATE restaurants SET popularity_class = NULL WHERE is_rated = 1 LIMIT 1",
])
def test_database_rejects_invalid_data(engine, bad_sql):
    """CHECK and FOREIGN KEY constraints must block bad data (changes are rolled back)."""
    with engine.connect() as cn:
        trans = cn.begin()
        with pytest.raises(Exception):
            cn.execute(text(bad_sql))
        trans.rollback()


# ---------------------------------------------------------------- SQL results agree with pandas
def test_sql_aggregates_match_pandas(engine, clean, pairs):
    kpi = read_sql(engine, parse_queries()[0].sql).iloc[0]
    assert kpi["restaurants"] == len(clean)
    assert kpi["total_votes"] == clean["votes"].sum()
    assert float(kpi["avg_rating_rated_only"]) == pytest.approx(clean["aggregate_rating"].mean(), abs=0.005)
    assert float(kpi["online_delivery_pct"]) == pytest.approx(100 * clean["has_online_delivery"].mean(), abs=0.05)
    top = read_sql(engine, "SELECT cuisine, restaurants FROM v_cuisine_summary ORDER BY restaurants DESC LIMIT 5")
    expected = pairs["cuisine"].value_counts().head(5)
    assert dict(zip(top["cuisine"], top["restaurants"])) == expected.to_dict()


def test_every_query_runs_and_returns_rows(engine):
    for q in parse_queries():
        df = read_sql(engine, q.sql)
        assert len(df) > 0, f"{q.qid} returned no rows"


def test_every_sql_technique_is_covered(engine):
    from src.sql_runner import TECHNIQUES, technique_matrix
    m = technique_matrix(engine)
    missing = [t for t in TECHNIQUES if not m[t].any()]
    assert not missing, f"Techniques not used by any query: {missing}"


def test_sql_result_files_written():
    for q in parse_queries():
        assert (SQL_RESULTS_DIR / f"{q.qid}_{q.name}.csv").exists(), q.qid
    md = SQL_RESULTS_MD.read_text(encoding="utf-8")
    assert all(f"## {q.qid}." in md for q in parse_queries())


# ---------------------------------------------------------------- EDA outputs
def test_eda_figures_exist():
    figs = sorted(FIG_DIR.glob("fig*.png"))
    assert len(figs) >= 10
    assert all(f.stat().st_size > 10_000 for f in figs)


def test_eda_statistics_are_valid_and_reproducible(clean):
    st = pd.read_csv(STATS_CSV)
    assert st["p_value"].between(0, 1).all()
    row = st[st["question"] == "Is price range associated with rating?"].iloc[0]
    rated = clean[clean["is_rated"] == 1]
    rho = stats.spearmanr(rated["price_range"], rated["aggregate_rating"])[0]
    assert row["statistic"] == pytest.approx(rho, abs=0.001)  # MySQL data == CSV data


def test_eda_never_uses_unrated_ratings(clean):
    """Unrated restaurants must have no rating, so rating statistics cover rated restaurants only."""
    assert clean.loc[clean["is_rated"] == 0, "aggregate_rating"].isna().all()
    assert np.isfinite(clean.loc[clean["is_rated"] == 1, "aggregate_rating"]).all()
