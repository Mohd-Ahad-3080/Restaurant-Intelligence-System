"""Leakage-free features for the popularity model (target Option B: within-country thirds of votes).

The target is built from votes, so votes, aggregate_rating, rating_text, rating_color, is_rated,
votes_pct_in_country and anything derived from them are FORBIDDEN. `assert_no_leakage` enforces this.

Count-type features (branch_count, locality_size) count restaurants (rows), never votes or ratings.
cost_pct_in_country ranks cost within each country+currency over all restaurants; it uses only
the cost column (no target information).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.target import FORBIDDEN_FEATURES

TOP_CUISINES = 20
MIN_CITY_ROWS = 30  # cities with fewer restaurants are grouped as "Other"

NUMERIC = ["price_range", "cost_pct_in_country", "is_cost_outlier", "has_table_booking", "has_online_delivery",
           "is_delivering_now", "n_cuisines", "log_branch_count", "log_locality_size", "latitude", "longitude",
           "has_valid_coords"]
CATEGORICAL = ["country", "city_group"]
FORBIDDEN_WORDS = ("vote", "rating", "rated", "popularity")


def assert_no_leakage(columns) -> None:
    bad = [c for c in columns
           if c in FORBIDDEN_FEATURES or any(w in str(c).lower() for w in FORBIDDEN_WORDS)]
    if bad:
        raise ValueError(f"Leakage: forbidden feature(s) present: {bad}")


def top_cuisines(pairs: pd.DataFrame, n: int = TOP_CUISINES) -> list[str]:
    return pairs["cuisine"].value_counts().head(n).index.tolist()


def build_features(clean: pd.DataFrame, pairs: pd.DataFrame, cuisines: list[str] | None = None) -> pd.DataFrame:
    """Return one feature row per restaurant (index = restaurant_id), for ALL restaurants.

    `cuisines`: the cuisine flags to build. Default = the TOP_CUISINES most common in `pairs` (training).
    When scoring new data, pass the saved model's cuisine list so the columns match the model exactly.
    """
    df = clean.set_index("restaurant_id")
    X = pd.DataFrame(index=df.index)
    X["country"] = df["country"]
    city_n = df["city"].map(df["city"].value_counts())
    X["city_group"] = np.where(city_n >= MIN_CITY_ROWS, df["city"], "Other")
    X["price_range"] = df["price_range"]
    X["cost_pct_in_country"] = df.groupby(["country", "currency"])["avg_cost_for_two"].rank(pct=True)
    for c in ["is_cost_outlier", "has_table_booking", "has_online_delivery", "is_delivering_now", "n_cuisines",
              "latitude", "longitude", "has_valid_coords"]:
        X[c] = df[c]
    X["log_branch_count"] = np.log1p(df["restaurant_name"].map(df["restaurant_name"].value_counts()))
    loc_key = df["city"].astype(str) + "|" + df["locality"].astype(str)
    X["log_locality_size"] = np.log1p(loc_key.map(loc_key.value_counts()))

    tops = top_cuisines(pairs) if cuisines is None else list(cuisines)
    hot = (pairs[pairs["cuisine"].isin(tops)].assign(v=1)
           .pivot_table(index="restaurant_id", columns="cuisine", values="v", fill_value=0))
    hot = hot.reindex(index=X.index, columns=tops, fill_value=0)
    hot.columns = ["cuisine_" + c.lower().replace(" ", "_") for c in hot.columns]
    X = X.join(hot)
    assert_no_leakage(X.columns)
    return X


def cuisine_columns(X: pd.DataFrame) -> list[str]:
    return [c for c in X.columns if c.startswith("cuisine_")]
