"""Data quality checks on the raw Zomato data (after country join).

Writes docs/data_quality_report.md. All numbers are computed at run time.
"""
from __future__ import annotations

import pandas as pd

from src import config
from src.cleaning import COUNTRY_NAME_FIXES, CURRENCY_FIXES
from src.data_loading import load_with_country

YES_NO_COLS = ["Has Table booking", "Has Online delivery", "Is delivering now", "Switch to order menu"]
TEXT_COLS = ["Restaurant Name", "City", "Address", "Locality", "Locality Verbose", "Cuisines"]
NON_ASCII = r"[^\x00-\x7f]"


MISSING_ACTIONS = {
    "Cuisines": "Fill with 'Unknown'; excluded from cuisine pairs table",
    "Restaurant ID": "Drop row (ID is the primary key)",
    "Aggregate rating": "Keep as missing (unrated)",
}


def _plain_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Use plain object/float columns so comparisons with missing values give False, not NA."""
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_numeric_dtype(out[c]) and not pd.api.types.is_bool_dtype(out[c]):
            out[c] = out[c].astype("float64")
        else:
            out[c] = out[c].astype(object).where(out[c].notna(), None)
    return out


def _pct(n: int, total: int) -> float:
    return round(100 * n / total, 2) if total else 0.0


def cost_outliers_by_currency(df: pd.DataFrame) -> pd.DataFrame:
    """IQR rule (> Q3 + 1.5*IQR) computed separately within each currency, positive costs only."""
    rows = []
    for (country, cur), g in df[df["Average Cost for two"] > 0].groupby(["Country", "Currency"]):
        c = g["Average Cost for two"]
        q1, q3 = c.quantile(0.25), c.quantile(0.75)
        upper = q3 + 1.5 * (q3 - q1)
        rows.append({
            "country": country, "currency": cur, "n": len(c),
            "min": int(c.min()), "median": float(c.median()), "max": int(c.max()),
            "iqr_upper_fence": float(upper), "outliers_above_fence": int((c > upper).sum()),
        })
    return pd.DataFrame(rows).sort_values("n", ascending=False).reset_index(drop=True)


def coordinate_issues(df: pd.DataFrame) -> dict[str, int]:
    zero_zero = (df["Longitude"] == 0) & (df["Latitude"] == 0)
    one_zero = ((df["Longitude"] == 0) ^ (df["Latitude"] == 0))
    out_of_range = (df["Latitude"].abs() > 90) | (df["Longitude"].abs() > 180)
    # far from city median: > 1 degree (~100 km) away, ignoring (0,0) rows
    valid = df[~zero_zero & ~one_zero].copy()
    med = valid.groupby("City")[["Latitude", "Longitude"]].transform("median")
    far = ((valid["Latitude"] - med["Latitude"]).abs() > 1) | ((valid["Longitude"] - med["Longitude"]).abs() > 1)
    return {
        "zero_zero": int(zero_zero.sum()),
        "one_coord_zero": int(one_zero.sum()),
        "out_of_range": int(out_of_range.sum()),
        "far_from_city_median": int(far.sum()),
    }


def run_checks(df: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict]:
    """Return (checks table, detail dict)."""
    if df is None:
        df = load_with_country()
    df = _plain_dtypes(df)
    n = len(df)
    checks: list[dict] = []

    def add(check, column, count, action, severity="Info"):
        checks.append({"check": check, "column": column, "count": int(count),
                       "pct_of_rows": _pct(count, n), "severity": severity, "action": action})

    # 1. Missing values
    missing = df.isna().sum()
    for col, miss in missing.items():
        if miss:
            action = MISSING_ACTIONS.get(col, "Keep as missing")
            add("Missing values", col, miss, action, "Low")
    add("Columns with no missing values", "all", int((missing == 0).sum()), "None needed")

    # 2. Duplicates
    add("Duplicate rows (all columns)", "all", df.duplicated().sum(), "Drop if any")
    add("Duplicate Restaurant ID", "Restaurant ID", df["Restaurant ID"].duplicated().sum(), "Drop if any")
    add("Duplicate name + address", "Restaurant Name, Address",
        df.duplicated(["Restaurant Name", "Address"]).sum(), "Review if any")
    add("Repeated restaurant names (chains/branches)", "Restaurant Name",
        df["Restaurant Name"].duplicated().sum(), "Keep: different branches, not duplicates")

    # 3. Ratings
    not_rated = df["Rating text"].eq("Not rated")
    zero = df["Aggregate rating"].eq(0)
    add("Rating = 0 with 'Not rated'", "Aggregate rating", (zero & not_rated).sum(),
        "Treat as missing (NaN) + is_rated flag", "High")
    add("Rating = 0 but rating text not 'Not rated'", "Aggregate rating", (zero & ~not_rated).sum(), "Review if any")
    add("'Not rated' but votes > 0", "Votes", (not_rated & df["Votes"].gt(0)).sum(),
        "Keep votes; rating stays missing (too few votes to publish a rating)", "Medium")
    add("Rated but votes = 0", "Votes", (~not_rated & df["Votes"].eq(0)).sum(), "Review if any")
    add("Rating outside 0-5", "Aggregate rating",
        (df["Aggregate rating"].notna() & ~df["Aggregate rating"].between(0, 5)).sum(),
        "Set to missing if any")
    add("Negative votes", "Votes", df["Votes"].lt(0).sum(), "Drop/flag if any")
    band = df.groupby("Rating text")["Aggregate rating"].agg(["min", "max"])
    add("Rating text <-> colour one-to-one mismatch", "Rating text, Rating color",
        (df.groupby("Rating text")["Rating color"].nunique() > 1).sum(), "None: derived fields")

    # 4. Costs
    zero_cost = df["Average Cost for two"].le(0)
    add("Zero or negative cost for two", "Average Cost for two", zero_cost.sum(),
        "Set to missing (NaN) + flag", "Medium")
    outl = cost_outliers_by_currency(df)
    add("Cost outliers above IQR fence (within currency)", "Average Cost for two",
        outl["outliers_above_fence"].sum(), "Keep + flag (expensive places are real)", "Low")

    # 5. Currency labelling
    country_fixed = df["Country"].replace(COUNTRY_NAME_FIXES)
    for wrong, right in COUNTRY_NAME_FIXES.items():
        add(f"Country spelled '{wrong}'", "Country", df["Country"].eq(wrong).sum(),
            f"Correct to '{right}'", "Low")
    for (country, wrong), right in CURRENCY_FIXES.items():
        m = country_fixed.eq(country) & df["Currency"].eq(wrong)
        add(f"{country} rows labelled '{wrong}'", "Currency", m.sum(), f"Relabel to '{right}' + log", "Medium")
    add("Country code not in lookup (country 'Unknown')", "Country Code",
        df["Country"].eq("Unknown").sum(), "Keep; country shown as 'Unknown'", "Medium")
    dollar_countries = sorted(df.loc[df["Currency"].eq("Dollar($)"), "Country"].unique())
    add(f"'Dollar($)' shared by {len(dollar_countries)} countries", "Currency",
        df["Currency"].eq("Dollar($)").sum(), "Keep; always group cost by country", "Low")

    # 6. Coordinates
    coords = coordinate_issues(df)
    add("Coordinates (0, 0)", "Longitude, Latitude", coords["zero_zero"],
        "Set to missing (NaN) + has_valid_coords flag", "High")
    add("Exactly one coordinate = 0", "Longitude, Latitude", coords["one_coord_zero"],
        "Set to missing (NaN) + flag", "Medium")
    add("Coordinates outside valid range", "Longitude, Latitude", coords["out_of_range"], "Drop/flag if any")
    add("Coordinates > 1 degree from city median", "Longitude, Latitude", coords["far_from_city_median"],
        "Keep + flag for map review", "Low")

    # 7. Yes/No consistency
    for col in YES_NO_COLS:
        s = df[col].dropna().astype(str).str.strip()
        add("Values other than exactly 'Yes'/'No'", col, (~s.isin(["Yes", "No"])).sum(),
            "Convert Yes/No to 1/0 (case-insensitive); others -> empty")
    constant = [c for c in df.columns if df[c].nunique(dropna=False) <= 1]
    add("Constant columns (single value): " + (", ".join(constant) or "none"), "all", len(constant),
        "Keep in clean file; exclude from analysis", "Low")
    add("Delivering now = Yes but no online delivery", "Is delivering now",
        (df["Is delivering now"].eq("Yes") & df["Has Online delivery"].eq("No")).sum(), "Review if any")

    # 8. City names / text
    cities = df["City"].dropna().astype(str)
    add("City names with leading/trailing spaces", "City", (cities != cities.str.strip()).sum(), "Strip")
    add("City names differing only by case", "City",
        cities.nunique() - cities.str.strip().str.lower().nunique(), "Normalise if any")
    garbled_cities = sorted(cities[cities.str.contains(NON_ASCII, regex=True, na=False)].unique())
    add("City names with garbled characters", "City", len(garbled_cities),
        "Keep source spelling (consistent within dataset)", "Low")
    city_country = df.groupby("City")["Country"].nunique()
    add("City name used in more than one country", "City", (city_country > 1).sum(), "Review if any")
    for col in TEXT_COLS:
        s = df[col].dropna()
        ws = (s != s.str.strip()) | s.str.contains("  ", regex=False)
        if ws.sum():
            add("Extra whitespace (leading/trailing/double)", col, ws.sum(), "Strip and collapse spaces")
    ctrl = df[TEXT_COLS + ["Currency"]].fillna("").apply(
        lambda c: c.astype(str).str.contains(r"[\x80-\x9f]", regex=True)).sum().sum()
    add("Cells with invisible control characters (U+0080-U+009F)", "text columns + Currency", ctrl,
        "Remove (they break exact matching, e.g. 'Pounds(\\x8c£)')", "Medium")
    garbled_rows = df[TEXT_COLS].fillna("").apply(lambda c: c.str.contains(NON_ASCII, regex=True)).any(axis=1)
    add("Rows with garbled (non-ASCII) text in name/address fields", "text columns", garbled_rows.sum(),
        "Keep as-is: source corruption is not reversibly decodable", "Low")

    # 9. Structural gaps
    date_like = [c for c in df.columns if any(k in c.lower() for k in ("date", "year", "opened"))]
    type_like = [c for c in df.columns if "type" in c.lower() or "establishment" in c.lower()]
    add("Date / opening-year columns found: " + (", ".join(date_like) or "none"), "-", len(date_like),
        "If none: no time trends possible ('openings by year' dropped)", "High")
    add("Restaurant-type columns found: " + (", ".join(type_like) or "none"), "-", len(type_like),
        "If none: recorded as limitation", "Medium")

    details = {
        "n_rows": n,
        "rating_bands": band,
        "cost_outliers": outl,
        "coords_by_country": df[(df["Longitude"] == 0) & (df["Latitude"] == 0)].groupby("Country").size(),
        "zero_cost_rows": df.loc[zero_cost, ["Restaurant ID", "Restaurant Name", "Country", "City",
                                             "Currency", "Price range"]],
        "garbled_cities": garbled_cities,
        "dollar_countries": dollar_countries,
        "not_rated_votes": df.loc[not_rated, "Votes"].describe(),
        "yes_no_values": {c: df[c].value_counts().to_dict() for c in YES_NO_COLS},
    }
    return pd.DataFrame(checks), details


def _md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        out.append("| " + " | ".join(str(v).replace("|", "/") for v in row) + " |")
    return "\n".join(out)


def write_report(checks: pd.DataFrame, details: dict, out_path=config.DEFAULT_PATHS.quality_report_md,
                 source_name: str = "data/raw/zomato.csv") -> None:
    d = details
    zc = d["zero_cost_rows"]
    lines = [
        "# Data Quality Report",
        "",
        f"*Generated by `src/data_quality.py` from `{source_name}` + `Country-Code.xlsx`. "
        "All figures computed from the loaded data at run time.*",
        "",
        f"Rows checked: **{d['n_rows']:,}**",
        "",
        "## Summary of checks",
        "",
        _md_table(checks),
        "",
        "## Details",
        "",
        "### Rating bands (rating text vs aggregate rating)",
        "",
        _md_table(d["rating_bands"].reset_index()),
        "",
        "Rating text and rating colour are fully determined by the numeric rating, so they are derived fields.",
        "",
        "### Votes among 'Not rated' restaurants",
        "",
        _md_table(d["not_rated_votes"].round(2).reset_index().rename(columns={"index": "stat"})),
        "",
        "### Cost for two by currency (positive costs only, local currency)",
        "",
        _md_table(d["cost_outliers"]),
        "",
        f"Countries sharing the 'Dollar($)' label: {', '.join(d['dollar_countries'])}.",
        "",
        f"### Rows with zero cost for two ({len(zc)})",
        "",
        _md_table(zc.groupby(["Country", "Currency"]).size().reset_index(name="rows")),
        "",
        "### Coordinates (0, 0) by country",
        "",
        _md_table(d["coords_by_country"].reset_index(name="rows")),
        "",
        "### Garbled city names (kept as in source)",
        "",
        ", ".join(f"`{c}`" for c in d["garbled_cities"]),
        "",
        "### Text encoding note",
        "",
        f"File encoding used: `{details.get('encoding', 'n/a')}`. Non-ASCII text cells are counted above. "
        "For the Kaggle file, accented characters were already corrupted before publication "
        "(e.g. 'Café' appears as 'Cafí©'); common decode/re-encode chains (latin-1, cp1252, mac_roman, "
        "cp437, cp850, utf-8) did not recover the original text, so values are kept as-is. This affects "
        "display names only; grouping is unaffected because the corruption is consistent.",
        "",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    from src.data_loading import detect_encoding
    checks, details = run_checks()
    details["encoding"] = detect_encoding()
    write_report(checks, details)
    return checks, details


if __name__ == "__main__":
    c, d = main()
    pd.set_option("display.width", 220)
    print(c[["check", "column", "count", "pct_of_rows", "severity"]].to_string(index=False))
    print()
    print(d["cost_outliers"].to_string(index=False))
    print(d["zero_cost_rows"].to_string(index=False))
