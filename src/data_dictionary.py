"""Generate docs/data_dictionary.md from the real data.

Descriptions are written by hand; every number (types, missing counts, unique counts,
examples) is computed from the loaded data at run time.
"""
from __future__ import annotations

import pandas as pd

from src import config
from src.data_loading import detect_encoding, load_raw_zomato, load_with_country

# raw name -> (clean name, description, notes)
COLUMNS: dict[str, tuple[str, str, str]] = {
    "Restaurant ID": ("restaurant_id", "Zomato's unique identifier for the restaurant.",
                      "Primary key. Verified unique."),
    "Restaurant Name": ("restaurant_name", "Name of the restaurant.",
                        "Not unique: chains appear many times. Some names contain garbled accented "
                        "characters from the source file (e.g. 'Cafí©' for 'Café')."),
    "Country Code": ("country_code", "Numeric country code used by Zomato.",
                     "Join key to Country-Code.xlsx."),
    "Country": ("country", "Country name, joined from Country-Code.xlsx.",
                "Not in zomato.csv. Known misspellings (e.g. 'Phillipines') corrected in cleaning; "
                "codes missing from the lookup become 'Unknown'."),
    "City": ("city", "City where the restaurant is located.",
             "A few names garbled in source (e.g. 'Sí£o Paulo', 'ÛÁstanbul')."),
    "Address": ("address", "Full street address.", "Free text."),
    "Locality": ("locality", "Neighbourhood / area within the city.", "Free text; used for area analysis."),
    "Locality Verbose": ("locality_verbose", "Locality followed by city.",
                         "Mostly redundant with locality + city."),
    "Longitude": ("longitude", "Longitude in decimal degrees.", "Some rows are (0, 0) = missing; see quality report."),
    "Latitude": ("latitude", "Latitude in decimal degrees.", "Some rows are (0, 0) = missing; see quality report."),
    "Cuisines": ("cuisines", "Comma-separated list of cuisines served.",
                 "Exploded into restaurant_cuisines.csv (one row per restaurant-cuisine pair)."),
    "Average Cost for two": ("avg_cost_for_two", "Typical cost of a meal for two people.",
                             "In LOCAL currency (see currency). Do not compare raw values across countries; use "
                             "price_range, or the derived avg_cost_for_two_usd (approximate, World Bank 2017 rates, "
                             "see docs/currency_and_costs.md)."),
    "Currency": ("currency", "Currency of avg_cost_for_two.",
                 "Philippines rows are labelled 'Botswana Pula(P)' in source (source error). "
                 "'Dollar($)' is shared by Australia, Canada, Singapore and US (different dollars)."),
    "Has Table booking": ("has_table_booking", "Whether table booking is offered (Yes/No).", "Converted to 1/0."),
    "Has Online delivery": ("has_online_delivery", "Whether online delivery is offered (Yes/No).", "Converted to 1/0."),
    "Is delivering now": ("is_delivering_now", "Whether delivering at the moment the data was scraped (Yes/No).",
                          "Snapshot-in-time flag; converted to 1/0."),
    "Switch to order menu": ("switch_to_order_menu", "Whether the 'switch to order menu' option is shown (Yes/No).",
                             "Converted to 1/0."),
    "Price range": ("price_range", "Zomato price band, 1 (cheapest) to 4 (most expensive).",
                    "Comparable across countries; preferred over cost for cross-country analysis."),
    "Aggregate rating": ("aggregate_rating", "Average user rating, 0-5 scale.",
                         "0 together with rating_text 'Not rated' means MISSING, not a real zero."),
    "Rating color": ("rating_color", "Colour band shown for the rating.",
                     "Fully determined by aggregate_rating (derived field)."),
    "Rating text": ("rating_text", "Text band for the rating (Poor ... Excellent, Not rated).",
                    "Fully determined by aggregate_rating (derived field)."),
    "Votes": ("votes", "Number of user votes/ratings received.", "Highly right-skewed."),
}


def _examples(s: pd.Series, n: int = 3) -> str:
    vals = s.dropna().unique()[:n]
    return "; ".join(str(v).replace("|", "/") for v in vals)


def build_dictionary(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for raw, (clean, desc, notes) in COLUMNS.items():
        s = df[raw]
        if s.nunique(dropna=False) <= 1:
            notes += " Constant in this file (single value) - carries no information."
        rows.append({
            "raw_name": raw,
            "clean_name": clean,
            "dtype": str(s.dtype),
            "description": desc,
            "example_values": _examples(s),
            "missing_count": int(s.isna().sum()),
            "unique_values": int(s.nunique()),
            "notes": notes,
        })
    return pd.DataFrame(rows)


def write_markdown(dd: pd.DataFrame, df: pd.DataFrame, input_path=config.RAW_ZOMATO_CSV,
                   out_path=config.DEFAULT_PATHS.data_dictionary_md) -> None:
    raw = load_raw_zomato(input_path)
    date_like = [c for c in raw.columns if any(k in str(c).lower() for k in ("date", "year", "opened"))]
    type_like = [c for c in raw.columns if "type" in str(c).lower()]
    source = "Kaggle, \"Zomato Restaurants Data\" by Shruti Mehta (secondary data)"
    licence = "**CC0: Public Domain** (as stated on the Kaggle dataset page)"
    enc = detect_encoding(input_path)
    lines = [
        "# Data Dictionary",
        "",
        "*Generated by `src/data_dictionary.py` from the loaded data. Do not edit numbers by hand.*",
        "",
        "## Dataset overview",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Source | {source} |",
        f"| Licence | {licence} |",
        f"| Files | `{input_path.name}`, `Country-Code.xlsx` |",
        f"| Encoding | `{enc}`" + (" (file is not valid UTF-8)" if enc != "utf-8-sig" else "") + " |",
        f"| Rows | {len(raw):,} |",
        f"| Columns in input file | {raw.shape[1]} |",
        f"| Columns after country join | {df.shape[1]} |",
        f"| Countries | {df['Country'].nunique()} |",
        f"| Cities | {df['City'].nunique()} |",
        "| Date / opening-year column | " + (", ".join(date_like) or "**None** (no time dimension)") + " |",
        "| Restaurant-type column | " + (", ".join(type_like) or "**None**") + " |",
        "",
        "## Columns",
        "",
        "| Raw name | Clean name | Type (raw) | Description | Example values | Missing | Unique | Notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in dd.itertuples(index=False):
        lines.append(f"| {r.raw_name} | `{r.clean_name}` | {r.dtype} | {r.description} | {r.example_values} | "
                     f"{r.missing_count} | {r.unique_values:,} | {r.notes} |")
    lines += [
        "",
        "## Derived files",
        "",
        "- `data/processed/zomato_clean.csv`: one row per restaurant, snake_case columns above plus cleaning flags.",
        "- `data/processed/restaurant_cuisines.csv`: one row per (restaurant_id, cuisine) pair.",
        "",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> pd.DataFrame:
    df = load_with_country()
    dd = build_dictionary(df)
    write_markdown(dd, df)
    return dd


if __name__ == "__main__":
    out = main()
    print(out[["raw_name", "clean_name", "dtype", "missing_count", "unique_values"]].to_string(index=False))
