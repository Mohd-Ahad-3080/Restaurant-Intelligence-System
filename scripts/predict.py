"""Predict a restaurant's popularity class (Low / Medium / High) with the SAVED model.

Two ways to run it (from the project folder, with .venv active):

  1) Answer questions one by one:
       python scripts/predict.py

  2) Type everything in one line:
       python scripts/predict.py --city "New Delhi" --locality "Connaught Place" --cuisines "North Indian, Chinese" --price-range 2 --cost 600 --delivery yes --booking no

Cost = cost for two in the city's LOCAL currency. The model does not need (and never uses) votes or a
rating, so it works for a restaurant that has just opened. Test accuracy of the model: 61.3%
(3 classes; guessing would give about 33%). Treat the result as an estimate, not a promise.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scoring import load_model, new_restaurant_raw, predict_raw  # noqa: E402


def ask(question: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    answer = input(f"{question}{hint}: ").replace("﻿", "").strip()  # drop BOM from piped input
    return answer or default


def interactive() -> list[str]:
    print("Answer each question and press Enter (press Enter alone to accept the value in [brackets]).")
    city = ask("City", "New Delhi")
    return ["--city", city,
            "--locality", ask("Locality (optional)", "Connaught Place" if city.lower() == "new delhi" else ""),
            "--cuisines", ask("Cuisines, comma-separated", "North Indian, Chinese"),
            "--price-range", ask("Price range 1-4 (1 = budget, 4 = luxury)", "2"),
            "--cost", ask("Cost for two (local currency)", "600"),
            "--delivery", ask("Online delivery? (yes/no)", "yes"),
            "--booking", ask("Table booking? (yes/no)", "no"),
            "--name", ask("Restaurant name (optional; a known chain name counts its branches)", "")]


def yes(v: str) -> bool:
    return str(v).strip().lower() in ("yes", "y", "1", "true")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        argv = interactive()
    p = argparse.ArgumentParser(description="Predict popularity class with the saved model.")
    p.add_argument("--city", required=True)
    p.add_argument("--cuisines", required=True, help="Comma-separated, e.g. 'North Indian, Chinese'")
    p.add_argument("--price-range", type=int, required=True, choices=[1, 2, 3, 4])
    p.add_argument("--cost", type=float, required=True, help="Cost for two, local currency")
    p.add_argument("--delivery", default="no", help="yes/no")
    p.add_argument("--booking", default="no", help="yes/no")
    p.add_argument("--locality", default="")
    p.add_argument("--name", default="")
    p.add_argument("--country", default=None, help="Only if the city name exists in several countries")
    a = p.parse_args(argv)

    try:
        _, meta = load_model()
        row, notes = new_restaurant_raw(
            city=a.city, cuisines=[c.strip() for c in a.cuisines.split(",") if c.strip()],
            price_range=a.price_range, cost_for_two=a.cost, online_delivery=yes(a.delivery),
            table_booking=yes(a.booking), locality=a.locality or None, name=a.name or None, country=a.country)
        r = predict_raw(row).iloc[0]
    except (ValueError, FileNotFoundError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print()
    print(f"Restaurant : {r.restaurant_name} | {r.city}, {r.country}" + (f" | {r.locality}" if r.locality else ""))
    print(f"Input      : {r.cuisines} | price range {r.price_range} | cost for two {r.avg_cost_for_two:,.0f} "
          f"{r.currency} | delivery {'yes' if r.has_online_delivery else 'no'} | "
          f"booking {'yes' if r.has_table_booking else 'no'}")
    print(f"Context    : cost percentile in {r.country} = {r.cost_pct_in_country * 100:.0f} (0 cheapest, 100 dearest); "
          f"{r.restaurants_in_locality:,} restaurant(s) in this locality and "
          f"{r.branches_with_same_name:,} branch(es) with this name (both counts include this one)")
    for n in notes:
        print(f"Note       : {n}")
    print()
    print(f"PREDICTED POPULARITY: {r.predicted_class.upper()}")
    for label, col in (("High", "prob_high"), ("Medium", "prob_medium"), ("Low", "prob_low")):
        print(f"  {label:<7}{r[col]:6.1%}  " + "#" * round(r[col] * 40))
    acc = meta["test_metrics"]["test_accuracy"]
    print(f"\nModel: {meta['best_model']} (test accuracy {acc:.1%}; random guessing about 33%). "
          "Popularity = Zomato votes relative to the same country, not sales.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
