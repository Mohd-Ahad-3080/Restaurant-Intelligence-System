"""Python <-> MySQL link: connection, running SQL files, loading the cleaned data.

Credentials are read from .env (git-ignored); see .env.example.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine

from src import config

SCHEMA_SQL = config.SQL_DIR / "01_schema.sql"
VIEWS_SQL = config.SQL_DIR / "02_views.sql"
QUERIES_SQL = config.SQL_DIR / "03_analysis_queries.sql"

RESTAURANT_COLUMNS = [
    "restaurant_id", "restaurant_name", "country_code", "city", "address", "locality", "locality_verbose",
    "longitude", "latitude", "has_valid_coords", "cuisines", "n_cuisines", "avg_cost_for_two", "avg_cost_for_two_usd", "currency",
    "is_cost_outlier", "has_table_booking", "has_online_delivery", "is_delivering_now",
    "switch_to_order_menu", "price_range", "aggregate_rating", "rating_color", "rating_text", "votes",
    "is_rated", "votes_pct_in_country", "popularity_class",
]


class DatabaseError(RuntimeError):
    pass


def get_engine(env_file: Path = config.ROOT / ".env") -> Engine:
    load_dotenv(env_file)
    missing = [k for k in ("MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DB") if not os.getenv(k)]
    if missing:
        raise DatabaseError(f"Missing {', '.join(missing)} in .env (copy .env.example to .env and fill it in).")
    url = URL.create(
        "mysql+mysqlconnector",
        username=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=os.getenv("MYSQL_DB"),
        query={"charset": "utf8mb4"},
    )
    return create_engine(url, pool_pre_ping=True)


def check_connection(engine: Engine) -> str:
    try:
        with engine.connect() as cn:
            return cn.execute(text("SELECT VERSION()")).scalar()
    except Exception as e:  # noqa: BLE001 - turn any driver error into a readable message
        raise DatabaseError(
            "Cannot connect to MySQL. Is the MySQL server running (Windows: service MySQL84; Mac: System Settings > "
            "MySQL > Start) and are the .env credentials right? First-time setup: "
            "sql/00_create_database_and_user.sql\n"
            f"Details: {e}") from None


def split_statements(sql: str) -> list[str]:
    """Split a SQL script on semicolons at line ends; drop comment-only chunks."""
    out = []
    for chunk in re.split(r";\s*(?:\n|$)", sql):
        body = "\n".join(l for l in chunk.splitlines() if not l.strip().startswith("--")).strip()
        if body:
            out.append(chunk.strip())
    return out


def run_sql_file(engine: Engine, path: Path) -> int:
    stmts = split_statements(Path(path).read_text(encoding="utf-8"))
    with engine.begin() as cn:
        for s in stmts:
            cn.execute(text(s))
    return len(stmts)


def load_clean_data(engine: Engine, clean: pd.DataFrame, pairs: pd.DataFrame) -> dict[str, int]:
    """(Re)create the schema and views, then insert countries, restaurants and cuisine pairs."""
    run_sql_file(engine, SCHEMA_SQL)
    countries = (clean[["country_code", "country"]].drop_duplicates()
                 .rename(columns={"country": "country_name"}).sort_values("country_code"))
    rest = clean[RESTAURANT_COLUMNS].copy()
    rest = rest.astype(object).where(rest.notna(), None)
    with engine.begin() as cn:
        countries.to_sql("countries", cn, if_exists="append", index=False)
        rest.to_sql("restaurants", cn, if_exists="append", index=False, chunksize=1000, method="multi")
        pairs[["restaurant_id", "cuisine"]].to_sql("restaurant_cuisines", cn, if_exists="append",
                                                    index=False, chunksize=2000, method="multi")
    run_sql_file(engine, VIEWS_SQL)
    with engine.connect() as cn:
        return {t: cn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                for t in ("countries", "restaurants", "restaurant_cuisines")}


def read_sql(engine: Engine, sql: str) -> pd.DataFrame:
    with engine.connect() as cn:
        return pd.read_sql(text(sql), cn)
