"""Popularity target (Option B: within-country thirds of votes).

popularity_class = within-country percentile rank of votes, cut into thirds,
computed among RATED restaurants only. Unrated restaurants get no class and are
excluded from model training.
"""
from __future__ import annotations

import pandas as pd

LABELS = ["Low", "Medium", "High"]

# One wording used everywhere (docs, dashboards, report) so the definition never drifts.
TARGET_DEFINITION = ("Popularity class = within-country tertiles (thirds) of votes among rated restaurants "
                     "(Low / Medium / High). Unrated restaurants have no class and are not used for training.")
EXCLUDED_FEATURES_NOTE = ("Votes, aggregate rating, rating text, rating colour and the rated flag are excluded "
                          "as model features because the target is built from votes; a model that uses them "
                          "is invalid (leaky).")

# Never use these as model features: they are the target or derived from it.
FORBIDDEN_FEATURES = ["votes", "aggregate_rating", "rating_text", "rating_color", "is_rated",
                      "popularity_class", "votes_pct_in_country"]


def add_popularity_class(df: pd.DataFrame) -> pd.DataFrame:
    """Add votes_pct_in_country and popularity_class columns (clean snake_case names)."""
    out = df.copy()
    eligible = out["is_rated"].eq(1) & out["votes"].notna()
    pct = out.loc[eligible].groupby("country")["votes"].rank(pct=True, method="average")
    out["votes_pct_in_country"] = pct  # NaN for unrated
    out["popularity_class"] = pd.cut(out["votes_pct_in_country"], [0, 1 / 3, 2 / 3, 1.0],
                                     labels=LABELS, include_lowest=True).astype("string")
    return out
