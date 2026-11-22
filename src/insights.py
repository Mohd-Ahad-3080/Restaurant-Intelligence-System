"""Key findings and recommendations for the Power BI 'Insights' page, the Tableau 'Insights and recommendations'
dashboard and the report. Every number is computed here from the cleaned data and the model outputs; the text
around it is fixed wording. All findings are associations in observational data, not causal effects.
"""
from __future__ import annotations

import pandas as pd

from src import config

OUT_DIR = config.ROOT / "outputs" / "insights"
DOC = config.DOCS_DIR / "insights.md"
NCR_CITIES = ["New Delhi", "Gurgaon", "Noida", "Faridabad", "Ghaziabad"]


def _pct(x: float, d: int = 1) -> str:
    return f"{100 * x:.{d}f}%"


def compute(clean: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    P = config.PREDICTIONS_DIR
    rated = clean[clean["is_rated"] == 1]
    high = lambda col: rated.groupby(col)["popularity_class"].apply(lambda s: (s == "High").mean())
    avg = lambda col: rated.groupby(col)["aggregate_rating"].mean()
    stats = pd.read_csv(config.ROOT / "outputs" / "eda_statistics.csv")
    rho = stats.loc[stats["question"].str.startswith("Is rating associated with number of votes"), "statistic"].iloc[0]
    comp = pd.read_csv(P / "model_comparison.csv").set_index("model")
    var = pd.read_csv(P / "model_variants.csv").set_index("variant")
    by_dist = pd.read_csv(P / "medium_class_accuracy_by_distance.csv")
    hvl = pd.read_csv(P / "high_vs_low_model.csv").iloc[0]
    meta = pd.read_json(config.MODELS_DIR / "popularity_model_meta.json", typ="series")
    best = meta["best_model"]
    n, u = len(clean), int((clean["is_rated"] == 0).sum())
    unr, rat = clean[clean["is_rated"] == 0], rated
    hp, ap = high("price_range"), avg("price_range")
    # Services: India only, rated restaurants (online delivery exists only in India and the UAE, so an
    # all-countries comparison mixes in countries without delivery; same definition as the report and EDA)
    ri = rated[rated["country"] == "India"]
    high_in = lambda col: ri.groupby(col)["popularity_class"].apply(lambda s: (s == "High").mean())
    avg_in = lambda col: ri.groupby(col)["aggregate_rating"].mean()
    hb, ab = high_in("has_table_booking"), avg_in("has_table_booking")
    hd, ad = high_in("has_online_delivery"), avg_in("has_online_delivery")
    near, far = by_dist.iloc[0], by_dist.iloc[-1]
    main, noloc = var.iloc[0], var.loc["No location (all countries)"]
    india = (clean["country"] == "India").mean()
    ncr = clean["city"].isin(NCR_CITIES).mean()

    F = [
        ("F1", "Market concentration",
         f"{_pct(india)} of the {n:,} restaurants are in India and {_pct(ncr)} are in Delhi NCR alone.",
         _pct(ncr), "data/processed/zomato_clean.csv"),
        ("F2", "Price range and popularity",
         f"The share of High-popularity restaurants rises from {_pct(hp[1])} in price range 1 to {_pct(hp[3])} in "
         f"range 3 ({_pct(hp[4])} in range 4); average rating rises from {ap[1]:.2f} to {ap[4]:.2f}.",
         f"{_pct(hp[1])} -> {_pct(hp[3])}", "rated restaurants; EDA chi-square and Kruskal-Wallis tests"),
        ("F3", "Table booking (India)",
         f"In India (rated restaurants), {_pct(hb[1])} of restaurants with table booking are High-popularity, "
         f"against {_pct(hb[0])} without; mean rating {ab[1]:.2f} vs {ab[0]:.2f}.",
         f"{_pct(hb[1])} vs {_pct(hb[0])}", "rated Indian restaurants; EDA Mann-Whitney and chi-square tests"),
        ("F4", "Online delivery (India)",
         f"In India (rated restaurants), delivery outlets are more often High-popularity ({_pct(hd[1])} vs "
         f"{_pct(hd[0])}), but their mean rating is almost the same ({ad[1]:.2f} vs {ad[0]:.2f}): delivery goes "
         "with more votes, not better ratings. Delivery exists only in India and the UAE.",
         f"{_pct(hd[1])} vs {_pct(hd[0])}", "rated Indian restaurants; EDA Mann-Whitney test"),
        ("F5", "Votes and rating",
         f"Votes and rating are strongly linked (Spearman rho = {rho:.2f}). The target is built from votes, so "
         "votes, rating and anything derived from them are excluded from the model's features.",
         f"rho {rho:.2f}", "outputs/eda_statistics.csv"),
        ("F6", "Unrated restaurants",
         f"{u:,} restaurants ({_pct(u / n)}) have no rating yet; only {_pct(unr['has_online_delivery'].mean())} of "
         f"them offer online delivery, against {_pct(rat['has_online_delivery'].mean())} of rated ones.",
         f"{u:,} ({_pct(u / n)})", "docs/unrated_restaurants.md"),
        ("F7", "Popularity model",
         f"The honest model ({best}) reaches {_pct(comp.loc[best, 'test_accuracy'])} accuracy against a "
         f"{_pct(comp.loc['Baseline (majority class)', 'test_accuracy'])} baseline. Location is its strongest "
         f"signal: without location features accuracy falls to {_pct(noloc['test_accuracy'])}.",
         _pct(comp.loc[best, "test_accuracy"]), "docs/model_results.md"),
        ("F8", "Medium class",
         f"Accuracy is {_pct(near['test_accuracy'])} for restaurants within 5 percentile points of a class cut-off "
         f"and {_pct(far['test_accuracy'])} for those far from it. Telling High from Low alone (a separate, easier "
         f"question) reaches {_pct(hvl['test_accuracy'])}.",
         f"{_pct(near['test_accuracy'])} vs {_pct(far['test_accuracy'])}", "docs/model_results.md"),
    ]
    findings = pd.DataFrame(F, columns=["id", "theme", "finding", "key_number", "source"])
    R = [
        ("R1", "Choose the location first", "F1, F7",
         "Location and locality carry the most signal for popularity; compare candidate localities before "
         "deciding cuisine or price. Caveat: outside Delhi NCR the data lists mostly well-known restaurants, so "
         "part of the location effect reflects how Zomato sampled cities."),
        ("R2", "Offer table booking where the format allows it", "F3",
         "It goes with a much higher share of High-popularity restaurants (association, not proof of cause)."),
        ("R3", "Use delivery for reach, not for rating", "F4",
         f"In India, delivery goes with a higher High-popularity share ({_pct(hd[1])} vs {_pct(hd[0])}) but "
         f"ratings barely differ ({ad[1]:.2f} vs {ad[0]:.2f}); service quality still drives the rating."),
        ("R4", "Mind the price band", "F2",
         "Mid and upper price ranges are more often High-popularity; budget outlets compete in a crowded, "
         "lower-voted segment."),
        ("R5", "Help unrated restaurants get their first ratings", "F6",
         "A fifth of listings have no rating; platform prompts or owner follow-up would make them comparable."),
        ("R6", "Use the model as a screen, not a verdict", "F7, F8",
         "It separates likely High from likely Low well; Medium predictions near a cut-off are uncertain."),
    ]
    recs = pd.DataFrame(R, columns=["id", "title", "based_on", "text"])
    return findings, recs


def run_insights(clean: pd.DataFrame) -> dict:
    findings, recs = compute(clean)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    findings.to_csv(OUT_DIR / "insights.csv", index=False)
    recs.to_csv(OUT_DIR / "recommendations.csv", index=False)
    L = ["# Insights and Recommendations", "",
         "*Generated by `src/insights.py`; every number is computed from the data and model outputs. Findings are "
         "associations in observational data, not causal effects.*", "", "## Key findings", "",
         "| # | theme | finding | key number | source |", "|---|---|---|---|---|"]
    L += [f"| {r.id} | {r.theme} | {r.finding} | {r.key_number} | {r.source} |" for r in findings.itertuples()]
    L += ["", "## Recommendations", "", "| # | recommendation | based on | why |", "|---|---|---|---|"]
    L += [f"| {r.id} | {r.title} | {r.based_on} | {r.text} |" for r in recs.itertuples()]
    DOC.write_text("\n".join(L) + "\n", encoding="utf-8")
    return {"findings": findings, "recommendations": recs}
