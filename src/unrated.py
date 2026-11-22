"""Unrated restaurants (aggregate rating 0 / "Not rated" in the raw file): how they are treated everywhere,
how their profile differs from rated restaurants, and what the saved model predicts for them.

The saved model uses no votes and no rating, so it can score unrated restaurants. Their predictions cannot be
checked (they have no popularity class), so they are reported as a distribution only, never as accuracy.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

from src import config
from src.eda import C, _save, _style
from src.features import assert_no_leakage, build_features
from src.target import LABELS

OUT_DIR = config.ROOT / "outputs" / "unrated"
DOC = config.DOCS_DIR / "unrated_restaurants.md"
GROUP = {1: "Rated", 0: "Unrated"}


def _pct_table(d: pd.DataFrame, col: str) -> pd.DataFrame:
    t = pd.crosstab(d[col], d["is_rated"].map(GROUP), normalize="columns") * 100
    return t.reindex(columns=["Rated", "Unrated"]).fillna(0)


def profile(clean: pd.DataFrame) -> dict:
    d = clean.copy()
    d["group"] = d["is_rated"].map(GROUP)
    d["india"] = np.where(d["country"] == "India", "India", "Outside India")
    d["is_chain"] = (d["restaurant_name"].map(d["restaurant_name"].value_counts()) > 1).astype(int)
    d["cost_pct_in_country"] = d.groupby(["country", "currency"])["avg_cost_for_two"].rank(pct=True)

    by_country = (d.groupby("country").agg(restaurants=("is_rated", "size"), rated=("is_rated", "sum"))
                  .assign(unrated=lambda t: t["restaurants"] - t["rated"])
                  .assign(unrated_pct=lambda t: 100 * t["unrated"] / t["restaurants"],
                          share_of_all_unrated_pct=lambda t: 100 * t["unrated"] / t["unrated"].sum())
                  .sort_values("unrated", ascending=False).reset_index())
    by_city = (d.groupby(["country", "city"]).agg(restaurants=("is_rated", "size"), rated=("is_rated", "sum"))
               .assign(unrated=lambda t: t["restaurants"] - t["rated"])
               .assign(unrated_pct=lambda t: 100 * t["unrated"] / t["restaurants"],
                       share_of_all_unrated_pct=lambda t: 100 * t["unrated"] / t["unrated"].sum())
               .sort_values("unrated", ascending=False).head(10).reset_index())
    price = _pct_table(d, "price_range").rename_axis("price_range").reset_index()
    services = (d.groupby("group").agg(restaurants=("is_rated", "size"),
                                       online_delivery_pct=("has_online_delivery", lambda s: 100 * s.mean()),
                                       table_booking_pct=("has_table_booking", lambda s: 100 * s.mean()),
                                       delivering_now_pct=("is_delivering_now", lambda s: 100 * s.mean()),
                                       in_india_pct=("india", lambda s: 100 * (s == "India").mean()),
                                       chain_pct=("is_chain", lambda s: 100 * s.mean()),
                                       median_cost_pct_in_country=("cost_pct_in_country", "median"),
                                       mean_cuisines_listed=("n_cuisines", "mean"),
                                       median_votes=("votes", "median"), max_votes=("votes", "max"))
                .reindex(["Rated", "Unrated"]).rename_axis("group").reset_index())
    tests = []
    for col, label in [("price_range", "Price range (1-4)"), ("has_online_delivery", "Online delivery"),
                       ("has_table_booking", "Table booking"), ("india", "India vs outside India"),
                       ("is_chain", "Chain (same name 2+ times)")]:
        chi2, p, dof, _ = chi2_contingency(pd.crosstab(d[col], d["group"]))
        tests.append({"variable": label, "chi2": chi2, "dof": dof, "p_value": p})
    return {"by_country": by_country, "by_city": by_city, "price_range": price, "services": services,
            "tests": pd.DataFrame(tests)}


def predict_unrated(clean: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    """Saved model's predictions for unrated restaurants (no actual class exists, so no accuracy)."""
    meta = json.loads((config.MODELS_DIR / "popularity_model_meta.json").read_text(encoding="utf-8"))
    assert_no_leakage(meta["features"])
    model = joblib.load(config.MODELS_DIR / "popularity_model.joblib")
    cuisines = sorted({c for c in pairs["cuisine"].unique()
                       if "cuisine_" + c.lower().replace(" ", "_") in meta["features"]})
    X = build_features(clean, pairs, cuisines=cuisines)[meta["features"]]
    ids = clean.loc[clean["is_rated"] == 0, "restaurant_id"]
    Xu = X.loc[X.index.isin(ids)]
    proba = pd.DataFrame(model.predict_proba(Xu), index=Xu.index, columns=model.classes_)[LABELS]
    info = clean.set_index("restaurant_id").loc[Xu.index, ["restaurant_name", "country", "city", "locality",
                                                            "price_range", "has_online_delivery",
                                                            "has_table_booking"]]
    out = info.join(proba.rename(columns={"Low": "prob_low", "Medium": "prob_medium", "High": "prob_high"}))
    out["predicted_class"] = proba.idxmax(axis=1)
    out["actual_class"] = "none (unrated)"
    out["model"] = meta["best_model"]
    return out.reset_index()


def treatment(clean: pd.DataFrame, preds: pd.DataFrame) -> pd.DataFrame:
    """How unrated restaurants are handled in each part of the project, with the numbers that show it."""
    n, u = len(clean), int((clean["is_rated"] == 0).sum())
    rated_avg = clean["aggregate_rating"].mean()
    zero_avg = clean["aggregate_rating"].fillna(0).mean()
    u_votes = int(clean.loc[clean["is_rated"] == 0, "votes"].sum())
    split = preds["predicted_class"].value_counts().reindex(LABELS, fill_value=0)
    rows = [
        ("Cleaning", "Raw rating 0 with 'Not rated' is treated as missing (blank), not as a real 0; flag "
                     "is_rated = 0.", f"{u:,} of {n:,} restaurants ({100 * u / n:.1f}%)"),
        ("KPIs: counts", "Restaurant, city, delivery and booking counts include unrated restaurants.",
         f"Restaurants KPI = {n:,}"),
        ("KPIs: average rating", "Average rating uses rated restaurants only.",
         f"{rated_avg:.2f} (rated only); it would be a misleading {zero_avg:.2f} if the zeros were counted"),
        ("KPIs: total votes", "Total votes includes the few votes unrated restaurants have.",
         f"Unrated restaurants hold {u_votes:,} votes in total (max {int(clean.loc[clean['is_rated'] == 0, 'votes'].max())} each)"),
        ("MySQL", "aggregate_rating is stored as NULL, so AVG() skips unrated rows; is_rated column; a CHECK "
                  "constraint keeps popularity_class NULL exactly when is_rated = 0; query Q24 shows the unrated "
                  "share by city.", "sql/01_schema.sql, sql/03_analysis_queries.sql"),
        ("Power BI", "Measures 'Rated Restaurants' and 'Unrated %'; Avg Rating is blank for unrated rows; the rating "
                     "distribution shows 'Not rated' as a separate grey bar.", "dashboards/powerbi/dax_measures.md"),
        ("Tableau", "Rating fields stay empty for unrated restaurants, so averages use rated restaurants only.",
         "dashboards/tableau/TABLEAU_GUIDE.md"),
        ("Model training", "Excluded: they have no popularity class (the target needs a rating and votes).",
         f"Training and test use {n - u:,} rated restaurants"),
        ("Model predictions", "The saved model uses no votes or rating, so it can still predict for unrated "
                              "restaurants. These predictions cannot be checked (no actual class).",
         f"Predicted for {len(preds):,}: " + ", ".join(f"{c} {split[c]:,} ({100 * split[c] / len(preds):.1f}%)"
                                                      for c in LABELS)),
    ]
    return pd.DataFrame(rows, columns=["area", "rule", "evidence"])


def plot_profile(p: dict) -> Path:
    _style()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.4))
    pr = p["price_range"].set_index("price_range")
    x, w = np.arange(len(pr)), 0.38
    for i, (g, col) in enumerate([("Rated", C["accent"]), ("Unrated", C["text2"])]):
        bars = a1.bar(x + (i - 0.5) * w, pr[g], w, label=g, color=col)
        for b, v in zip(bars, pr[g]):
            a1.text(b.get_x() + b.get_width() / 2, v + 0.8, f"{v:.0f}%", ha="center", fontsize=8, color=C["text2"])
    a1.set_xticks(x, [f"Price range {i}" for i in pr.index])
    a1.set_ylabel("% of group")
    a1.grid(axis="x", visible=False)
    a1.legend()
    a1.set_title("Price range mix")
    s = p["services"].set_index("group")
    cols = ["online_delivery_pct", "table_booking_pct", "in_india_pct", "chain_pct"]
    labels = ["Online delivery", "Table booking", "In India", "Chain"]
    x = np.arange(len(cols))
    for i, (g, col) in enumerate([("Rated", C["accent"]), ("Unrated", C["text2"])]):
        bars = a2.bar(x + (i - 0.5) * w, s.loc[g, cols], w, label=g, color=col)
        for b, v in zip(bars, s.loc[g, cols]):
            a2.text(b.get_x() + b.get_width() / 2, v + 0.8, f"{v:.0f}%", ha="center", fontsize=8, color=C["text2"])
    a2.set_xticks(x, labels)
    a2.set_ylim(0, 105)
    a2.grid(axis="x", visible=False)
    a2.set_title("Services, location and chain status")
    fig.suptitle(f"Rated ({int(s.loc['Rated', 'restaurants']):,}) vs unrated ({int(s.loc['Unrated', 'restaurants']):,}) "
                 "restaurants", fontsize=11)
    return _save(fig, "fig20_unrated_profile")


def write_doc(clean, p, treat, preds, fig: Path) -> None:
    n, u = len(clean), int((clean["is_rated"] == 0).sum())
    s = p["services"].set_index("group")
    L = ["# Unrated Restaurants", "", "*Generated by `src/unrated.py` from the cleaned Kaggle data. Nothing is typed in.*",
         "", f"**Unrated restaurants: {u:,} of {n:,} ({100 * u / n:.1f}%).** In the raw file they have aggregate "
         "rating 0 and rating text 'Not rated'. A 0 here means 'no rating yet', not a bad rating.", "",
         "## How they are treated", "", "| area | rule | evidence |", "|---|---|---|"]
    L += [f"| {r.area} | {r.rule} | {r.evidence} |" for r in treat.itertuples(index=False)]
    L += ["", "## Profile: rated vs unrated", "",
          "| group | restaurants | online delivery % | table booking % | in India % | chain % | median cost "
          "percentile in country | mean cuisines listed | median votes | max votes |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for g, r in s.iterrows():
        L.append(f"| {g} | {int(r.restaurants):,} | {r.online_delivery_pct:.1f} | {r.table_booking_pct:.1f} | "
                 f"{r.in_india_pct:.1f} | {r.chain_pct:.1f} | {r.median_cost_pct_in_country:.2f} | "
                 f"{r.mean_cuisines_listed:.2f} | {r.median_votes:g} | {r.max_votes:g} |")
    L += ["", "Price range mix (% of each group):", "", "| price range | rated % | unrated % |", "|---|---|---|"]
    L += [f"| {int(r.price_range)} | {r.Rated:.1f} | {r.Unrated:.1f} |" for r in p["price_range"].itertuples(index=False)]
    L += ["", "Unrated by country:", "", "| country | restaurants | unrated | unrated % in country | share of all unrated % |",
          "|---|---|---|---|---|"]
    L += [f"| {r.country} | {r.restaurants:,} | {r.unrated:,} | {r.unrated_pct:.1f} | {r.share_of_all_unrated_pct:.1f} |"
          for r in p["by_country"].itertuples(index=False)]
    L += ["", "Top 10 cities by number of unrated restaurants:", "",
          "| country | city | restaurants | unrated | unrated % in city | share of all unrated % |", "|---|---|---|---|---|---|"]
    L += [f"| {r.country} | {r.city} | {r.restaurants:,} | {r.unrated:,} | {r.unrated_pct:.1f} | "
          f"{r.share_of_all_unrated_pct:.1f} |" for r in p["by_city"].itertuples(index=False)]
    L += ["", "Chi-square tests of independence (rated vs unrated):", "", "| variable | chi-square | df | p-value |",
          "|---|---|---|---|"]
    L += [f"| {r.variable} | {r.chi2:.1f} | {r.dof} | {r.p_value:.3g} |" for r in p["tests"].itertuples(index=False)]
    split = preds["predicted_class"].value_counts().reindex(LABELS, fill_value=0)
    L += ["", "## Saved-model predictions for unrated restaurants", "",
          f"The saved model predicts for all {len(preds):,} unrated restaurants: "
          + ", ".join(f"{c} {split[c]:,} ({100 * split[c] / len(preds):.1f}%)" for c in LABELS)
          + ". These predictions describe what similar rated restaurants achieved; they cannot be checked, because "
          "unrated restaurants have no actual popularity class. File: `outputs/unrated/unrated_predictions.csv`.",
          "", "## Figure", "", f"- `{fig.relative_to(config.ROOT).as_posix()}`", ""]
    DOC.write_text("\n".join(L), encoding="utf-8")


def run_unrated(clean: pd.DataFrame, pairs: pd.DataFrame) -> dict:
    p = profile(clean)
    preds = predict_unrated(clean, pairs)
    treat = treatment(clean, preds)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for k, df in p.items():
        df.to_csv(OUT_DIR / f"unrated_{k}.csv", index=False)
    treat.to_csv(OUT_DIR / "unrated_treatment.csv", index=False)
    preds.to_csv(OUT_DIR / "unrated_predictions.csv", index=False)
    fig = plot_profile(p)
    write_doc(clean, p, treat, preds, fig)
    return {**p, "treatment": treat, "predictions": preds, "figure": fig}
