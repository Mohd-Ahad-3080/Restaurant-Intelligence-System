"""Recommend restaurants from the command line (uses the existing engine in src/recommender.py).

Two ways to run it (from the project folder, with .venv active):

  1) Answer questions one by one:
       python scripts/recommend.py

  2) Type everything in one line:
       python scripts/recommend.py --city "New Delhi" --cuisine "North Indian" --budget 800 --min-rating 3.5 --delivery required

Budget = cost for two in the city's LOCAL currency (e.g. rupees in New Delhi, pounds in London).
--data lets you use another cleaned file (e.g. outputs/runs/<name>/processed/zomato_clean.csv).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from src import config  # noqa: E402
from src.recommender import Request, budget_currency, filter_funnel, recommend  # noqa: E402

DEFAULT_DATA = config.PROCESSED_DIR / "zomato_clean.csv"


def ask(question: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    answer = input(f"{question}{hint}: ").replace("﻿", "").strip()  # drop BOM from piped input
    return answer or default


def interactive() -> list[str]:
    print("Answer each question and press Enter (press Enter alone to accept the value in [brackets]).")
    args = ["--city", ask("City (e.g. New Delhi, Gurgaon, Mumbai, London)", "New Delhi")]
    cuisine = ask("Cuisine(s), comma-separated, or leave empty for any", "North Indian")
    if cuisine:
        args += ["--cuisine", cuisine]
    budget = ask("Budget for two in local currency, or leave empty for no limit", "800")
    if budget:
        args += ["--budget", budget]
    args += ["--min-rating", ask("Minimum rating (0 to 5)", "3.5")]
    args += ["--delivery", "required" if ask("Online delivery required? (yes/no)", "yes").lower().startswith("y")
             else "any"]
    locality = ask("Locality (optional, e.g. Connaught Place)", "")
    if locality:
        args += ["--locality", locality]
    return args


def show(result: pd.DataFrame, req: Request, data: pd.DataFrame) -> None:
    funnel = filter_funnel(data, req)
    cur = budget_currency(data, req)
    print()
    print(f"Request: {req.city}" + (f" / {req.locality}" if req.locality else "")
          + f" | cuisine: {', '.join(req.cuisines) or 'any'} | budget: "
          + (f"{req.budget:,.0f} {cur}" if req.budget else "no limit")
          + f" | min rating: {req.min_rating} | delivery: {req.delivery}")
    print("Filters: " + " -> ".join(f"{k}: {v:,}" for k, v in funnel.items()))
    if result.empty:
        print("\nNo restaurant meets these filters. Try a lower minimum rating or delivery = any.")
        return
    t = pd.DataFrame({
        "#": result["rank"],
        "Restaurant": result["restaurant_name"].str.slice(0, 30),
        "Locality": result["locality"].str.slice(0, 24),
        "Rating": result["aggregate_rating"].map(lambda v: "-" if pd.isna(v) else f"{v:.1f}"),
        "Votes": result["votes"].map("{:,}".format),
        "Cost": result["avg_cost_for_two"].map(lambda v: "-" if pd.isna(v) else f"{v:,.0f}"),
        "Rating pts": result["rating_points"].map("{:.3f}".format),
        "Popular pts": result["popularity_points"].map("{:.3f}".format),
        "Budget pts": result["budget_points"].map("{:.3f}".format),
        "Cuisine pts": result["cuisine_points"].map("{:.3f}".format),
        "SCORE": result["total_score"].map("{:.3f}".format),
    })
    print()
    print(t.to_string(index=False))
    print("\nSCORE = 0.40 x rating + 0.25 x popularity + 0.20 x budget fit + 0.15 x cuisine match "
          "(the 'pts' columns add up to SCORE).")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        argv = interactive()
    p = argparse.ArgumentParser(description="Ranked restaurant recommendations.")
    p.add_argument("--city", required=True)
    p.add_argument("--cuisine", default="", help="One or more cuisines, comma-separated")
    p.add_argument("--budget", type=float, default=None, help="Cost for two, local currency")
    p.add_argument("--min-rating", type=float, default=0.0)
    p.add_argument("--delivery", choices=["any", "required"], default="any")
    p.add_argument("--locality", default=None)
    p.add_argument("--country", default=None, help="Only if the city name exists in several countries")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--data", type=Path, default=DEFAULT_DATA, help="Cleaned CSV to search")
    a = p.parse_args(argv)

    if not a.data.exists():
        print(f"ERROR: {a.data} not found. Run `python run_pipeline.py` first.", file=sys.stderr)
        return 1
    data = pd.read_csv(a.data, encoding="utf-8")
    req = Request(city=a.city, cuisines=[c.strip() for c in a.cuisine.split(",") if c.strip()], budget=a.budget,
                  min_rating=a.min_rating, delivery=a.delivery, locality=a.locality, top_n=a.top, country=a.country)
    try:
        result = recommend(data, req)
        show(result, req, data)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
