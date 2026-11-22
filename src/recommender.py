"""Content-based restaurant recommendation engine.

Score = 0.40 x rating + 0.25 x popularity + 0.20 x budget suitability + 0.15 x cuisine match,
each component normalised to 0-1. (This is not the ML model, so rating and votes may be used.)

Hard filters : city, locality (optional), minimum rating, delivery preference.
Soft (scored): budget, cuisine.

Component definitions
- rating     = aggregate_rating / 5 (unrated restaurants score 0 and fail any min_rating > 0).
- popularity = log(1 + votes) / log(1 + max votes in the chosen city); log because votes are very skewed.
- budget     = 1 if cost for two <= budget; falls linearly to 0 at 2 x budget; 0.5 if cost unknown;
               1 for everyone if no budget is given. The budget is ALWAYS in the selected city's
               LOCAL currency (e.g. GBP for London, INR for New Delhi). `city_candidates` guarantees one
               currency per request, and the output column `budget_currency` states it.
- cuisine    = share of the requested cuisines the restaurant offers (1 if no cuisine requested).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src import config

WEIGHTS = {"rating": 0.40, "popularity": 0.25, "budget": 0.20, "cuisine": 0.15}
UNKNOWN_COST_SCORE = 0.5


@dataclass
class Request:
    city: str
    cuisines: list[str] = field(default_factory=list)
    budget: float | None = None
    min_rating: float = 0.0
    delivery: str = "any"          # "any" or "required"
    locality: str | None = None
    top_n: int = 10
    country: str | None = None     # only needed if a city name exists in more than one country


def _norm(s: str) -> str:
    return " ".join(str(s).lower().split())


def _budget_score(cost: pd.Series, budget: float | None) -> pd.Series:
    if budget is None:
        return pd.Series(1.0, index=cost.index)
    if budget <= 0:
        raise ValueError("Budget must be a positive amount.")
    over = ((cost - budget) / budget).clip(lower=0)
    score = (1 - over).clip(lower=0, upper=1)
    return score.where(cost.notna(), UNKNOWN_COST_SCORE)


def _cuisine_score(cuisines: pd.Series, wanted: list[str]) -> pd.Series:
    if not wanted:
        return pd.Series(1.0, index=cuisines.index)
    want = {_norm(w) for w in wanted}
    offered = cuisines.fillna("").map(lambda s: {_norm(c) for c in s.split(",")})
    return offered.map(lambda have: len(want & have) / len(want))


def city_candidates(clean: pd.DataFrame, req: Request) -> pd.DataFrame:
    """Rows for the requested city (and country, if given). Guarantees ONE local currency, so the
    budget and every cost compared with it are in the same currency."""
    rows = clean[clean["city"].map(_norm) == _norm(req.city)]
    if req.country:
        rows = rows[rows["country"].map(_norm) == _norm(req.country)]
    if rows.empty:
        close = sorted(c for c in clean["city"].dropna().unique() if _norm(req.city)[:3] in _norm(c))[:5]
        raise ValueError(f"City '{req.city}'" + (f" in '{req.country}'" if req.country else "") + " not found."
                         + (f" Did you mean: {', '.join(close)}?" if close else ""))
    currencies = sorted(rows["currency"].dropna().unique())
    if len(currencies) > 1:
        raise ValueError(f"City '{req.city}' has restaurants in several currencies ({', '.join(currencies)}). "
                         "Specify the country so the budget is compared in one local currency.")
    return rows


def budget_currency(clean: pd.DataFrame, req: Request) -> str:
    """The local currency in which `req.budget` is interpreted."""
    return str(city_candidates(clean, req)["currency"].iloc[0])


def recommend(clean: pd.DataFrame, req: Request, weights: dict[str, float] = WEIGHTS) -> pd.DataFrame:
    if abs(sum(weights.values()) - 1) > 1e-9:
        raise ValueError("Weights must add up to 1.")
    if req.delivery not in ("any", "required"):
        raise ValueError("delivery must be 'any' or 'required'.")

    city_rows = city_candidates(clean, req)
    known = {_norm(c) for s in clean["cuisines"].dropna() for c in s.split(",")}
    unknown = [c for c in req.cuisines if _norm(c) not in known]
    if unknown:
        raise ValueError(f"Unknown cuisine(s): {', '.join(unknown)}")

    max_votes = city_rows["votes"].max()
    cand = city_rows.copy()
    if req.locality:
        cand = cand[cand["locality"].map(_norm).str.contains(_norm(req.locality), regex=False)]
    cand = cand[cand["aggregate_rating"].fillna(0) >= req.min_rating]
    if req.delivery == "required":
        cand = cand[cand["has_online_delivery"] == 1]
    if cand.empty:
        return pd.DataFrame()

    comp = pd.DataFrame(index=cand.index)
    comp["rating_score"] = cand["aggregate_rating"].fillna(0) / 5
    comp["popularity_score"] = (np.log1p(cand["votes"]) / np.log1p(max_votes)) if max_votes > 0 else 0.0
    comp["budget_score"] = _budget_score(cand["avg_cost_for_two"], req.budget)
    comp["cuisine_score"] = _cuisine_score(cand["cuisines"], req.cuisines)
    for k, w in weights.items():
        comp[f"{k}_points"] = w * comp[f"{k}_score"]
    comp["total_score"] = comp[[f"{k}_points" for k in weights]].sum(axis=1)

    out = cand[["restaurant_id", "restaurant_name", "city", "locality", "cuisines", "avg_cost_for_two", "currency",
                "price_range", "aggregate_rating", "votes", "has_online_delivery", "has_table_booking"]].join(comp)
    out = out.sort_values(["total_score", "aggregate_rating", "votes", "restaurant_id"],
                          ascending=[False, False, False, True]).head(req.top_n)
    out.insert(0, "rank", range(1, len(out) + 1))
    out["budget"] = req.budget
    out["budget_currency"] = city_rows["currency"].iloc[0]
    return out.reset_index(drop=True)


def filter_funnel(clean: pd.DataFrame, req: Request) -> dict[str, int]:
    """How many restaurants remain after each hard filter (for explaining results in the report)."""
    d = city_candidates(clean, req)
    f = {"in city": len(d)}
    if req.locality:
        d = d[d["locality"].map(_norm).str.contains(_norm(req.locality), regex=False)]
        f["in locality"] = len(d)
    d = d[d["aggregate_rating"].fillna(0) >= req.min_rating]
    f[f"rating >= {req.min_rating}"] = len(d)
    if req.delivery == "required":
        d = d[d["has_online_delivery"] == 1]
        f["offers online delivery"] = len(d)
    return f


# Example requests used to illustrate the engine in the report (inputs only; results come from the data).
SCENARIOS = {
    "S1": Request("New Delhi", ["North Indian"], budget=800, min_rating=3.5, delivery="required", top_n=5),
    "S2": Request("Gurgaon", ["Italian"], budget=2000, min_rating=4.0, top_n=5),
    "S3": Request("Noida", ["Chinese"], budget=500, min_rating=3.0, locality="Sector 18", top_n=5),
    "S4": Request("London", ["British"], budget=60, min_rating=4.0, top_n=5),
}

def run_examples(clean: pd.DataFrame) -> pd.DataFrame:
    rows, md = [], ["# Recommendation Engine: Worked Examples", "",
                    "*Generated by `src/recommender.py` from the cleaned data. Scores: 0.40 × rating + 0.25 × "
                    "popularity + 0.20 × budget + 0.15 × cuisine, each 0–1.*", "",
                    "Hard filters: city, locality (optional), minimum rating, delivery. Budget (local currency) and "
                    "cuisine are scored, not filtered, so a close alternative can still appear with a lower score.",
                    ""]
    for sid, req in SCENARIOS.items():
        res = recommend(clean, req)
        funnel = filter_funnel(clean, req)
        md += [f"## {sid}: {req.city}" + (f" / {req.locality}" if req.locality else ""), "",
               f"Request: cuisine {', '.join(req.cuisines) or 'any'}; budget "
               f"{f'{req.budget:,.0f} {budget_currency(clean, req)}' if req.budget else 'none'} for two "
               f"(local currency of {req.city}); minimum rating {req.min_rating}; delivery {req.delivery}.", "",
               "Filter funnel: " + " → ".join(f"{k}: {v:,}" for k, v in funnel.items()) + ".", ""]
        if res.empty:
            md += ["No restaurant meets the hard filters.", ""]
            continue
        md += ["| rank | restaurant | locality | rating | votes | cost for two | rating pts | popularity pts | "
               "budget pts | cuisine pts | total |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in res.itertuples(index=False):
            cost = "" if pd.isna(r.avg_cost_for_two) else f"{r.avg_cost_for_two:,.0f}"
            md.append(f"| {r.rank} | {r.restaurant_name} | {r.locality} | {r.aggregate_rating:.1f} | {r.votes:,} | "
                      f"{cost} | {r.rating_points:.3f} | {r.popularity_points:.3f} | {r.budget_points:.3f} | "
                      f"{r.cuisine_points:.3f} | **{r.total_score:.3f}** |")
        md.append("")
        rows.append(res.assign(scenario=sid))
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    out.to_csv(config.OUTPUTS_DIR / "recommendation_examples.csv", index=False)
    (config.DOCS_DIR / "recommendation_examples.md").write_text("\n".join(md), encoding="utf-8")
    return out
