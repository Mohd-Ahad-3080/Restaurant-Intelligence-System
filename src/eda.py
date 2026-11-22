"""Exploratory data analysis for the report.

Reads the cleaned data FROM MYSQL (tables and views loaded by run_pipeline.py), produces report figures
(outputs/figures/figNN_*.png), a statistics table (outputs/eda_statistics.csv) and a findings
document (docs/eda_findings.md). All numbers are computed here; nothing is typed in.

Statistical tests are non-parametric (ratings and votes are not normally distributed) and describe
association, not causation.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy.engine import Engine

from src import config
from src.db import read_sql

FIG_DIR = config.FIGURES_DIR
STATS_CSV = config.OUTPUTS_DIR / "eda_statistics.csv"
FINDINGS_MD = config.DOCS_DIR / "eda_findings.md"
DPI = 200
ALPHA = 0.05

# Colour theme shared by all charts and dashboards
C = {
    "accent": "#CB202D", "highlight": "#8E1520", "light1": "#E8838B", "light2": "#F5C6CA",
    "slate": "#1F2329", "text": "#18181B", "text2": "#5C5C66", "border": "#E4E4E7", "track": "#EFEFF1",
}
PRICE_COLOURS = {1: "#8E1520", 2: "#CB202D", 3: "#E8838B", 4: "#F5C6CA"}  # Budget -> Luxury
PRICE_LABELS = {1: "1 Budget", 2: "2", 3: "3", 4: "4 Luxury"}
POP_COLOURS = {"Low": C["light2"], "Medium": C["light1"], "High": C["highlight"]}
POP_ORDER = ["Low", "Medium", "High"]


# ------------------------------------------------------------------ plotting helpers
def _style():
    plt.rcParams.update({
        "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.edgecolor": C["border"], "axes.labelcolor": C["text2"], "xtick.color": C["text2"],
        "ytick.color": C["text2"], "text.color": C["text"], "axes.spines.top": False,
        "axes.spines.right": False, "axes.grid": True, "grid.color": C["track"], "grid.linewidth": 0.8,
        "axes.axisbelow": True, "figure.facecolor": "white", "savefig.facecolor": "white",
        "legend.frameon": False,
    })


def _save(fig, name: str) -> Path:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    p = FIG_DIR / f"{name}.png"
    fig.tight_layout()
    fig.savefig(p, dpi=DPI)
    plt.close(fig)
    return p


def _hbar(ax, labels, values, colour=C["accent"], fmt="{:,.0f}"):
    y = np.arange(len(labels))
    ax.barh(y, values, color=colour, height=0.7)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    vmax = max(values) if len(values) else 0
    for yi, v in zip(y, values):
        ax.text(v + vmax * 0.01, yi, fmt.format(v), va="center", fontsize=8, color=C["text2"])
    ax.set_xlim(0, vmax * 1.12 if vmax else 1)


# ------------------------------------------------------------------ data
def load_from_mysql(engine: Engine) -> tuple[pd.DataFrame, pd.DataFrame]:
    rest = read_sql(engine, "SELECT * FROM v_restaurants")
    pairs = read_sql(engine, "SELECT rc.restaurant_id, rc.cuisine FROM restaurant_cuisines rc")
    for col in ("aggregate_rating", "avg_cost_for_two", "votes_pct_in_country", "longitude", "latitude"):
        rest[col] = pd.to_numeric(rest[col], errors="coerce").astype(float)
    return rest, pairs


# ------------------------------------------------------------------ statistics
def _mwu(a: pd.Series, b: pd.Series, label: str, a_name: str, b_name: str) -> dict:
    a, b = a.dropna(), b.dropna()
    u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
    r_rb = 2 * u / (len(a) * len(b)) - 1  # rank-biserial: >0 means group a tends to be higher
    return {"test": "Mann-Whitney U", "question": label,
            "groups": f"{a_name} (n={len(a):,}, median={a.median():.2f}) vs {b_name} (n={len(b):,}, median={b.median():.2f})",
            "statistic": round(float(u), 1), "p_value": float(p), "effect_size": round(float(r_rb), 3),
            "effect_measure": "rank-biserial r"}


def _spearman(x: pd.Series, y: pd.Series, label: str) -> dict:
    d = pd.concat([x, y], axis=1).dropna()
    rho, p = stats.spearmanr(d.iloc[:, 0], d.iloc[:, 1])
    return {"test": "Spearman correlation", "question": label, "groups": f"n={len(d):,}",
            "statistic": round(float(rho), 3), "p_value": float(p), "effect_size": round(float(rho), 3),
            "effect_measure": "rho"}


def _kruskal(df: pd.DataFrame, group: str, value: str, label: str) -> dict:
    d = df[[group, value]].dropna()
    groups = [g[value].values for _, g in d.groupby(group)]
    h, p = stats.kruskal(*groups)
    eps2 = h / (len(d) - 1)
    return {"test": "Kruskal-Wallis H", "question": label, "groups": f"{len(groups)} groups, n={len(d):,}",
            "statistic": round(float(h), 1), "p_value": float(p), "effect_size": round(float(eps2), 3),
            "effect_measure": "epsilon-squared"}


def _chi2(df: pd.DataFrame, a: str, b: str, label: str) -> dict:
    t = pd.crosstab(df[a], df[b])
    chi2, p, dof, _ = stats.chi2_contingency(t)
    v = np.sqrt(chi2 / (t.values.sum() * (min(t.shape) - 1)))
    return {"test": "Chi-square independence", "question": label,
            "groups": f"{t.shape[0]}x{t.shape[1]} table, n={t.values.sum():,}, dof={dof}",
            "statistic": round(float(chi2), 1), "p_value": float(p), "effect_size": round(float(v), 3),
            "effect_measure": "Cramer's V"}


def run_statistics(rest: pd.DataFrame) -> pd.DataFrame:
    rated = rest[rest["is_rated"] == 1].copy()
    india = rated[rated["country_name"] == "India"]
    rows = [
        _spearman(np.log1p(rated["votes"]), rated["aggregate_rating"],
                  "Is rating associated with number of votes? (rated restaurants)"),
        _kruskal(rated, "price_range", "aggregate_rating", "Does rating differ across price ranges?"),
        _spearman(rated["price_range"], rated["aggregate_rating"], "Is price range associated with rating?"),
        _mwu(india.loc[india["has_online_delivery"] == 1, "aggregate_rating"],
             india.loc[india["has_online_delivery"] == 0, "aggregate_rating"],
             "India: does rating differ with online delivery?", "Delivery", "No delivery"),
        _mwu(india.loc[india["has_table_booking"] == 1, "aggregate_rating"],
             india.loc[india["has_table_booking"] == 0, "aggregate_rating"],
             "India: does rating differ with table booking?", "Booking", "No booking"),
        _spearman(india["avg_cost_for_two"], india["aggregate_rating"],
                  "India: is cost for two (INR) associated with rating?"),
        _spearman(rated.loc[rated["n_cuisines"] > 0, "n_cuisines"], rated["aggregate_rating"],
                  "Is the number of cuisines offered associated with rating?"),
        _chi2(rated, "price_range", "popularity_class", "Is popularity class independent of price range?"),
        _chi2(rated, "has_online_delivery", "popularity_class",
              "Is popularity class independent of online delivery?"),
        _chi2(rated, "has_table_booking", "popularity_class", "Is popularity class independent of table booking?"),
    ]
    branches = rest.groupby("restaurant_name")["restaurant_id"].transform("count")
    rated_b = branches[rest["is_rated"] == 1]
    rows.append(_mwu(rated.loc[rated_b > 1, "aggregate_rating"], rated.loc[rated_b == 1, "aggregate_rating"],
                     "Do chain branches (2+ outlets) differ in rating from single outlets?", "Chain", "Single"))
    loc = (india.groupby(["city", "locality"])
           .agg(n=("restaurant_id", "size"), avg=("aggregate_rating", "mean")).reset_index())
    loc = loc[loc["n"] >= 10]
    rows.append(_spearman(loc["n"], loc["avg"],
                          "India: are localities with more rated restaurants (competition) rated differently? "
                          "(localities with 10+ rated)"))
    out = pd.DataFrame(rows)
    out["significant_at_0.05"] = out["p_value"] < ALPHA
    return out


# ------------------------------------------------------------------ figures
def make_figures(rest: pd.DataFrame, pairs: pd.DataFrame) -> list[Path]:
    _style()
    rated = rest[rest["is_rated"] == 1]
    india_rated = rated[rated["country_name"] == "India"]
    paths = []

    # 01 restaurants by country
    s = rest["country_name"].value_counts()
    fig, ax = plt.subplots(figsize=(8, 4.8))
    _hbar(ax, s.index.tolist(), s.values)
    ax.set_title("Restaurants by country")
    ax.set_xlabel("Number of restaurants")
    paths.append(_save(fig, "fig01_restaurants_by_country"))

    # 02 top 10 cities
    s = rest["city"].value_counts().head(10)
    fig, ax = plt.subplots(figsize=(8, 4.2))
    _hbar(ax, s.index.tolist(), s.values)
    ax.set_title("Top 10 cities by number of restaurants")
    ax.set_xlabel("Number of restaurants")
    paths.append(_save(fig, "fig02_top_cities"))

    # 03 rating distribution (rated only)
    fig, ax = plt.subplots(figsize=(8, 4.2))
    bins = np.arange(rated["aggregate_rating"].min() - 0.05, rated["aggregate_rating"].max() + 0.15, 0.1)
    ax.hist(rated["aggregate_rating"], bins=bins, color=C["accent"], edgecolor="white", linewidth=0.6)
    m = rated["aggregate_rating"].mean()
    ax.axvline(m, color=C["slate"], linestyle="--", linewidth=1.2)
    ax.text(m, ax.get_ylim()[1] * 0.95, f"  mean {m:.2f}", color=C["slate"], fontsize=9, va="top")
    ax.set_title(f"Rating distribution (rated restaurants, n={len(rated):,}; "
                 f"{int((rest['is_rated'] == 0).sum()):,} unrated excluded)")
    ax.set_xlabel("Aggregate rating (0-5)")
    ax.set_ylabel("Restaurants")
    paths.append(_save(fig, "fig03_rating_distribution"))

    # 04 top 15 cuisines
    s = pairs["cuisine"].value_counts().head(15)
    fig, ax = plt.subplots(figsize=(8, 5))
    _hbar(ax, s.index.tolist(), s.values)
    ax.set_title("Top 15 cuisines (restaurants offering each)")
    ax.set_xlabel("Number of restaurants")
    paths.append(_save(fig, "fig04_top_cuisines"))

    # 05 price range mix
    s = rest["price_range"].value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar([PRICE_LABELS[i] for i in s.index], s.values, color=[PRICE_COLOURS[i] for i in s.index],
                  edgecolor=C["text2"], linewidth=0.6, width=0.65)
    for b, v in zip(bars, s.values):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:,}\n({100 * v / s.sum():.1f}%)", ha="center",
                va="bottom", fontsize=8, color=C["text2"])
    ax.set_ylim(0, s.max() * 1.2)
    ax.grid(axis="x", visible=False)
    ax.set_title("Restaurants by price range")
    ax.set_xlabel("Price range")
    ax.set_ylabel("Restaurants")
    paths.append(_save(fig, "fig05_price_range_mix"))

    # 06 rating by price range (box plot)
    pr = sorted(rated["price_range"].dropna().unique())
    data = [rated.loc[rated["price_range"] == p, "aggregate_rating"].values for p in pr]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    bp = ax.boxplot(data, patch_artist=True, widths=0.55, medianprops={"color": C["slate"], "linewidth": 1.5},
                    flierprops={"marker": "o", "markersize": 2, "markerfacecolor": C["text2"],
                                "markeredgecolor": "none", "alpha": 0.4})
    for patch, p in zip(bp["boxes"], pr):
        patch.set_facecolor(PRICE_COLOURS[int(p)])
        patch.set_edgecolor(C["text2"])
    ax.set_xticks(range(1, len(pr) + 1), [f"{PRICE_LABELS[int(p)]}\n(n={len(d):,})" for p, d in zip(pr, data)])
    ax.grid(axis="x", visible=False)
    ax.set_title("Rating by price range (rated restaurants)")
    ax.set_xlabel("Price range")
    ax.set_ylabel("Aggregate rating")
    paths.append(_save(fig, "fig06_rating_by_price_range"))

    # 07 votes vs rating
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.scatter(rated["votes"], rated["aggregate_rating"], s=6, alpha=0.25, color=C["accent"], edgecolors="none")
    ax.set_xscale("log")
    rho = stats.spearmanr(rated["votes"], rated["aggregate_rating"])[0]
    ax.set_title(f"Votes vs rating (rated restaurants, Spearman rho = {rho:.2f})")
    ax.set_xlabel("Votes (log scale)")
    ax.set_ylabel("Aggregate rating")
    paths.append(_save(fig, "fig07_votes_vs_rating"))

    # 08 delivery & booking vs rating (India)
    fig, axes = plt.subplots(1, 2, figsize=(8, 4), sharey=True)
    for ax, col, title in [(axes[0], "has_online_delivery", "Online delivery"),
                           (axes[1], "has_table_booking", "Table booking")]:
        g = india_rated.groupby(col)["aggregate_rating"].agg(["mean", "size"]).reindex([0, 1])
        bars = ax.bar(["No", "Yes"], g["mean"], color=[C["text2"], C["accent"]], width=0.6)
        for b, (mval, n) in zip(bars, g.itertuples(index=False)):
            ax.text(b.get_x() + b.get_width() / 2, mval, f"{mval:.2f}\n(n={n:,})", ha="center", va="bottom",
                    fontsize=8, color=C["text2"])
        ax.set_title(title, fontsize=11)
        ax.set_ylim(0, 5)
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("Mean rating (rated, India)")
    fig.suptitle("India: mean rating with and without services", x=0.02, ha="left", fontweight="bold")
    paths.append(_save(fig, "fig08_services_vs_rating_india"))

    # 09 popularity class by price range (100% stacked)
    t = pd.crosstab(rated["price_range"], rated["popularity_class"], normalize="index")[POP_ORDER] * 100
    fig, ax = plt.subplots(figsize=(8, 4))
    left = np.zeros(len(t))
    ylabels = [PRICE_LABELS[int(i)] for i in t.index]
    for cls in POP_ORDER:
        ax.barh(ylabels, t[cls], left=left, color=POP_COLOURS[cls], edgecolor="white", linewidth=1.5,
                label=cls, height=0.65)
        for yi, (l, w) in enumerate(zip(left, t[cls])):
            if w >= 6:
                ax.text(l + w / 2, yi, f"{w:.0f}%", ha="center", va="center", fontsize=8,
                        color="white" if cls == "High" else C["text"])
        left += t[cls].values
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.grid(visible=False)
    ax.set_xlabel("Share of rated restaurants (%)")
    ax.set_ylabel("Price range")
    ax.set_title("Popularity class by price range")
    ax.legend(ncol=3, loc="lower center", bbox_to_anchor=(0.5, -0.32))
    paths.append(_save(fig, "fig09_popularity_by_price_range"))

    # 10 % High popularity by service combination
    g = rated.assign(
        combo=np.select([(rated.has_online_delivery == 1) & (rated.has_table_booking == 1),
                         rated.has_online_delivery == 1, rated.has_table_booking == 1],
                        ["Delivery + booking", "Delivery only", "Booking only"], "Neither"))
    s = (g.groupby("combo")["popularity_class"].apply(lambda x: 100 * (x == "High").mean())
         .reindex(["Neither", "Booking only", "Delivery only", "Delivery + booking"]))
    n = g["combo"].value_counts().reindex(s.index)
    fig, ax = plt.subplots(figsize=(8, 3.8))
    _hbar(ax, [f"{i} (n={n[i]:,})" for i in s.index], s.values, fmt="{:.1f}%")
    ax.set_xlim(0, 100)
    ax.set_title("Share of High-popularity restaurants by services offered")
    ax.set_xlabel("High popularity (% of rated restaurants)")
    paths.append(_save(fig, "fig10_high_popularity_by_services"))

    # 11 locality competition vs rating (India, localities with 10+ rated)
    loc = (india_rated.groupby(["city", "locality"])
           .agg(n=("restaurant_id", "size"), avg=("aggregate_rating", "mean")).reset_index())
    loc = loc[loc["n"] >= 10]
    rho = stats.spearmanr(loc["n"], loc["avg"])[0]
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.scatter(loc["n"], loc["avg"], s=18, alpha=0.6, color=C["accent"], edgecolors="white", linewidths=0.4)
    ax.set_title(f"India: locality size vs mean rating ({len(loc)} localities, Spearman rho = {rho:.2f})")
    ax.set_xlabel("Rated restaurants in locality")
    ax.set_ylabel("Mean rating of locality")
    paths.append(_save(fig, "fig11_locality_competition"))

    # 12 mean rating of top 15 cuisines
    top = pairs["cuisine"].value_counts().head(15).index
    m = (pairs[pairs["cuisine"].isin(top)].merge(rated[["restaurant_id", "aggregate_rating"]], on="restaurant_id")
         .groupby("cuisine")["aggregate_rating"].agg(["mean", "size"]).sort_values("mean", ascending=False))
    overall = rated["aggregate_rating"].mean()
    fig, ax = plt.subplots(figsize=(8, 5))
    y = np.arange(len(m))
    ax.hlines(y, overall, m["mean"], color=C["border"], linewidth=2)
    ax.scatter(m["mean"], y, color=[C["accent"] if v >= overall else C["text2"] for v in m["mean"]], s=40, zorder=3)
    ax.axvline(overall, color=C["slate"], linestyle="--", linewidth=1,
               label=f"Overall mean of rated restaurants ({overall:.2f})")
    ax.legend(loc="lower right", fontsize=8)
    ax.set_yticks(y, [f"{c} (n={n:,})" for c, n in zip(m.index, m["size"])])
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_title("Mean rating of the 15 most common cuisines (rated)")
    ax.set_xlabel("Mean aggregate rating")
    paths.append(_save(fig, "fig12_rating_by_cuisine"))
    return paths


# ------------------------------------------------------------------ findings document
def _p(p: float) -> str:
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


def key_figures(rest: pd.DataFrame, pairs: pd.DataFrame) -> dict:
    rated = rest[rest["is_rated"] == 1]
    city_counts = rest["city"].value_counts()
    india = rest[rest["country_name"] == "India"]
    small_india = india["city"].value_counts()
    return {
        "n": len(rest), "rated": len(rated), "unrated": int((rest["is_rated"] == 0).sum()),
        "india_share": 100 * len(india) / len(rest),
        "top4_cities": city_counts.head(4).index.tolist(),
        "top4_share": 100 * city_counts.head(4).sum() / len(rest),
        "india_cities": int(small_india.size),
        "india_cities_le_25": int((small_india <= 25).sum()),
        "rating_mean": rated["aggregate_rating"].mean(), "rating_median": rated["aggregate_rating"].median(),
        "rating_sd": rated["aggregate_rating"].std(), "rating_skew": rated["aggregate_rating"].skew(),
        "votes_median": rated["votes"].median(), "votes_mean": rated["votes"].mean(),
        "votes_skew": rated["votes"].skew(),
        "top_cuisine": pairs["cuisine"].value_counts().index[0],
        "top_cuisine_share": 100 * pairs["cuisine"].value_counts().iloc[0] / len(rest),
    }


def delivery_definition(rest: pd.DataFrame) -> str:
    """The one official 'online delivery vs rating' figure, and why the all-countries version is misleading."""
    rated = rest[rest["is_rated"] == 1]
    india = rated[rated["country_name"] == "India"].groupby("has_online_delivery")["aggregate_rating"]
    allc = rated.groupby("has_online_delivery")["aggregate_rating"].mean()
    abroad = rated[rated["country_name"] != "India"]
    m, n = india.mean(), india.size()
    return ("Online delivery vs rating, official figure (used in the report, the docs and the Power BI dashboard): "
            f"**India only, rated restaurants, mean rating: {m[1]:.2f} with delivery (n={n[1]:,}) vs {m[0]:.2f} "
            f"without (n={n[0]:,})** (SQL Q08; T4 above reports the medians of the same groups). Delivery exists only "
            f"in India and UAE, so an all-countries comparison ({allc[1]:.2f} vs {allc[0]:.2f}) is misleading: its "
            f"'no delivery' group also contains the {int((abroad['has_online_delivery'] == 0).sum()):,} rated "
            f"restaurants outside India without delivery, which average "
            f"{abroad[abroad['has_online_delivery'] == 0]['aggregate_rating'].mean():.2f}.")


def write_findings(rest: pd.DataFrame, pairs: pd.DataFrame, st: pd.DataFrame, figures: list[Path],
                   out: Path = FINDINGS_MD, source: str = "the MySQL database `restaurant_intelligence`") -> None:
    k = key_figures(rest, pairs)
    lines = [
        "# EDA Findings",
        "",
        f"*Generated by `src/eda.py` from {source}. All numbers are computed "
        "at run time. Statistical tests show association, not causation.*",
        "",
        "## Key figures",
        "",
        f"- Restaurants: **{k['n']:,}**; rated **{k['rated']:,}**; unrated **{k['unrated']:,}**.",
        f"- India accounts for **{k['india_share']:.1f}%** of restaurants.",
        f"- The four largest cities ({', '.join(k['top4_cities'])}) hold **{k['top4_share']:.1f}%** of all "
        f"restaurants. Of {k['india_cities']} Indian cities, **{k['india_cities_le_25']}** have 25 or fewer "
        "restaurants, which suggests Zomato listed only a small sample outside Delhi NCR.",
        f"- Ratings (rated only): mean **{k['rating_mean']:.2f}**, median {k['rating_median']:.2f}, "
        f"SD {k['rating_sd']:.2f}, skewness {k['rating_skew']:.2f}.",
        f"- Votes (rated only): median **{k['votes_median']:.0f}**, mean {k['votes_mean']:.1f}, "
        f"skewness {k['votes_skew']:.2f} (heavily right-skewed, so medians and rank-based tests are used).",
        f"- Most common cuisine: **{k['top_cuisine']}**, offered by {k['top_cuisine_share']:.1f}% of restaurants.",
        "",
        "## Statistical tests",
        "",
        "| # | Question | Test | Groups / n | Statistic | p-value | Effect size | Significant (α = 0.05) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(st.itertuples(index=False), start=1):
        lines.append(f"| T{i} | {r.question} | {r.test} | {r.groups} | {r.statistic:,} | {_p(r.p_value)} | "
                     f"{r.effect_measure} = {r.effect_size} | {'Yes' if r.significant_at_0_05 else 'No'} |")
    lines += [
        "",
        "Effect-size guide used in interpretation (rule of thumb): |rho| or |r| < 0.1 negligible, 0.1–0.3 small, "
        "0.3–0.5 moderate, > 0.5 large; Cramér's V < 0.1 negligible, 0.1–0.3 small, 0.3–0.5 moderate.",
        "",
        delivery_definition(rest),
        "",
        "## Figures",
        "",
    ]
    lines += [f"- `{p.relative_to(config.ROOT).as_posix()}`" for p in figures]
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def load_from_csv() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fallback without MySQL: the same rows and columns as v_restaurants (restaurants + country_name), read
    from the cleaned CSVs that MySQL itself is loaded from."""
    rest = pd.read_csv(config.PROCESSED_DIR / "zomato_clean.csv", encoding="utf-8")
    rest["country_name"] = rest["country"]
    pairs = pd.read_csv(config.PROCESSED_DIR / "restaurant_cuisines.csv", encoding="utf-8")[["restaurant_id", "cuisine"]]
    for col in ("aggregate_rating", "avg_cost_for_two", "votes_pct_in_country", "longitude", "latitude"):
        rest[col] = pd.to_numeric(rest[col], errors="coerce").astype(float)
    return rest, pairs


def run_eda(engine: Engine | None) -> dict:
    """EDA from MySQL; with engine=None (no MySQL) from the cleaned CSVs instead (same data)."""
    rest, pairs = load_from_mysql(engine) if engine is not None else load_from_csv()
    st = run_statistics(rest)
    st.rename(columns={"significant_at_0.05": "significant_at_0_05"}, inplace=True)
    STATS_CSV.parent.mkdir(parents=True, exist_ok=True)
    st.to_csv(STATS_CSV, index=False)
    figs = make_figures(rest, pairs)
    write_findings(rest, pairs, st, figs, **({} if engine is not None else {
        "source": "the cleaned CSV files (MySQL not available; same data as the MySQL tables)"}))
    return {"restaurants": rest, "pairs": pairs, "statistics": st, "figures": figs,
            "key_figures": key_figures(rest, pairs)}
