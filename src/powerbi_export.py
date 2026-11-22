"""Prepare the data for the Power BI dashboard.

Writes dashboards/powerbi/powerbi_data.xlsx (one sheet per table, so Power BI imports everything in one
step) and dashboards/powerbi/expected_values.md (numbers to check the dashboard against). Every value is
computed from the cleaned data and the popularity model outputs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import config
from src.model import NCR_CITIES

PBI_DIR = config.ROOT / "dashboards" / "powerbi"
PBI_XLSX = PBI_DIR / "powerbi_data.xlsx"
EXPECTED_MD = PBI_DIR / "expected_values.md"

# Colour theme shared by all charts and dashboards
PRICE = {1: ("1 Budget", "#8E1520"), 2: ("2 Moderate", "#CB202D"), 3: ("3 Expensive", "#E8838B"),
         4: ("4 Luxury", "#F5C6CA")}
CLASS_ORDER = {"Low": 1, "Medium": 2, "High": 3}
CLASS_COLOUR = {"Low": "#F5C6CA", "Medium": "#E8838B", "High": "#8E1520"}
ACCENT, GREY = "#CB202D", "#5C5C66"

METRIC_LABELS = {
    "test_accuracy": "Accuracy", "test_precision_macro": "Precision (macro)", "test_recall_macro": "Recall (macro)",
    "test_f1_macro": "F1 (macro)", "test_f1_weighted": "F1 (weighted)", "test_roc_auc_ovr_macro": "ROC-AUC (OvR)",
    "cv_f1_macro_mean": "CV F1 (macro, train)",
}
FEATURE_LABELS = {
    "latitude": "Latitude", "longitude": "Longitude", "city_group": "City", "country": "Country",
    "cost_pct_in_country": "Cost percentile within country", "log_locality_size": "Restaurants in locality (log)",
    "has_online_delivery": "Online delivery", "has_table_booking": "Table booking",
    "is_delivering_now": "Delivering now", "price_range": "Price range",
    "log_branch_count": "Number of branches (log)", "has_valid_coords": "Has valid coordinates",
    "n_cuisines": "Number of cuisines", "is_cost_outlier": "Cost outlier flag",
}


def _feature_label(f: str) -> str:
    if f.startswith("cuisine_"):
        return "Cuisine: " + f.removeprefix("cuisine_").replace("_", " ").title()
    return FEATURE_LABELS.get(f, f)


def restaurants_table(clean: pd.DataFrame) -> pd.DataFrame:
    d = clean.copy()
    d["price_label"] = d["price_range"].map(lambda p: PRICE.get(p, ("Unknown", GREY))[0])
    d["price_color"] = d["price_range"].map(lambda p: PRICE.get(p, ("Unknown", GREY))[1])
    band_order = (d.assign(r=d["aggregate_rating"].fillna(-1)).groupby("rating_text")["r"].mean()
                  .rank(method="dense").astype(int))
    d["rating_band_order"] = d["rating_text"].map(band_order)
    d["rating_bar_color"] = np.where(d["is_rated"] == 1, ACCENT, GREY)
    d["popularity_order"] = d["popularity_class"].map(CLASS_ORDER)
    d["table_booking_label"] = d["has_table_booking"].map({1: "Yes", 0: "No"})
    d["online_delivery_label"] = d["has_online_delivery"].map({1: "Yes", 0: "No"})
    d["zone"] = np.where(d["country"] != "India", "Outside India",
                         np.where(d["city"].isin(NCR_CITIES), "India: Delhi NCR", "India: other cities"))
    d["branch_count"] = d["restaurant_name"].map(d["restaurant_name"].value_counts())
    d["outlet_type"] = np.where(d["branch_count"] > 1, "Chain (2+ branches)", "Single outlet")
    loc_key = d["city"].astype(str) + "|" + d["locality"].astype(str)
    d["locality_size"] = loc_key.map(loc_key.value_counts())
    cols = ["restaurant_id", "restaurant_name", "country", "city", "locality", "zone", "latitude", "longitude",
            "has_valid_coords", "cuisines", "n_cuisines", "avg_cost_for_two", "avg_cost_for_two_usd", "currency",
            "price_range",
            "price_label", "price_color", "has_table_booking", "table_booking_label", "has_online_delivery",
            "online_delivery_label", "aggregate_rating", "rating_text", "rating_band_order", "rating_bar_color",
            "votes", "is_rated", "popularity_class", "popularity_order", "branch_count", "outlet_type",
            "locality_size"]
    return d[cols]


def model_tables() -> dict[str, pd.DataFrame]:
    pdir = config.PREDICTIONS_DIR
    comp = pd.read_csv(pdir / "model_comparison.csv")
    meta_best = __import__("json").loads((config.MODELS_DIR / "popularity_model_meta.json").read_text(encoding="utf-8"))["best_model"]
    comp["is_best"] = (comp["model"] == meta_best).astype(int)
    comp["model_order"] = range(1, len(comp) + 1)
    comp_out = comp[["model", "model_order", "is_best"] + list(METRIC_LABELS)]

    long = comp.melt(id_vars=["model", "model_order", "is_best"], value_vars=list(METRIC_LABELS),
                     var_name="metric_key", value_name="value")
    long["metric"] = long["metric_key"].map(METRIC_LABELS)
    long["metric_order"] = long["metric_key"].map({k: i for i, k in enumerate(METRIC_LABELS, start=1)})

    cm = pd.read_csv(pdir / "confusion_matrix.csv", index_col=0)
    cml = cm.reset_index().melt(id_vars="actual", var_name="predicted", value_name="count")
    cml["pct_of_actual"] = cml["count"] / cml.groupby("actual")["count"].transform("sum")
    cml["actual_order"] = cml["actual"].map(CLASS_ORDER)
    cml["predicted_order"] = cml["predicted"].map(CLASS_ORDER)
    cml["is_correct"] = (cml["actual"] == cml["predicted"]).astype(int)

    imp = pd.read_csv(pdir / "feature_importance.csv")
    imp.insert(0, "rank", range(1, len(imp) + 1))
    imp.insert(2, "feature_label", imp["feature"].map(_feature_label))

    pred = pd.read_csv(pdir / "popularity_predictions.csv")[
        ["restaurant_id", "actual_class", "predicted_class", "prob_low", "prob_medium", "prob_high", "split",
         "correct", "model"]]
    pred["actual_order"] = pred["actual_class"].map(CLASS_ORDER)
    pred["predicted_order"] = pred["predicted_class"].map(CLASS_ORDER)
    pred["predicted_color"] = pred["predicted_class"].map(CLASS_COLOUR)
    pred["result"] = np.where(pred["correct"] == 1, "Correct", "Incorrect")

    rob = pd.read_csv(pdir / "robustness_checks.csv")
    classes = pd.DataFrame({"popularity_class": list(CLASS_ORDER), "class_order": list(CLASS_ORDER.values()),
                            "class_color": [CLASS_COLOUR[c] for c in CLASS_ORDER]})
    return {"model_comparison": comp_out, "model_metrics_long": long.drop(columns="metric_key"),
            "confusion_matrix": cml, "feature_importance": imp, "predictions": pred,
            "robustness_checks": rob, "popularity_classes": classes}


def expected_values(rest: pd.DataFrame, pairs: pd.DataFrame, tables: dict) -> str:
    def kpis(d: pd.DataFrame) -> list[str]:
        return [f"{len(d):,}", f"{d['city'].nunique():,}", f"{d['aggregate_rating'].mean():.2f}",
                f"{int(d['votes'].sum()):,}", f"{100 * d['has_online_delivery'].mean():.1f}%"]

    rows = [("No slicer selected", rest)] + [(f"Country = {c}", rest[rest["country"] == c])
                                              for c in rest["country"].value_counts().index[:3]]
    top = pairs["cuisine"].value_counts().head(10)
    comp = tables["model_comparison"]
    best = comp[comp["is_best"] == 1].iloc[0]
    lines = ["# Expected values (check your dashboard against these)", "",
             "*Generated by `src/powerbi_export.py` from the same data loaded into Power BI.*", "",
             "## Page 1 KPI cards", "",
             "| Filter | Restaurants | Cities | Avg Rating | Total Votes | Online Delivery % |", "|---|---|---|---|---|---|"]
    lines += [f"| {name} | " + " | ".join(kpis(d)) + " |" for name, d in rows]
    lines += ["", "Avg Rating counts rated restaurants only (unrated have a blank rating).", "",
              "## Page 1 charts (no slicer)", "",
              "Top 10 cuisines: " + ", ".join(f"{c} {n:,}" for c, n in top.items()) + ".", "",
              "Rating bands: " + ", ".join(f"{b} {n:,}" for b, n in rest.groupby("rating_text").size()
                                           .reindex(rest.drop_duplicates("rating_text")
                                                    .sort_values("rating_band_order")["rating_text"]).items()) + ".",
              "",
              "Price ranges: " + ", ".join(f"{l} {n:,}" for l, n in rest.groupby("price_label").size().items()) + ".",
              "",
              f"Table booking {100 * rest['has_table_booking'].mean():.1f}%, online delivery "
              f"{100 * rest['has_online_delivery'].mean():.1f}%.", ""]
    rated = rest[rest["is_rated"] == 1]
    india = rated[rated["country"] == "India"]
    dl = india.groupby("has_online_delivery")["aggregate_rating"].agg(["size", "mean"])
    tb = rest.groupby("has_table_booking")["price_range"].mean()
    loc = rest.groupby(["locality", "city"]).size().sort_values(ascending=False)
    zones = rated.groupby("zone")["aggregate_rating"].mean()
    lines += ["## Page 2 (no slicer)", "",
              "Online delivery vs rating (official definition, used in the report, docs and dashboard): "
              "**India only, rated restaurants, mean rating**, because online delivery exists only in India and "
              f"UAE. With delivery {dl.loc[1, 'mean']:.2f} (n={int(dl.loc[1, 'size']):,}), without "
              f"{dl.loc[0, 'mean']:.2f} (n={int(dl.loc[0, 'size']):,}).", "",
              f"Avg price range with table booking {tb.loc[1]:.2f}, without {tb.loc[0]:.2f}.", "",
              "## Page 3 (no slicer)", "",
              "Most crowded localities: " + ", ".join(f"{l} ({c}) {n:,}" for (l, c), n in loc.head(10).items())
              + ".", "",
              "Avg rating by zone: " + ", ".join(f"{z} {v:.2f}" for z, v in zones.items()) + ".", "",
              "## Page 4 (model)", "",
              f"Best model {best['model']}: accuracy {best['test_accuracy']:.3f}, macro-F1 {best['test_f1_macro']:.3f}, "
              f"ROC-AUC {best['test_roc_auc_ovr_macro']:.3f}. Prediction agreement over all "
              f"{len(tables['predictions']):,} rated restaurants (out-of-fold + test): "
              f"{tables['predictions']['correct'].mean():.1%}.", ""]
    return "\n".join(lines)


def export_powerbi(clean: pd.DataFrame, pairs: pd.DataFrame) -> dict:
    PBI_DIR.mkdir(parents=True, exist_ok=True)
    rest = restaurants_table(clean)
    tables = {"restaurants": rest, "restaurant_cuisines": pairs[["restaurant_id", "cuisine"]], **model_tables()}
    with pd.ExcelWriter(PBI_XLSX, engine="openpyxl") as xw:
        for name, df in tables.items():
            df.to_excel(xw, sheet_name=name, index=False)
    EXPECTED_MD.write_text(expected_values(rest, pairs, tables), encoding="utf-8")
    return {name: len(df) for name, df in tables.items()}
