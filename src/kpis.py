"""Headline KPIs computed from whatever cleaned data is loaded (no fixed numbers)."""
from __future__ import annotations

import pandas as pd


def headline_kpis(clean: pd.DataFrame, pairs: pd.DataFrame | None = None) -> dict:
    n = len(clean)
    k = {
        "restaurants": n,
        "countries": int(clean["country"].nunique()),
        "cities": int(clean["city"].nunique()),
        "rated_restaurants": int(clean["is_rated"].sum()),
        "avg_rating_rated_only": round(float(clean["aggregate_rating"].mean()), 2)
        if clean["aggregate_rating"].notna().any() else None,
        "total_votes": int(clean["votes"].sum()),
        "online_delivery_pct": round(100 * float(clean["has_online_delivery"].mean()), 1),
        "table_booking_pct": round(100 * float(clean["has_table_booking"].mean()), 1),
        "unique_cuisine_combinations": int(clean.loc[clean["n_cuisines"] > 0, "cuisines"].nunique()),
    }
    if pairs is not None:
        k["unique_individual_cuisines"] = int(pairs["cuisine"].nunique())
    return k


def format_kpis(k: dict) -> str:
    labels = {
        "restaurants": "Restaurants", "countries": "Countries", "cities": "Cities",
        "rated_restaurants": "Rated restaurants", "avg_rating_rated_only": "Average rating (rated only)",
        "total_votes": "Total votes", "online_delivery_pct": "Online delivery %",
        "table_booking_pct": "Table booking %", "unique_cuisine_combinations": "Unique cuisine combinations",
        "unique_individual_cuisines": "Unique individual cuisines",
    }
    w = max(len(v) for v in labels.values())
    return "\n".join(f"  {labels[key]:<{w}} : {val:,}" if isinstance(val, int) else f"  {labels[key]:<{w}} : {val}"
                     for key, val in k.items())
