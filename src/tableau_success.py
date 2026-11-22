"""Tableau dashboard 3: Success prediction (same content as Power BI page 4).

Data: data/processed/tableau_success_prediction.csv, written here from the model outputs in outputs/predictions
(nothing typed in). One tidy table with a `section` column; each sheet filters one section:
- comparison: test accuracy and macro-F1 of the 4 algorithms and the majority baseline;
- confusion: confusion matrix of the saved model on the test set (count and row share);
- class_split: actual vs predicted class counts for every rated restaurant (training rows out-of-fold);
- importance: top 15 features by permutation importance (drop in macro-F1).
"""
from __future__ import annotations

import pandas as pd

from src import config
from src.tableau_twb import (ACCENT, DS, HIGHLIGHT, PROC, TAB_DIR, TEXT2, axis_title, calc_column, csv_datasource,
                             fmt, hide_field_labels, inst, q, worksheet)
from src.powerbi_export import _feature_label   # same readable feature names as Power BI page 4
from src.target import EXCLUDED_FEATURES_NOTE, LABELS, TARGET_DEFINITION

SUCCESS_CSV = PROC / "tableau_success_prediction.csv"
HYPER_SUCCESS = TAB_DIR / "tableau_success_prediction.hyper"
SUCCESS_COLUMNS = [("section", "string"), ("item", "string"), ("series", "string"), ("score", "real"),
                   ("count", "integer"), ("share", "real"), ("item_order", "integer"), ("series_order", "integer")]
DASH3 = "Success prediction"
TOP_FEATURES = 15
SERIES_COLOURS = {"Accuracy": HIGHLIGHT, "Macro F1": ACCENT, "Actual": TEXT2, "Predicted": ACCENT,
                  "Importance": ACCENT}


def write_success_data() -> pd.DataFrame:
    P = config.PREDICTIONS_DIR
    rows = []
    comp = pd.read_csv(P / "model_comparison.csv")
    for i, r in enumerate(comp.itertuples(index=False)):
        for j, (col, lab) in enumerate([("test_accuracy", "Accuracy"), ("test_f1_macro", "Macro F1")]):
            rows.append(("comparison", r.model, lab, getattr(r, col), None, None, i, j))
    cm = pd.read_csv(P / "confusion_matrix.csv", index_col=0)
    for i, a in enumerate(LABELS):
        total = cm.loc[a].sum()
        for j, b in enumerate(LABELS):
            rows.append(("confusion", a, b, None, int(cm.loc[a, b]), cm.loc[a, b] / total, i, j))
    pred = pd.read_csv(P / "popularity_predictions.csv")
    for j, (col, lab) in enumerate([("actual_class", "Actual"), ("predicted_class", "Predicted")]):
        vc = pred[col].value_counts()
        for i, c in enumerate(LABELS):
            rows.append(("class_split", c, lab, None, int(vc.get(c, 0)), vc.get(c, 0) / len(pred), i, j))
    imp = pd.read_csv(P / "feature_importance.csv").head(TOP_FEATURES)
    for i, r in enumerate(imp.itertuples(index=False)):
        rows.append(("importance", _feature_label(r.feature), "Importance", r.importance_mean, None, None, i, 0))
    df = pd.DataFrame(rows, columns=[c for c, _ in SUCCESS_COLUMNS])
    df.to_csv(SUCCESS_CSV, index=False, encoding="utf-8")
    return df


def success_notes() -> list[str]:
    """Text box lines: target definition, leakage rule, saved model and leaky score (numbers from the outputs)."""
    P = config.PREDICTIONS_DIR
    comp = pd.read_csv(P / "model_comparison.csv").set_index("model")
    leak = pd.read_csv(P / "leakage_demo.csv").iloc[1]
    meta = pd.read_json(config.MODELS_DIR / "popularity_model_meta.json", typ="series")
    best = meta["best_model"]
    return [TARGET_DEFINITION,
            f"{EXCLUDED_FEATURES_NOTE} With votes and rating added, accuracy would be {leak['test_accuracy']:.1%} "
            "(invalid).",
            f"Saved model: {best} (chosen by 5-fold CV on the training set). Test set: accuracy "
            f"{comp.loc[best, 'test_accuracy']:.1%}, macro-F1 {comp.loc[best, 'test_f1_macro']:.3f}; majority baseline "
            f"{comp.loc['Baseline (majority class)', 'test_accuracy']:.1%}."]


def success_datasource() -> tuple[str, DS]:
    columns = {
        "section": "<column caption='Section' datatype='string' name='[section]' role='dimension' type='nominal' />",
        "item": "<column caption='Item' datatype='string' name='[item]' role='dimension' type='nominal' />",
        "series": "<column caption='Series' datatype='string' name='[series]' role='dimension' type='nominal' />",
        "score": "<column caption='Score' datatype='real' default-format='n#,##0.000;-#,##0.000' name='[score]' "
                 "role='measure' type='quantitative' />",
        "count": "<column caption='Restaurants' datatype='integer' default-format='n#,##0;-#,##0' name='[count]' "
                 "role='measure' type='quantitative' />",
        "share": "<column caption='Share' datatype='real' default-format='p0%' name='[share]' role='measure' "
                 "type='quantitative' />",
        "item_order": "<column caption='Item order' datatype='integer' name='[item_order]' role='measure' "
                      "type='quantitative' />",
        "series_order": "<column caption='Series order' datatype='integer' name='[series_order]' role='measure' "
                        "type='quantitative' />",
        "Calculation_cell_label": calc_column(
            "Calculation_cell_label", "Cell label", "string", "measure", "nominal",
            'STR(SUM([count])) + " (" + STR(ROUND(100 * SUM([share]), 0)) + "%)"'),
    }
    maps = "".join(f"\n            <map to='{c}'>\n              <bucket>&quot;{q(n)}&quot;</bucket>\n            </map>"
                   for n, c in SERIES_COLOURS.items())
    style = ("      <style>\n        <style-rule element='mark'>\n"
             f"          <encoding attr='color' field='[none:series:nk]' type='palette'>{maps}\n"
             "          </encoding>\n        </style-rule>\n      </style>\n")
    return csv_datasource("success", "tableau_success_prediction", SUCCESS_CSV, SUCCESS_COLUMNS, columns,
                          HYPER_SUCCESS, style)


def section_filter(ds: DS, sec: str) -> str:
    return (f"\n          <filter class='categorical' column='{ds.ref('none:section:nk')}'>\n"
            f"            <groupfilter function='member' level='[none:section:nk]' member='{q(chr(34) + sec + chr(34))}' "
            "user:ui-domain='database' user:ui-enumeration='inclusive' user:ui-marker='enumerate' />\n"
            "          </filter>")


def _sort(ds: DS, dim: str, order_inst: str, direction: str = "ASC") -> str:
    return (f"\n          <sort class='computed' column='{ds.ref(dim)}' direction='{direction}' "
            f"using='{ds.ref(order_inst)}' />")


def success_sheets(ds: DS) -> list[tuple[str, str]]:
    sec, sec_x = inst("section", "None", "nk")
    item, item_x = inst("item", "None", "nk")
    ser, ser_x = inst("series", "None", "nk")
    score, score_x = inst("score", "Sum", "qk")
    cnt, cnt_x = inst("count", "Sum", "qk")
    share, share_x = inst("share", "Sum", "qk")
    io, io_x = inst("item_order", "Min", "qk")
    so, so_x = inst("series_order", "Min", "qk")
    lab, lab_x = inst("Calculation_cell_label", "User", "nk")
    r = lambda i: ds.ref(i[1:-1])
    sheets = []

    name = "Model comparison (test set)"
    sheets.append((name, worksheet(
        name, ds, ds.deps(["section", "item", "series", "score", "item_order", "series_order"],
                          [sec_x, item_x, ser_x, score_x, io_x, so_x]),
        "Model comparison on the test set: accuracy and macro-F1",
        rows=f"({r(item)} / {r(ser)})", cols=r(score), mark="Bar", filters=section_filter(ds, "comparison"),
        sort=_sort(ds, item[1:-1], io[1:-1]) + _sort(ds, ser[1:-1], so[1:-1]),
        encodings=f"\n              <color column='{r(ser)}' />\n              <text column='{r(score)}' />",
        table_style=axis_title(r(score), "cols", "Score (test set)", 1) + hide_field_labels(),
        pane_style=fmt("mark-labels-show", "true"))))

    name = "Confusion matrix (test set)"
    sheets.append((name, worksheet(
        name, ds, ds.deps(["section", "item", "series", "count", "share", "item_order", "series_order",
                           "Calculation_cell_label"],
                          [sec_x, item_x, ser_x, cnt_x, share_x, io_x, so_x, lab_x]),
        "Confusion matrix of the saved model (rows = actual, columns = predicted)",
        rows=r(item), cols=r(ser), mark="Square", filters=section_filter(ds, "confusion"),
        sort=_sort(ds, item[1:-1], io[1:-1]) + _sort(ds, ser[1:-1], so[1:-1]),
        encodings=f"\n              <color column='{r(share)}' />\n              <text column='{r(lab)}' />",
        table_style=hide_field_labels(),
        pane_style=fmt("mark-labels-show", "true"))))

    name = "Predicted vs actual class split"
    sheets.append((name, worksheet(
        name, ds, ds.deps(["section", "item", "series", "count", "item_order", "series_order"],
                          [sec_x, item_x, ser_x, cnt_x, io_x, so_x]),
        "Popularity classes: actual vs predicted (all rated restaurants; training rows out-of-fold)",
        rows=f"({r(item)} / {r(ser)})", cols=r(cnt), mark="Bar", filters=section_filter(ds, "class_split"),
        sort=_sort(ds, item[1:-1], io[1:-1]) + _sort(ds, ser[1:-1], so[1:-1]),
        encodings=f"\n              <color column='{r(ser)}' />\n              <text column='{r(cnt)}' />",
        table_style=axis_title(r(cnt), "cols", "Restaurants") + hide_field_labels(),
        pane_style=fmt("mark-labels-show", "true"))))

    name = f"Feature importance (top {TOP_FEATURES})"
    sheets.append((name, worksheet(
        name, ds, ds.deps(["section", "item", "score", "item_order"], [sec_x, item_x, score_x, io_x]),
        f"Top {TOP_FEATURES} features: drop in macro-F1 when the feature is shuffled (test set)",
        rows=r(item), cols=r(score), mark="Bar", filters=section_filter(ds, "importance"),
        sort=_sort(ds, item[1:-1], io[1:-1]),
        encodings=f"\n              <text column='{r(score)}' />",
        table_style=_fixed_axis(r(score), "cols", "Drop in macro-F1", _importance_axis_max()) + hide_field_labels(),
        pane_style=fmt("mark-color", ACCENT) + fmt("mark-labels-show", "true"))))
    return sheets


def _importance_axis_max() -> float:
    """Axis end with ~30% headroom over the largest importance, so the value labels of the top bars fit
    beside them instead of overlapping (rounded up to 0.02)."""
    import math
    top = pd.read_csv(config.PREDICTIONS_DIR / "feature_importance.csv")["importance_mean"].max()
    return round(math.ceil(top * 1.3 / 0.02) * 0.02, 2)


def _fixed_axis(field_ref: str, scope: str, title: str, max_: float, spacing: float = 0.02) -> str:
    """Axis title plus a fixed range 0..max_ (same <encoding attr='space'> structure as axis_title)."""
    return (f"\n          <style-rule element='axis'>\n            <format attr='title' field='{field_ref}' "
            f"scope='{scope}' value='{q(title)}' />"
            f"\n            <encoding attr='space' class='0' field='{field_ref}' field-type='quantitative' "
            f"major-origin='0' major-spacing='{spacing}' max='{max_}' min='0' range-type='fixed' "
            f"scope='{scope}' type='space' />\n          </style-rule>")


def success_layout(sheets: list[tuple[str, str]]) -> tuple[list, list[tuple[list[str], tuple]]]:
    """Notes box under the header, then a 2 x 2 grid of charts (1280 x 720 page)."""
    notes = [(success_notes(), (16, 64, 1248, 96))]   # 3 lines at 9 pt incl. wrapping: 72 px cut the last one
    x, w, y, h = (16, 648), 616, (168, 442), 266
    grid = [(x[0], y[0]), (x[1], y[0]), (x[0], y[1]), (x[1], y[1])]
    placements = [(n, (gx, gy, w, h)) for (n, _), (gx, gy) in zip(sheets, grid)]
    return placements, notes
