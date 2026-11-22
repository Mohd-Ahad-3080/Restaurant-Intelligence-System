"""Schema validation for a raw Zomato-format CSV.

Goal: a wrong file produces a clear, plain-language message instead of a crash.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# Columns the pipeline cannot work without, and the type each must hold.
REQUIRED_COLUMNS: dict[str, str] = {
    "Restaurant ID": "integer",
    "Restaurant Name": "text",
    "Country Code": "integer",
    "City": "text",
    "Locality": "text",
    "Longitude": "number",
    "Latitude": "number",
    "Cuisines": "text",
    "Average Cost for two": "number",
    "Currency": "text",
    "Has Table booking": "yes/no",
    "Has Online delivery": "yes/no",
    "Price range": "integer",
    "Aggregate rating": "number",
    "Rating text": "text",
    "Votes": "integer",
}

# Columns that are nice to have. If missing they are added as empty, with a warning.
OPTIONAL_COLUMNS: dict[str, str] = {
    "Address": "text",
    "Locality Verbose": "text",
    "Is delivering now": "yes/no",
    "Switch to order menu": "yes/no",
    "Rating color": "text",
}

ALL_COLUMNS = {**REQUIRED_COLUMNS, **OPTIONAL_COLUMNS}

# A numeric column is "wrongly typed" if more than this share of its non-empty values
# cannot be read as numbers. Below it, the bad cells are set to empty and reported.
MAX_BAD_NUMERIC_SHARE = 0.05


class SchemaError(ValueError):
    """Raised when the input file does not match the expected format."""


@dataclass
class ValidationResult:
    df: pd.DataFrame
    warnings: list[str] = field(default_factory=list)


def _normalise_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Match headers to the expected names ignoring case and surrounding spaces."""
    lookup = {name.strip().lower(): name for name in ALL_COLUMNS}
    renamed = {c: lookup.get(str(c).strip().lower(), str(c).strip()) for c in df.columns}
    return df.rename(columns=renamed)


def _examples(values: pd.Series, n: int = 3) -> str:
    return ", ".join(repr(v) for v in values.head(n).tolist())


def validate(df: pd.DataFrame, source: str = "input file") -> ValidationResult:
    """Check columns and types. Returns a copy with numeric columns converted.

    Raises SchemaError listing every problem found.
    """
    if df is None or len(df) == 0:
        raise SchemaError(f"The {source} has no data rows.")

    df = _normalise_headers(df.copy())
    errors: list[str] = []
    warnings: list[str] = []

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        errors.append("Missing required column(s): " + ", ".join(f"'{c}'" for c in missing))

    if df.columns.duplicated().any():
        dups = sorted(set(df.columns[df.columns.duplicated()]))
        errors.append("Duplicate column name(s): " + ", ".join(f"'{c}'" for c in dups))

    for col in OPTIONAL_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
            warnings.append(f"Optional column '{col}' not found; added as empty.")

    extra = [c for c in df.columns if c not in ALL_COLUMNS]
    if extra:
        warnings.append("Extra column(s) ignored: " + ", ".join(f"'{c}'" for c in extra))

    if errors:  # cannot type-check columns that are absent / duplicated
        raise SchemaError(_format(source, errors))

    for col, kind in ALL_COLUMNS.items():
        s = df[col]
        if kind in ("integer", "number"):
            present = s.notna() & (s.astype(str).str.strip() != "")
            num = pd.to_numeric(s.where(present), errors="coerce")
            bad = present & num.isna()
            share = bad.sum() / max(int(present.sum()), 1)
            if share > MAX_BAD_NUMERIC_SHARE:
                errors.append(f"Column '{col}' should contain {kind}s, but {bad.sum():,} of "
                              f"{int(present.sum()):,} values are not numbers "
                              f"(e.g. {_examples(s[bad])}).")
                continue
            if bad.any():
                warnings.append(f"Column '{col}': {bad.sum():,} non-numeric value(s) set to empty "
                                f"(e.g. {_examples(s[bad])}).")
            if kind == "integer":
                frac = num.notna() & (num != num.round())
                if frac.any():
                    errors.append(f"Column '{col}' should contain whole numbers, but {frac.sum():,} "
                                  f"value(s) have decimals (e.g. {_examples(num[frac])}).")
                    continue
                num = num.astype("Int64")
            df[col] = num
        elif kind == "yes/no" and col in REQUIRED_COLUMNS:
            vals = s.dropna().astype(str).str.strip().str.lower()
            ok = vals.isin(["yes", "no"])
            if len(vals) and ok.mean() < 1 - MAX_BAD_NUMERIC_SHARE:
                errors.append(f"Column '{col}' should contain Yes/No, but found values like "
                              f"{_examples(s.dropna()[~ok.values].drop_duplicates())}.")
        else:  # text
            df[col] = s.astype("string")

    if "Restaurant ID" in df and df["Restaurant ID"].isna().all():
        errors.append("Column 'Restaurant ID' is empty.")

    if errors:
        raise SchemaError(_format(source, errors))
    ordered = list(ALL_COLUMNS) + [c for c in df.columns if c not in ALL_COLUMNS]
    return ValidationResult(df[ordered], warnings)


def _format(source: str, errors: list[str]) -> str:
    lines = [f"The {source} does not match the expected Zomato format:"]
    lines += [f"  - {e}" for e in errors]
    lines.append("Expected columns: " + ", ".join(REQUIRED_COLUMNS))
    return "\n".join(lines)
