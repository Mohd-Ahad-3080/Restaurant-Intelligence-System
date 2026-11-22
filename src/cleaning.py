"""Clean a validated Zomato-format dataset.

Every step records how many rows/cells it touched in a cleaning log, so the
cleaned file can always be traced back to the raw file. Works on any input
file with the expected columns (nothing here depends on the Kaggle numbers).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.target import add_popularity_class

RENAME = {
    "Restaurant ID": "restaurant_id", "Restaurant Name": "restaurant_name",
    "Country Code": "country_code", "Country": "country", "City": "city", "Address": "address",
    "Locality": "locality", "Locality Verbose": "locality_verbose", "Longitude": "longitude",
    "Latitude": "latitude", "Cuisines": "cuisines", "Average Cost for two": "avg_cost_for_two",
    "Currency": "currency", "Has Table booking": "has_table_booking",
    "Has Online delivery": "has_online_delivery", "Is delivering now": "is_delivering_now",
    "Switch to order menu": "switch_to_order_menu", "Price range": "price_range",
    "Aggregate rating": "aggregate_rating", "Rating color": "rating_color",
    "Rating text": "rating_text", "Votes": "votes",
}
TEXT_COLS = ["restaurant_name", "city", "address", "locality", "locality_verbose", "cuisines",
             "currency", "rating_text", "rating_color", "country"]
YES_NO_COLS = ["has_table_booking", "has_online_delivery", "is_delivering_now", "switch_to_order_menu"]

# Known source errors (rules, not numbers). Keys are matched exactly.
COUNTRY_NAME_FIXES = {"Phillipines": "Philippines"}
# (country after name fix, wrong currency label) -> correct label.
CURRENCY_FIXES = {("Philippines", "Botswana Pula(P)"): "Philippine Peso(P)"}
CURRENCY_TYPOS = {"Emirati Diram(AED)": "Emirati Dirham (AED)"}   # spelling error in the Kaggle source

INVISIBLE_CONTROL_CHARS = r"[\x80-\x9f]"  # C1 control characters left by the source's encoding damage
NOT_RATED_TEXT = "not rated"
UNKNOWN_CUISINE = "Unknown"
PRICE_RANGES = (1, 2, 3, 4)


class CleaningLog:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, step: str, column: str, affected: int, rows_after: int, reason: str):
        self.rows.append({"step_no": len(self.rows) + 1, "step": step, "column": column,
                          "rows_affected": int(affected), "rows_after": int(rows_after),
                          "reason": reason})

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)


def cost_outlier_flags(df: pd.DataFrame, cost: str = "avg_cost_for_two",
                       group: tuple[str, str] = ("country", "currency")) -> pd.Series:
    """True where cost > Q3 + 1.5*IQR within its country+currency group (positive costs only)."""
    valid = df[cost].where(df[cost] > 0)
    keys = [df[g] for g in group]
    q1 = valid.groupby(keys).transform(lambda s: s.quantile(0.25))
    q3 = valid.groupby(keys).transform(lambda s: s.quantile(0.75))
    return (valid > q3 + 1.5 * (q3 - q1)).fillna(False)


def _collapse_spaces(s: pd.Series) -> pd.Series:
    return s.str.strip().str.replace(r"\s{2,}", " ", regex=True)


def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (clean restaurants, restaurant-cuisine pairs, cleaning log)."""
    log = CleaningLog()
    df = raw.copy()
    log.add("Load validated raw data", "all", len(df), len(df), "Starting row count")

    # --- Row-level fixes -------------------------------------------------------------
    before = len(df)
    df = df.drop_duplicates()
    log.add("Drop exact duplicate rows", "all", before - len(df), len(df), "Identical rows add no information")

    before = len(df)
    df = df[df["Restaurant ID"].notna()]
    log.add("Drop rows with missing Restaurant ID", "Restaurant ID", before - len(df), len(df),
            "ID is the primary key")

    before = len(df)
    df = df.drop_duplicates(subset="Restaurant ID", keep="first")
    log.add("Drop duplicate Restaurant IDs (keep first)", "Restaurant ID", before - len(df), len(df),
            "ID must be unique")

    df = df.rename(columns=RENAME)[list(RENAME.values())]  # extra columns are dropped
    log.add("Rename columns to snake_case", "all", 0, len(df), "Consistent names for SQL/Python")
    n = len(df)

    # --- Text tidy-up ----------------------------------------------------------------
    changed = 0
    for col in TEXT_COLS:
        s = df[col].astype("string")
        new = s.str.replace(INVISIBLE_CONTROL_CHARS, "", regex=True)
        changed += int(((s != new) & s.notna()).sum())
        df[col] = new
    log.add("Remove invisible control characters (U+0080-U+009F)", ", ".join(TEXT_COLS), changed, n,
            "Cells changed; e.g. 'Pounds(\\x8c£)' -> 'Pounds(£)' (encoding debris, never visible)")

    changed = 0
    for col in TEXT_COLS:
        s = df[col].astype("string")
        new = _collapse_spaces(s)
        changed += int(((s != new) & s.notna()).sum())
        df[col] = new
    log.add("Trim and collapse extra spaces in text", ", ".join(TEXT_COLS), changed, n,
            "Cells changed (not rows)")

    for wrong, right in COUNTRY_NAME_FIXES.items():
        m = df["country"].eq(wrong).fillna(False)
        df.loc[m, "country"] = right
        log.add(f"Fix country spelling '{wrong}' -> '{right}'", "country", m.sum(), n,
                "Spelling error in Country-Code.xlsx")

    for (country, wrong), right in CURRENCY_FIXES.items():
        m = (df["country"].eq(country) & df["currency"].eq(wrong)).fillna(False)
        df.loc[m, "currency"] = right
        log.add(f"Relabel currency '{wrong}' -> '{right}' for {country}", "currency", m.sum(), n,
                "Source mislabel: currency label does not match the country")
    for wrong, right in CURRENCY_TYPOS.items():
        m = df["currency"].eq(wrong).fillna(False)
        df.loc[m, "currency"] = right
        log.add(f"Fix currency spelling '{wrong}' -> '{right}'", "currency", m.sum(), n,
                "Source typo in the currency name ('Diram' -> 'Dirham')")

    # --- Cuisines -----------------------------------------------------------------------
    miss = df["cuisines"].isna() | df["cuisines"].eq("")
    df.loc[miss, "cuisines"] = UNKNOWN_CUISINE
    log.add("Fill missing cuisines with 'Unknown'", "cuisines", miss.sum(), n,
            "Keeps restaurant; excluded from cuisine pairs table")
    split = df["cuisines"].str.split(",").apply(lambda parts: [p.strip() for p in parts if p.strip()])
    repeated = split.apply(lambda parts: len(parts) != len(set(parts)))
    df["cuisines"] = split.apply(lambda parts: ", ".join(dict.fromkeys(parts)))  # keeps first-seen order
    log.add("Remove a cuisine listed twice for the same restaurant", "cuisines", repeated.sum(), n,
            "e.g. 'Chinese, ..., Chinese' counted once")
    df["n_cuisines"] = np.where(df["cuisines"].eq(UNKNOWN_CUISINE), 0,
                                df["cuisines"].str.count(",") + 1)

    # --- Yes/No -> 1/0 ------------------------------------------------------------------
    for col in YES_NO_COLS:
        s = df[col].astype("string").str.strip().str.lower()
        mapped = s.map({"yes": 1, "no": 0})
        invalid = s.notna() & mapped.isna()
        df[col] = pd.array(mapped, dtype="Int64")
        log.add("Convert Yes/No to 1/0", col, invalid.sum(), n,
                "Rows affected = values that were not Yes/No (set to empty)")

    # --- Ratings and votes --------------------------------------------------------------
    rt = df["rating_text"].str.lower()
    not_rated = (rt.eq(NOT_RATED_TEXT) | df["aggregate_rating"].eq(0)).fillna(False)
    df.loc[not_rated, "aggregate_rating"] = np.nan
    log.add("Rating 0 / 'Not rated' -> missing", "aggregate_rating", not_rated.sum(), n,
            "A zero means no rating yet, not a real score")
    bad = ~df["aggregate_rating"].between(0, 5) & df["aggregate_rating"].notna()
    df.loc[bad, "aggregate_rating"] = np.nan
    log.add("Ratings outside 0-5 -> missing", "aggregate_rating", bad.sum(), n, "Impossible values")
    df["is_rated"] = df["aggregate_rating"].notna().astype("Int64")

    bad = df["votes"].lt(0).fillna(False)
    df.loc[bad, "votes"] = pd.NA
    log.add("Negative votes -> missing", "votes", bad.sum(), n, "Impossible values")

    # --- Price & cost -------------------------------------------------------------------
    bad = ~df["price_range"].isin(PRICE_RANGES) & df["price_range"].notna()
    df.loc[bad, "price_range"] = pd.NA
    log.add("Price range outside 1-4 -> missing", "price_range", bad.sum(), n, "Zomato bands are 1-4")

    df["avg_cost_for_two"] = df["avg_cost_for_two"].astype("Float64")
    bad = df["avg_cost_for_two"].le(0).fillna(False)
    df.loc[bad, "avg_cost_for_two"] = np.nan
    log.add("Cost for two <= 0 -> missing", "avg_cost_for_two", bad.sum(), n, "A meal cannot cost 0")
    df["is_cost_outlier"] = cost_outlier_flags(df).astype("Int64")
    log.add("Flag cost outliers (IQR, within country + currency)", "is_cost_outlier",
            df["is_cost_outlier"].sum(), n, "Flag only; expensive restaurants are real")
    from src.currency import add_cost_usd
    df = add_cost_usd(df)
    log.add("Add approximate cost in USD (World Bank 2017 official rates, by country)", "avg_cost_for_two_usd",
            df["avg_cost_for_two_usd"].notna().sum(), n,
            "Rows affected = rows with a cost; for cross-country comparison only, local cost is kept")

    # --- Coordinates --------------------------------------------------------------------
    lon, lat = df["longitude"], df["latitude"]
    bad = (lon.eq(0) | lat.eq(0) | lon.isna() | lat.isna() | (lat.abs() > 90) | (lon.abs() > 180)).fillna(True)
    df.loc[bad, ["longitude", "latitude"]] = np.nan
    df["has_valid_coords"] = (~bad).astype("Int64")
    log.add("Zero / out-of-range coordinates -> missing", "longitude, latitude", bad.sum(), n,
            "(0,0) is a placeholder, not a real location")

    # --- Target -------------------------------------------------------------------------
    df = add_popularity_class(df)
    log.add("Add popularity_class (Option B)", "popularity_class", df["popularity_class"].notna().sum(), n,
            "Rows affected = rated restaurants that received a class")

    log.add("Final cleaned row count", "all", 0, len(df), "Rows in zomato_clean.csv")

    pairs = (df.loc[df["cuisines"] != UNKNOWN_CUISINE, ["restaurant_id", "cuisines"]]
             .assign(cuisine=lambda d: d["cuisines"].str.split(", "))
             .explode("cuisine")[["restaurant_id", "cuisine"]]
             .drop_duplicates().reset_index(drop=True))
    return df.reset_index(drop=True), pairs, log.to_frame()
