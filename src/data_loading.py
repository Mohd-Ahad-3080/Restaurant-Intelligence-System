"""Load a raw Zomato-format CSV (Kaggle file or any file with the same columns)
and join country names. Raw files are never modified.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src import config
from src.schema import SchemaError, ValidationResult, validate

# Tried in order. The Kaggle zomato.csv is not valid UTF-8; latin-1 can decode any byte.
ENCODINGS = ("utf-8-sig", "latin-1")
UNKNOWN_COUNTRY = "Unknown"


def detect_encoding(path: Path = config.RAW_ZOMATO_CSV) -> str:
    """Return the first encoding in ENCODINGS that decodes the whole file."""
    raw = Path(path).read_bytes()
    for enc in ENCODINGS:
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    raise SchemaError(f"Could not read {path}: unknown text encoding.")


def load_raw_zomato(path: Path = config.RAW_ZOMATO_CSV) -> pd.DataFrame:
    """Load the CSV exactly as published (original column names, no type changes)."""
    path = Path(path)
    if not path.exists():
        raise SchemaError(
            f"Input file not found: {path}\n"
            "For the Kaggle data, download 'Zomato Restaurants Data' (Shruti Mehta) and place "
            "zomato.csv in data/raw/."
        )
    try:
        return pd.read_csv(path, encoding=detect_encoding(path))
    except pd.errors.EmptyDataError:
        raise SchemaError(f"The input file {path.name} is empty.") from None
    except pd.errors.ParserError as e:
        raise SchemaError(f"The input file {path.name} is not a valid CSV: {e}") from None


def load_country_codes(path: Path = config.RAW_COUNTRY_XLSX) -> pd.DataFrame:
    """Load the country lookup (columns: Country Code, Country)."""
    path = Path(path)
    if not path.exists():
        raise SchemaError(f"Country lookup not found: {path}. Place Country-Code.xlsx in data/raw/.")
    cc = pd.read_excel(path)
    cc.columns = [str(c).strip() for c in cc.columns]
    if not {"Country Code", "Country"} <= set(cc.columns):
        raise SchemaError(f"{path.name} must have columns 'Country Code' and 'Country'.")
    cc = cc[["Country Code", "Country"]].dropna()
    cc["Country Code"] = pd.to_numeric(cc["Country Code"], errors="coerce").astype("Int64")
    return cc.drop_duplicates("Country Code")


def load_validated(path: Path = config.RAW_ZOMATO_CSV,
                   countries: Path = config.RAW_COUNTRY_XLSX) -> ValidationResult:
    """Load, validate the schema, and join country names.

    Country codes missing from the lookup get Country = 'Unknown' (with a warning).
    The Country column is placed right after Country Code.
    """
    path = Path(path)
    result = validate(load_raw_zomato(path), source=f"file '{path.name}'")
    df = result.df
    cc = load_country_codes(countries)
    merged = df.merge(cc, on="Country Code", how="left", validate="many_to_one")
    unmatched = merged["Country"].isna()
    if unmatched.any():
        codes = sorted(merged.loc[unmatched, "Country Code"].dropna().unique().tolist())
        result.warnings.append(f"{unmatched.sum():,} row(s) have country codes not in the lookup "
                               f"{codes}; country set to '{UNKNOWN_COUNTRY}'.")
        merged["Country"] = merged["Country"].fillna(UNKNOWN_COUNTRY)
    merged["Country"] = merged["Country"].astype("string")
    cols = list(df.columns)
    cols.insert(cols.index("Country Code") + 1, "Country")
    result.df = merged[cols]
    return result


def load_with_country(path: Path = config.RAW_ZOMATO_CSV,
                      countries: Path = config.RAW_COUNTRY_XLSX) -> pd.DataFrame:
    """Convenience wrapper returning only the DataFrame."""
    return load_validated(path, countries).df


if __name__ == "__main__":
    res = load_validated()
    data = res.df
    print(f"Encoding used: {detect_encoding()}")
    print(f"Rows: {len(data):,}  Columns: {data.shape[1]}")
    for w in res.warnings:
        print("WARNING:", w)
    print(data["Country"].value_counts().to_string())
