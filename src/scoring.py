"""Score NEW restaurants with the saved popularity model (no re-training).

Several features are relative to the market: cost percentile within the country, branch count (same
name), locality size and city group. So new restaurants are scored *in the context of the Kaggle data*:
the new rows are added to the Kaggle reference rows, cleaned with exactly the same cleaning code and
turned into features with exactly the same feature code as in training. A reference row with the same
Restaurant ID as a new row is replaced by the new row (so scoring a row that is already in the Kaggle
file gives the same features as in training).

The model never sees votes or ratings (leakage rule); new restaurants need neither.
"""
from __future__ import annotations

import json
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd

from src import config
from src.cleaning import clean
from src.data_loading import load_validated
from src.features import assert_no_leakage, build_features

MODEL_PATH = config.MODELS_DIR / "popularity_model.joblib"
MODEL_META = config.MODELS_DIR / "popularity_model_meta.json"
LABELS = ["Low", "Medium", "High"]


def _norm(s) -> str:
    return " ".join(str(s).lower().split())


@lru_cache(maxsize=1)
def load_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Saved model not found: {MODEL_PATH}. Run `python run_pipeline.py` first.")
    meta = json.loads(MODEL_META.read_text(encoding="utf-8"))
    assert_no_leakage(meta["features"])
    return joblib.load(MODEL_PATH), meta


@lru_cache(maxsize=1)
def reference_raw() -> pd.DataFrame:
    """The Kaggle data (validated, with country names), the market the model was trained on."""
    return load_validated().df


def predict_raw(new_raw: pd.DataFrame) -> pd.DataFrame:
    """Predict Low/Medium/High for validated raw rows (Kaggle column names). One output row per restaurant."""
    model, meta = load_model()
    ref = reference_raw()
    new = new_raw.reindex(columns=ref.columns)
    ref = ref[~ref["Restaurant ID"].isin(new["Restaurant ID"])]
    cleaned, pairs, _ = clean(pd.concat([ref, new], ignore_index=True))

    wanted = set(meta["features"])
    cuisine_names = sorted({c for c in pairs["cuisine"].unique()
                            if "cuisine_" + c.lower().replace(" ", "_") in wanted})
    X = build_features(cleaned, pairs, cuisines=cuisine_names)
    missing = wanted - set(X.columns)
    if missing:
        raise ValueError(f"Could not build model features: {sorted(missing)}")
    ids = pd.Index(new["Restaurant ID"].dropna().unique())
    X = X.loc[X.index.isin(ids), meta["features"]]

    proba = pd.DataFrame(model.predict_proba(X), index=X.index, columns=model.classes_)[LABELS]
    info = cleaned.set_index("restaurant_id").loc[X.index, [
        "restaurant_name", "country", "city", "locality", "cuisines", "price_range", "avg_cost_for_two",
        "currency", "has_online_delivery", "has_table_booking"]]
    out = info.join(proba.rename(columns={"Low": "prob_low", "Medium": "prob_medium", "High": "prob_high"}))
    out["predicted_class"] = proba.idxmax(axis=1)
    out["cost_pct_in_country"] = X["cost_pct_in_country"].round(3)
    out["branches_with_same_name"] = np.rint(np.expm1(X["log_branch_count"])).astype(int)   # undo log(1 + n)
    out["restaurants_in_locality"] = np.rint(np.expm1(X["log_locality_size"])).astype(int)
    out["model"] = meta["best_model"]
    return out.reset_index()


def known_cuisines() -> dict[str, str]:
    """lower-case name -> name as written in the data."""
    ref = reference_raw()
    names = {c.strip() for s in ref["Cuisines"].dropna() for c in str(s).split(",") if c.strip()}
    return {_norm(c): c for c in sorted(names)}


def new_restaurant_raw(city: str, cuisines: list[str], price_range: int, cost_for_two: float,
                       online_delivery: bool, table_booking: bool, locality: str | None = None,
                       name: str | None = None, country: str | None = None,
                       latitude: float | None = None, longitude: float | None = None,
                       delivering_now: bool = False) -> tuple[pd.DataFrame, list[str]]:
    """Build one raw row (Kaggle format) for a restaurant typed in by the user.

    Country, country code and currency come from the city in the Kaggle data. Coordinates default to
    the median of the locality (or city). Returns (row, notes explaining the defaults used).
    """
    ref = reference_raw()
    notes: list[str] = []
    rows = ref[ref["City"].map(_norm) == _norm(city)]
    if country:
        rows = rows[rows["Country"].map(_norm) == _norm(country)]
    if rows.empty:
        close = sorted(c for c in ref["City"].dropna().unique() if _norm(city)[:3] in _norm(c))[:6]
        raise ValueError(f"City '{city}' is not in the data." + (f" Did you mean: {', '.join(close)}?" if close else ""))
    if rows["Country"].nunique() > 1:
        raise ValueError(f"'{city}' exists in several countries ({', '.join(sorted(rows['Country'].unique()))}). "
                         "Add the country.")
    if int(price_range) not in (1, 2, 3, 4):
        raise ValueError("Price range must be 1, 2, 3 or 4.")
    if not cost_for_two or float(cost_for_two) <= 0:
        raise ValueError("Cost for two must be a positive amount (local currency).")
    lookup = known_cuisines()
    bad = [c for c in cuisines if _norm(c) not in lookup]
    if bad:
        raise ValueError(f"Unknown cuisine(s): {', '.join(bad)}. Examples: North Indian, Chinese, Cafe, Italian.")
    if not cuisines:
        raise ValueError("Give at least one cuisine.")

    area = rows
    if locality:
        in_loc = rows[rows["Locality"].map(_norm) == _norm(locality)]
        if in_loc.empty:
            notes.append(f"Locality '{locality}' has no other restaurants in the data (locality size = 1).")
        else:
            area = in_loc
    else:
        notes.append("No locality given: locality size = 1 (only this restaurant).")
    if latitude is None or longitude is None:
        valid = area[(area["Latitude"] != 0) & (area["Longitude"] != 0)]
        latitude, longitude = (float(valid["Latitude"].median()), float(valid["Longitude"].median())) \
            if len(valid) else (0.0, 0.0)
        notes.append("Coordinates not given: using the middle of the " + ("locality." if area is not rows else "city."))

    yes_no = lambda b: "Yes" if b else "No"  # noqa: E731
    row = {
        "Restaurant ID": int(ref["Restaurant ID"].max()) + 1,
        "Restaurant Name": name or "New restaurant",
        "Country Code": int(rows["Country Code"].mode().iloc[0]),
        "Country": rows["Country"].iloc[0],
        "City": rows["City"].iloc[0],
        "Address": "",
        "Locality": locality or "",
        "Locality Verbose": f"{locality}, {rows['City'].iloc[0]}" if locality else "",
        "Longitude": longitude, "Latitude": latitude,
        "Cuisines": ", ".join(lookup[_norm(c)] for c in cuisines),
        "Average Cost for two": float(cost_for_two),
        "Currency": rows["Currency"].mode().iloc[0],
        "Has Table booking": yes_no(table_booking), "Has Online delivery": yes_no(online_delivery),
        "Is delivering now": yes_no(delivering_now), "Switch to order menu": "No",
        "Price range": int(price_range),
        "Aggregate rating": 0.0, "Rating color": "White", "Rating text": "Not rated", "Votes": 0,
    }
    return pd.DataFrame([row]).reindex(columns=ref.columns), notes
