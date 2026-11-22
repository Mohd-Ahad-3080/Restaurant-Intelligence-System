"""India deep dive: city and locality analysis for Indian restaurants only (8,652 of 9,551 in the Kaggle file).

All numbers are computed here from data/processed/zomato_clean.csv and restaurant_cuisines.csv.
Rating and popularity use RATED restaurants only (unrated have no rating or class). Costs are shown in INR
(local) and as approximate US$ (World Bank 2017 rate, see docs/currency_and_costs.md).
Also writes the row-level files the Tableau 'India deep dive' dashboard reads.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import config
from src.eda import C, _save, _style

OUT_DIR = config.ROOT / "outputs" / "india"
DOC = config.DOCS_DIR / "india_deep_dive.md"
TABLEAU_CSV = config.PROCESSED_DIR / "tableau_india.csv"
BIG_CITY_MIN = 50          # cuisine mix: cities with at least this many restaurants
TOP_LOCALITIES = 20
TOP_CUISINES = 5
PRICE_COLOURS = ["#8E1520", "#CB202D", "#E8838B", "#F5C6CA"]   # approved Theme B price sequence, range 1 -> 4


def india(clean: pd.DataFrame) -> pd.DataFrame:
    d = clean[clean["country"] == "India"].copy()
    d["is_high"] = d["popularity_class"].eq("High").fillna(False).astype(int)   # unrated: NA -> 0
    return d


def group_summary(d: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    r = d[d["is_rated"] == 1]
    base = d.groupby(by).agg(restaurants=("restaurant_id", "size"),
                             online_delivery_pct=("has_online_delivery", lambda s: 100 * s.mean()),
                             table_booking_pct=("has_table_booking", lambda s: 100 * s.mean()),
                             avg_cost_inr=("avg_cost_for_two", "mean"), median_cost_inr=("avg_cost_for_two", "median"),
                             avg_cost_usd=("avg_cost_for_two_usd", "mean"),
                             median_cost_usd=("avg_cost_for_two_usd", "median"),
                             avg_price_range=("price_range", "mean"))
    rr = r.groupby(by).agg(rated=("restaurant_id", "size"), avg_rating=("aggregate_rating", "mean"),
                           median_votes=("votes", "median"), high_popularity_pct=("is_high", lambda s: 100 * s.mean()))
    out = base.join(rr, how="left")
    out["rated"] = out["rated"].fillna(0).astype(int)
    if by == ["city"]:
        out = out.join(d.groupby("city")["locality"].nunique().rename("localities"))
    cols = ["restaurants", "rated"] + (["localities"] if by == ["city"] else []) + [
        "avg_rating", "median_votes", "high_popularity_pct", "online_delivery_pct", "table_booking_pct",
        "avg_price_range", "avg_cost_inr", "median_cost_inr", "avg_cost_usd", "median_cost_usd"]
    # ties (many cities have exactly 20-21 restaurants) broken by name, so every run gives the same order
    return out[cols].reset_index().sort_values(["restaurants", *by], ascending=[False] + [True] * len(by)) \
        .reset_index(drop=True)


def price_mix(d: pd.DataFrame) -> pd.DataFrame:
    t = pd.crosstab(d["city"], d["price_range"], normalize="index") * 100
    t.columns = [f"price_{int(c)}_pct" for c in t.columns]
    return t.join(d["city"].value_counts().rename("restaurants")).reset_index() \
        .sort_values(["restaurants", "city"], ascending=[False, True]).reset_index(drop=True)


def cuisine_mix(d: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    sizes = d["city"].value_counts()
    big = sizes[sizes >= BIG_CITY_MIN].index
    p = pairs.merge(d[["restaurant_id", "city"]], on="restaurant_id")
    p = p[p["city"].isin(big)]
    rows = []
    for city, g in p.groupby("city"):
        vc = g["cuisine"].value_counts().head(TOP_CUISINES)
        for rank, (cuisine, n) in enumerate(vc.items(), start=1):
            rows.append({"city": city, "restaurants_in_city": int(sizes[city]), "rank": rank, "cuisine": cuisine,
                         "restaurants_offering": int(n), "share_pct": 100 * n / sizes[city]})
    return pd.DataFrame(rows).sort_values(["restaurants_in_city", "rank"], ascending=[False, True])


def tableau_rows(d: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    """Row-level file for Tableau: one row per restaurant-cuisine pair (restaurants without a cuisine keep one
    row with an empty cuisine). `is_primary_row` = 1 on exactly one row per restaurant, so restaurant-level measures
    count each restaurant once."""
    labels = {1: "1 Budget", 2: "2 Moderate", 3: "3 Expensive", 4: "4 Luxury"}
    base = d[["restaurant_id", "city", "locality", "price_range", "has_online_delivery", "has_table_booking",
              "aggregate_rating", "votes", "is_rated", "is_high", "avg_cost_for_two", "avg_cost_for_two_usd"]].copy()
    base["locality_city"] = d["locality"].astype(str) + " (" + d["city"].astype(str) + ")"
    base["price_label"] = d["price_range"].map(labels)
    out = base.merge(pairs[["restaurant_id", "cuisine"]], on="restaurant_id", how="left")
    out = out.sort_values(["restaurant_id", "cuisine"], na_position="last").reset_index(drop=True)
    out["is_primary_row"] = (~out["restaurant_id"].duplicated()).astype(int)
    cols = ["restaurant_id", "is_primary_row", "city", "locality", "locality_city", "cuisine", "price_range", "price_label",
            "has_online_delivery", "has_table_booking", "aggregate_rating", "votes", "is_rated", "is_high",
            "avg_cost_for_two", "avg_cost_for_two_usd"]
    out[cols].to_csv(TABLEAU_CSV, index=False, encoding="utf-8")
    return out[cols]


# ------------------------------------------------------------------ figures
def plot_cities(cities: pd.DataFrame, top: int = 12) -> Path:
    _style()
    c = cities.head(top).iloc[::-1]
    fig, (a1, a2, a3) = plt.subplots(1, 3, figsize=(13, 5), sharey=True)
    y = np.arange(len(c))
    a1.barh(y, c["restaurants"], color=C["accent"])
    for yy, v in zip(y, c["restaurants"]):
        a1.text(v, yy, f" {v:,}", va="center", fontsize=8, color=C["text2"])
    a1.set_xscale("log")
    a1.set_title("Restaurants (log scale)")
    a2.barh(y, c["avg_rating"], color=C["highlight"])
    for yy, v in zip(y, c["avg_rating"]):
        a2.text(v, yy, f" {v:.2f}", va="center", fontsize=8, color=C["text2"])
    a2.set_xlim(0, 5)
    a2.set_title("Average rating (rated only)")
    a3.barh(y, c["high_popularity_pct"], color=C["light1"])
    for yy, v in zip(y, c["high_popularity_pct"]):
        a3.text(v, yy, f" {v:.0f}%", va="center", fontsize=8, color=C["text2"])
    a3.set_xlim(0, 105)
    a3.set_title("High-popularity share (rated only)")
    a1.set_yticks(y, c["city"])
    for a in (a1, a2, a3):
        a.grid(axis="y", visible=False)
    fig.suptitle(f"India: the {top} cities with the most restaurants", fontsize=11)
    return _save(fig, "fig21_india_cities")


def plot_mix(mix: pd.DataFrame, cities: pd.DataFrame, top: int = 10) -> Path:
    _style()
    m = mix.head(top).set_index("city").iloc[::-1]
    c = cities.set_index("city").loc[m.index]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 4.8), sharey=True)
    y, left = np.arange(len(m)), np.zeros(len(m))
    for i, col in enumerate([f"price_{k}_pct" for k in range(1, 5)]):
        vals = m[col].fillna(0) if col in m else np.zeros(len(m))
        a1.barh(y, vals, left=left, color=PRICE_COLOURS[i], label=f"Price range {i + 1}")
        left += vals
    a1.set_xlim(0, 100)
    a1.set_title("Price range mix (% of restaurants)")
    a1.legend(ncol=4, fontsize=7, loc="lower center", bbox_to_anchor=(0.5, -0.22))
    w = 0.38
    a2.barh(y + w / 2, c["online_delivery_pct"], w, color=C["accent"], label="Online delivery")
    a2.barh(y - w / 2, c["table_booking_pct"], w, color=C["text2"], label="Table booking")
    a2.set_xlim(0, 100)
    a2.set_title("Services (% of restaurants)")
    a2.legend(fontsize=7, loc="lower right")
    a1.set_yticks(y, m.index)
    for a in (a1, a2):
        a.grid(axis="y", visible=False)
    fig.suptitle(f"India: price mix and services in the {top} largest cities", fontsize=11)
    return _save(fig, "fig22_india_price_services")


# ------------------------------------------------------------------ doc
def write_doc(d, cities, locs, mix, cuis, figs) -> None:
    ncr =["New Delhi", "Gurgaon", "Noida", "Faridabad", "Ghaziabad"]
    ncr_share = d["city"].isin(ncr).mean()
    L = ["# India Deep Dive", "",
         "*Generated by `src/india.py` from the cleaned Kaggle data. Rating and popularity use rated restaurants "
         "only; costs in INR and approximate US$ (World Bank 2017 rate).*", "",
         f"India: **{len(d):,} restaurants** in **{d['city'].nunique()} cities** and "
         f"**{d.groupby(['city', 'locality']).ngroups:,} city-locality pairs**; {int(d['is_rated'].sum()):,} rated. "
         f"Delhi NCR (New Delhi, Gurgaon, Noida, Faridabad, Ghaziabad) holds {100 * ncr_share:.1f}% of them.", "",
         "Sampling caveat: outside Delhi NCR the file lists only about 20 restaurants per city, and these tend to be "
         "well-known ones (see median votes), so city comparisons outside NCR describe a selected sample.", "",
         "## Cities (all Indian cities, by number of restaurants)", "",
         "| city | restaurants | rated | localities | avg rating | median votes | High % | delivery % | "
         "booking % | avg price range | Average cost for two (INR) | Average cost for two (US$, approx.) |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in cities.itertuples(index=False):
        L.append(f"| {r.city} | {r.restaurants:,} | {r.rated:,} | {r.localities} | {r.avg_rating:.2f} | "
                 f"{r.median_votes:,.0f} | {r.high_popularity_pct:.1f} | {r.online_delivery_pct:.1f} | "
                 f"{r.table_booking_pct:.1f} | {r.avg_price_range:.2f} | {r.avg_cost_inr:,.0f} | {r.avg_cost_usd:.2f} |")
    L += ["", f"## Top {TOP_LOCALITIES} localities (by number of restaurants)", "",
          "| city | locality | restaurants | rated | avg rating | High % | delivery % | booking % | Average cost for two "
          "(INR) | Average cost for two (US$, approx.) |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in locs.head(TOP_LOCALITIES).itertuples(index=False):
        L.append(f"| {r.city} | {r.locality} | {r.restaurants:,} | {r.rated:,} | {r.avg_rating:.2f} | "
                 f"{r.high_popularity_pct:.1f} | {r.online_delivery_pct:.1f} | {r.table_booking_pct:.1f} | "
                 f"{r.avg_cost_inr:,.0f} | {r.avg_cost_usd:.2f} |")
    L += ["", f"## Price range mix by city (cities with {BIG_CITY_MIN}+ restaurants, % of restaurants)", "",
          "| city | restaurants | range 1 | range 2 | range 3 | range 4 |", "|---|---|---|---|---|---|"]
    for r in mix[mix["restaurants"] >= BIG_CITY_MIN].itertuples(index=False):
        L.append(f"| {r.city} | {r.restaurants:,} | " + " | ".join(
            f"{getattr(r, f'price_{k}_pct', 0):.1f}" for k in range(1, 5)) + " |")
    L += ["", f"## Cuisine mix by city (top {TOP_CUISINES} cuisines, % of the city's restaurants offering it)", "",
          "| city | rank | cuisine | restaurants offering | share % |", "|---|---|---|---|---|"]
    L += [f"| {r.city} | {r.rank} | {r.cuisine} | {r.restaurants_offering:,} | {r.share_pct:.1f} |"
          for r in cuis.itertuples(index=False)]
    L += ["", "## Figures", ""] + [f"- `{p.relative_to(config.ROOT).as_posix()}`" for p in figs] + [""]
    DOC.write_text("\n".join(L), encoding="utf-8")


def run_india(clean: pd.DataFrame, pairs: pd.DataFrame) -> dict:
    d = india(clean)
    cities = group_summary(d, ["city"])
    locs = group_summary(d, ["city", "locality"])
    mix = price_mix(d)
    cuis = cuisine_mix(d, pairs)
    rows = tableau_rows(d, pairs)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cities.to_csv(OUT_DIR / "india_cities.csv", index=False)
    locs.to_csv(OUT_DIR / "india_localities.csv", index=False)
    mix.to_csv(OUT_DIR / "india_price_mix_by_city.csv", index=False)
    cuis.to_csv(OUT_DIR / "india_cuisine_mix_by_city.csv", index=False)
    figs = [plot_cities(cities), plot_mix(mix, cities)]
    write_doc(d, cities, locs, mix, cuis, figs)
    return {"cities": cities, "localities": locs, "price_mix": mix, "cuisine_mix": cuis, "tableau_rows": rows,
            "figures": figs}
