"""Compute class splits for the candidate popularity-target definitions.

Numbers produced here feed docs/target_variable_proposal.md. Exploratory only:
the chosen target (Option B) is implemented in src/target.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data_loading import load_with_country

LABELS = ["Low", "Medium", "High"]


def _tertiles(s: pd.Series):
    q = s.quantile([1 / 3, 2 / 3]).values
    return q, pd.cut(s, [-np.inf, q[0], q[1], np.inf], labels=LABELS)


def option_a(rated: pd.DataFrame):
    """Global tertiles of log(1 + votes), rated restaurants only."""
    q, lab = _tertiles(np.log1p(rated["Votes"]))
    return np.expm1(q), lab


def option_b(rated: pd.DataFrame):
    """Within-country percentile rank of votes, cut into thirds, rated restaurants only."""
    pr = rated.groupby("Country")["Votes"].rank(pct=True, method="average")
    return pd.cut(pr, [0, 1 / 3, 2 / 3, 1.0], labels=LABELS, include_lowest=True)


def option_c(rated: pd.DataFrame):
    """Tertiles of a Bayesian weighted rating (votes-weighted toward the mean rating)."""
    m = rated["Votes"].median()
    c = rated["Aggregate rating"].mean()
    v, r = rated["Votes"], rated["Aggregate rating"]
    wr = v / (v + m) * r + m / (v + m) * c
    q, lab = _tertiles(wr)
    return m, c, q, lab


def main():
    df = load_with_country()
    rated = df[df["Rating text"] != "Not rated"].copy()
    print(f"Rated: {len(rated):,}  Unrated (excluded): {len(df) - len(rated):,}")
    print("Rated votes:", rated["Votes"].describe().round(1).to_dict())

    cuts, a = option_a(rated)
    print("\nA  vote cut-offs:", cuts.round(1), "| classes:", a.value_counts().to_dict())
    print("A  % High by country:", (a.eq("High").groupby(rated["Country"]).mean() * 100).round(1).to_dict())

    b = option_b(rated)
    print("\nB  classes:", b.value_counts().to_dict())
    print("B  % High by country:", (b.eq("High").groupby(rated["Country"]).mean() * 100).round(1).to_dict())

    m, c, q, lab = option_c(rated)
    print(f"\nC  prior m={m}, mean rating={c:.3f}, cuts={q.round(3)} | classes:", lab.value_counts().to_dict())

    corr = np.corrcoef(np.log1p(rated["Votes"]), rated["Aggregate rating"])[0, 1]
    print(f"\nCorrelation log(1+votes) vs rating (rated only): {corr:.3f}")
    nr = df[df["Rating text"] == "Not rated"]["Votes"]
    print(f"Unrated restaurants: votes min={nr.min()} max={nr.max()}; rated min votes={rated['Votes'].min()}")


if __name__ == "__main__":
    main()
