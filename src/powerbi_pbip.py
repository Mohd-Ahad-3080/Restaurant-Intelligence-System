"""Generate the Power BI Project (PBIP) content: semantic-model measures (TMDL) and report pages (PBIR).

Formats follow exactly what Power BI Desktop wrote in dashboards/powerbi (inspected 2026-11-09):
- Report: PBIR folder format, report.json schema 3.3.0, page.json 2.1.0, pages.json 1.1.0,
  visual.json -> visualContainer 2.13.0 (latest published by Microsoft; Desktop wrote none yet).
- Semantic model: TMDL (database compatibilityLevel 1606).

Run with Power BI Desktop CLOSED:  python -m src.powerbi_pbip --page 1 [--validate]
Re-running is safe: generated measures and generated visuals are replaced, not duplicated.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import uuid
from pathlib import Path

from src import config

PBI_DIR = config.ROOT / "dashboards" / "powerbi"
MODEL_DIR = PBI_DIR / "RestaurantIntelligence.SemanticModel" / "definition"
REPORT_DIR = PBI_DIR / "RestaurantIntelligence.Report"
REPORT_DEF = REPORT_DIR / "definition"
THEME_SRC = PBI_DIR / "theme_b_slate_red.json"
THEME_NAME = "theme_b_slate_red.json"

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
VC_SCHEMA = f"{SCHEMA}/visualContainer/2.13.0/schema.json"
PAGE_SCHEMA = f"{SCHEMA}/page/2.1.0/schema.json"
PAGE_W, PAGE_H = 1280, 720
GEN_PREFIX = "gen_"  # every generated visual name starts with this, so re-runs can replace them

# Theme B: the approved project colour theme (slate + brand red)
SLATE, WHITE, ACCENT, HIGHLIGHT, ACTIVE = "#1F2329", "#FFFFFF", "#CB202D", "#8E1520", "#E23744"
TEXT, TEXT2, BORDER, PAGE_BG = "#18181B", "#5C5C66", "#E4E4E7", "#F4F4F5"
TAB_INACTIVE = "#A1A1AA"   # inactive header tab text (requested by Anser, 2026-11-09)

# ------------------------------------------------------------------ measures (single source of truth)
# (table, name, DAX, formatString)
MEASURES = [
    ("restaurants", "Restaurants", "COUNTROWS ( restaurants )", "#,0"),
    ("restaurants", "Cities", "DISTINCTCOUNT ( restaurants[city] )", "#,0"),
    ("restaurants", "Avg Rating", "AVERAGE ( restaurants[aggregate_rating] )", "0.00"),
    ("restaurants", "Total Votes", "SUM ( restaurants[votes] )", "#,0"),
    ("restaurants", "Online Delivery %",
     "DIVIDE ( CALCULATE ( [Restaurants], restaurants[has_online_delivery] = 1 ), [Restaurants] )", "0.0%"),
    ("restaurants", "Table Booking %",
     "DIVIDE ( CALCULATE ( [Restaurants], restaurants[has_table_booking] = 1 ), [Restaurants] )", "0.0%"),
    ("restaurants", "Rated Restaurants", "CALCULATE ( [Restaurants], restaurants[is_rated] = 1 )", "#,0"),
    ("restaurants", "Unrated %", "DIVIDE ( [Restaurants] - [Rated Restaurants], [Restaurants] )", "0.0%"),
    ("restaurants", "Avg Votes", "AVERAGE ( restaurants[votes] )", "#,0.0"),
    ("restaurants", "Avg Cost for Two (local)", "AVERAGE ( restaurants[avg_cost_for_two] )", "#,0"),
    # Approximate US$ (World Bank 2017 official rate by country; docs/currency_and_costs.md)
    ("restaurants", "Avg Cost for Two (US$ approx)", "AVERAGE ( restaurants[avg_cost_for_two_usd] )", "#,0.00"),
    ("restaurants", "High Popularity %",
     "DIVIDE ( CALCULATE ( [Rated Restaurants], restaurants[popularity_class] = \"High\" ), [Rated Restaurants] )",
     "0.0%"),
    ("restaurants", "Top 10 City Restaurants",
     "IF ( RANKX ( ALLSELECTED ( restaurants[city] ), [Restaurants], , DESC, Skip ) <= 10, [Restaurants] )", "#,0"),
    # Price mix by city: rank cities by ALL their restaurants (not within one price band), show each band's count
    ("restaurants", "Top 10 City Restaurants by Price",
     "IF ( RANKX ( ALLSELECTED ( restaurants[city] ), CALCULATE ( [Restaurants], ALLSELECTED ( restaurants[price_label] ) ), "
     ", DESC, Skip ) <= 10, [Restaurants] )", "#,0"),
    ("restaurants", "T10 Locality High Popularity %",
     "IF ( NOT ISBLANK ( [Top 10 Locality Restaurants] ), [High Popularity %] )", "0.0%"),
    ("restaurants", "T10 Locality Avg Cost (local)",
     "IF ( NOT ISBLANK ( [Top 10 Locality Restaurants] ), [Avg Cost for Two (local)] )", "#,0"),
    ("restaurants", "Cuisine Restaurants", "DISTINCTCOUNT ( restaurant_cuisines[restaurant_id] )", "#,0"),
    ("restaurants", "Avg Price Range", "AVERAGE ( restaurants[price_range] )", "0.00"),
    ("restaurants", "Top 10 Cuisine Restaurants",
     "IF ( RANKX ( ALLSELECTED ( restaurant_cuisines[cuisine] ), [Cuisine Restaurants], , DESC, Skip ) <= 10, "
     "[Cuisine Restaurants] )", "#,0"),
    # Skip ranking (not Dense): Brazil, UAE and South Africa tie at 60, Dense would let 14 countries through.
    ("restaurants", "Top 10 Country Restaurants",
     "IF ( RANKX ( ALLSELECTED ( restaurants[country] ), [Restaurants], , DESC, Skip ) <= 10, [Restaurants] )", "#,0"),
    ("restaurants", "Service %",
     "SWITCH ( SELECTEDVALUE ( services[service_order] ), 1, [Table Booking %], 2, [Online Delivery %] )", "0.0%"),
    ("restaurants", "Price Bar Color", "SELECTEDVALUE ( restaurants[price_color], \"#5C5C66\" )", None),
    ("restaurants", "Rating Bar Color", "SELECTEDVALUE ( restaurants[rating_bar_color], \"#5C5C66\" )", None),
    # Pages 2-4
    ("restaurants", "Rated Avg Votes", "CALCULATE ( AVERAGE ( restaurants[votes] ), restaurants[is_rated] = 1 )",
     "#,0"),
    ("restaurants", "Localities", "COUNTROWS ( SUMMARIZE ( restaurants, restaurants[city], restaurants[locality] ) )",
     "#,0"),
    ("restaurants", "Top 10 Locality Restaurants",
     "IF ( RANKX ( ALLSELECTED ( restaurants[locality_city] ), [Restaurants], , DESC, Skip ) <= 10, [Restaurants] )",
     "#,0"),
    # Official delivery-vs-rating figure is India only (delivery exists only in India and UAE): see eda_findings.md
    ("restaurants", "Avg Rating (India)",
     "CALCULATE ( [Avg Rating], KEEPFILTERS ( restaurants[country] = \"India\" ) )", "0.00"),
    # Log scale on the scatter's Y axis did not render, so log10(votes) is plotted and the axis says so.
    ("restaurants", "Log10 Votes", "AVERAGE ( restaurants[log10_votes] )", "0.00"),
    # Top-localities table: values only for the 10 most crowded localities, so the table shows exactly 10 rows
    ("restaurants", "T10 Locality Avg Rating",
     "IF ( NOT ISBLANK ( [Top 10 Locality Restaurants] ), [Avg Rating] )", "0.00"),
    ("restaurants", "T10 Locality Avg Votes",
     "IF ( NOT ISBLANK ( [Top 10 Locality Restaurants] ), [Avg Votes] )", "#,0.0"),
    ("restaurants", "T10 Locality Avg Price Range",
     "IF ( NOT ISBLANK ( [Top 10 Locality Restaurants] ), [Avg Price Range] )", "0.00"),
    ("predictions", "Predicted Class Color", "SELECTEDVALUE ( predictions[predicted_color], \"#5C5C66\" )", None),
    ("feature_importance", "Importance", "SUM ( feature_importance[importance_mean] )", "0.000"),
    ("feature_importance", "Top 10 Importance",
     "IF ( RANKX ( ALLSELECTED ( feature_importance[feature_label] ), [Importance], , DESC, Skip ) <= 10, "
     "[Importance] )", "0.000"),
    ("model_comparison", "Best Model",
     "CALCULATE ( SELECTEDVALUE ( model_comparison[model] ), model_comparison[is_best] = 1 )", None),
    ("model_comparison", "Best Accuracy",
     "CALCULATE ( MAX ( model_comparison[test_accuracy] ), model_comparison[is_best] = 1 )", "0.0%"),
    ("model_comparison", "Best Macro F1",
     "CALCULATE ( MAX ( model_comparison[test_f1_macro] ), model_comparison[is_best] = 1 )", "0.000"),
    ("model_comparison", "Best ROC AUC",
     "CALCULATE ( MAX ( model_comparison[test_roc_auc_ovr_macro] ), model_comparison[is_best] = 1 )", "0.000"),
    ("model_comparison", "Baseline Accuracy",
     "CALCULATE ( MAX ( model_comparison[test_accuracy] ), model_comparison[model] = \"Baseline (majority class)\" )",
     "0.0%"),
    ("predictions", "Predicted Restaurants", "COUNTROWS ( predictions )", "#,0"),
    ("predictions", "Prediction Agreement %", "AVERAGE ( predictions[correct] )", "0.0%"),
    ("confusion_matrix", "Confusion Count", "SUM ( confusion_matrix[count] )", "#,0"),
    ("confusion_matrix", "Confusion % of Actual", "SUM ( confusion_matrix[pct_of_actual] )", "0%"),
    ("confusion_matrix", "Confusion Cell Color",
     "IF ( HASONEVALUE ( confusion_matrix[actual] ) && HASONEVALUE ( confusion_matrix[predicted] ) "
     "&& MAX ( confusion_matrix[is_correct] ) = 1, \"#F5C6CA\", \"#FFFFFF\" )", None),
]

# (table, column) -> {property: value}
COLUMN_PROPS = {
    ("restaurants", "price_label"): {"sortByColumn": "price_range"},
    ("restaurants", "rating_text"): {"sortByColumn": "rating_band_order"},
    ("restaurants", "popularity_class"): {"sortByColumn": "popularity_order"},
    ("restaurants", "country"): {"dataCategory": "Country"},
    ("restaurants", "city"): {"dataCategory": "City"},
    ("restaurants", "latitude"): {"dataCategory": "Latitude", "summarizeBy": "none"},
    ("restaurants", "longitude"): {"dataCategory": "Longitude", "summarizeBy": "none"},
    ("predictions", "actual_class"): {"sortByColumn": "actual_order"},
    ("predictions", "predicted_class"): {"sortByColumn": "predicted_order"},
    ("confusion_matrix", "actual"): {"sortByColumn": "actual_order"},
    ("confusion_matrix", "predicted"): {"sortByColumn": "predicted_order"},
    ("model_metrics_long", "metric"): {"sortByColumn": "metric_order"},
    ("model_comparison", "model"): {"sortByColumn": "model_order"},
    # Model metrics table on Page 4: show the real values per model, 3 decimals, no summing
    **{("model_comparison", c): {"summarizeBy": "none", "formatString": "0.000"}
       for c in ("test_accuracy", "test_precision_macro", "test_recall_macro", "test_f1_macro",
                 "test_roc_auc_ovr_macro", "cv_f1_macro_mean")},
}

# Calculated columns (table, name, DAX). locality_city keeps same-named localities in different cities apart
# (Malviya Nagar and Krishna Nagar each exist in two cities).
CALC_COLUMNS = [  # (table, name, DAX, dataType)
    ("restaurants", "locality_city", "restaurants[locality] & \" (\" & restaurants[city] & \")\"", "string"),
    # rated restaurants all have >= 4 votes; unrated stay blank so they drop out of the scatter
    ("restaurants", "log10_votes",
     "IF ( restaurants[is_rated] = 1 && restaurants[votes] > 0, LOG10 ( restaurants[votes] ) )", "double"),
]


def _tid(*parts: str) -> str:
    """Stable lineage tag / name, so re-running produces identical files."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "restaurant-intelligence/" + "/".join(parts)))


def _qname(name: str) -> str:
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else "'" + name.replace("'", "''") + "'"


# ------------------------------------------------------------------ TMDL (semantic model)
def _strip_measures(text: str) -> str:
    """Remove generated measures and generated calculated columns (they are re-inserted afterwards)."""
    calc = tuple(f"\tcolumn {_qname(n)} =" for _, n, _, _ in CALC_COLUMNS)
    out, skip = [], False
    for line in text.splitlines(keepends=True):
        if line.startswith("\tmeasure ") or line.startswith(calc):
            skip = True
            continue
        if skip and (line.startswith("\t\t") or line.strip() == ""):
            continue
        skip = False
        out.append(line)
    return "".join(out)


def _set_column_prop(text: str, column: str, prop: str, value: str) -> str:
    lines = text.splitlines(keepends=True)
    start = next(i for i, l in enumerate(lines) if l.rstrip("\r\n") == f"\tcolumn {_qname(column)}")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("\t") and
                not lines[i].startswith("\t\t") and lines[i].strip()), len(lines))
    for i in range(start + 1, end):
        if lines[i].startswith(f"\t\t{prop}:"):
            lines[i] = f"\t\t{prop}: {value}\n"
            return "".join(lines)
    lines.insert(start + 2, f"\t\t{prop}: {value}\n")  # right after dataType
    return "".join(lines)


# Source columns added after Power BI Desktop first wrote the model: (table, column, dataType, formatString, M type)
SOURCE_COLUMNS = [("restaurants", "avg_cost_for_two_usd", "double", "0.00", "type number")]


def ensure_source_columns() -> None:
    """Declare columns that were added to powerbi_data.xlsx later, in the same form Desktop writes them:
    a column block in the table's TMDL and an entry in the partition's 'Changed Type' step. Idempotent."""
    for table, col, dtype, fmt, mtype in SOURCE_COLUMNS:
        path = MODEL_DIR / "tables" / f"{table}.tmdl"
        text = path.read_text(encoding="utf-8")
        if f"\tcolumn {col}\n" not in text:
            block = (f"\tcolumn {col}\n\t\tdataType: {dtype}\n\t\tformatString: {fmt}\n"
                     f"\t\tlineageTag: {_tid('column', table, col)}\n\t\tsummarizeBy: sum\n"
                     f"\t\tsourceColumn: {col}\n\n\t\tannotation SummarizationSetBy = Automatic\n\n")
            i = text.index("\tpartition ")
            text = text[:i] + block + text[i:]
        entry = f'{{"{col}", {mtype}}}'
        if entry not in text:
            text = re.sub(r'(#"Changed Type" = Table\.TransformColumnTypes\(#"Promoted Headers",\{.*?)\}\)',
                          lambda m: m.group(1) + ", " + entry + "})", text, count=1)
        path.write_text(text, encoding="utf-8")


def patch_model(extra_measures: list[tuple] = ()) -> None:
    ensure_source_columns()
    by_table: dict[str, list] = {}
    for table, name, dax, fmt in [*MEASURES, *extra_measures]:
        by_table.setdefault(table, []).append((name, dax, fmt))
    tables = {t for t, _, _, _ in [*MEASURES, *extra_measures]} | {t for t, _ in COLUMN_PROPS}
    for table in tables:
        path = MODEL_DIR / "tables" / f"{table}.tmdl"
        text = _strip_measures(path.read_text(encoding="utf-8"))
        for (t, col), props in COLUMN_PROPS.items():
            if t == table:
                for k, v in props.items():
                    text = _set_column_prop(text, col, k, v)
        block = ""
        for name, dax, fmt in by_table.get(table, []):
            block += f"\tmeasure {_qname(name)} = {dax}\n"
            if fmt:
                block += f"\t\tformatString: {fmt}\n"
            block += f"\t\tlineageTag: {_tid('measure', table, name)}\n\n"
        for t, name, dax, dtype in CALC_COLUMNS:
            if t == table:
                block += (f"\tcolumn {_qname(name)} = {dax}\n\t\tdataType: {dtype}\n"
                          f"\t\tlineageTag: {_tid('column', table, name)}\n\t\tsummarizeBy: none\n\n"
                          "\t\tannotation SummarizationSetBy = Automatic\n\n")
        lines = text.splitlines(keepends=True)
        idx = next(i for i, l in enumerate(lines) if l.startswith("\tlineageTag:")) + 1
        if block:
            lines[idx:idx] = ["\n", block.rstrip("\n") + "\n"]
        path.write_text("".join(lines), encoding="utf-8")

    # Keep only the two relationships the dashboard needs (both filter in both directions).
    rel = MODEL_DIR / "relationships.tmdl"
    blocks = [b for b in rel.read_text(encoding="utf-8").split("\n\n") if b.strip()]
    keep = []
    for b in blocks:
        if "fromColumn: restaurant_cuisines.restaurant_id" in b:
            if "crossFilteringBehavior" not in b:
                b = b.replace("\n\tfromColumn:", "\n\tcrossFilteringBehavior: bothDirections\n\tfromColumn:", 1)
            keep.append(b)
        elif "fromColumn: predictions.restaurant_id" in b:
            keep.append(b)
    if len(keep) != 2:
        raise RuntimeError(f"Expected 2 relationships to keep, found {len(keep)}")
    rel.write_text("\n\n".join(keep) + "\n\n", encoding="utf-8")
    write_services_table()


SERVICES_TABLE = "services"


def write_services_table() -> None:
    """Small calculated table with the 2 service categories for the booking/delivery bar chart.

    It holds labels only; the percentages come from the real data via the [Service %] measure.
    """
    def col(name, dtype, extra=""):
        return (f"\tcolumn {name}\n\t\tdataType: {dtype}\n{extra}\t\tlineageTag: {_tid('column', SERVICES_TABLE, name)}\n"
                f"\t\tsummarizeBy: none\n\t\tisNameInferred\n\t\tsourceColumn: [{name}]\n"
                + ("\t\tsortByColumn: service_order\n" if name == "service" else "")
                + "\n\t\tannotation SummarizationSetBy = Automatic\n\n")
    text = (f"table {SERVICES_TABLE}\n\tlineageTag: {_tid('table', SERVICES_TABLE)}\n\n"
            + col("service", "string") + col("service_order", "int64", "\t\tformatString: 0\n")
            + f"\tpartition {SERVICES_TABLE} = calculated\n\t\tmode: import\n"
            '\t\tsource = DATATABLE ( "service", STRING, "service_order", INTEGER, '
            '{ { "Table booking", 1 }, { "Online delivery", 2 } } )\n\n'
            "\tannotation PBI_Id = " + _tid("pbi", SERVICES_TABLE).replace("-", "") + "\n")
    (MODEL_DIR / "tables" / f"{SERVICES_TABLE}.tmdl").write_text(text, encoding="utf-8")
    model = MODEL_DIR / "model.tmdl"
    m = model.read_text(encoding="utf-8")
    if f"ref table {SERVICES_TABLE}\n" not in m:
        last = [l for l in m.splitlines(keepends=True) if l.startswith("ref table ")][-1]
        m = m.replace(last, last + f"ref table {SERVICES_TABLE}\n", 1)
        model.write_text(m, encoding="utf-8")


# ------------------------------------------------------------------ PBIR helpers
def lit(v):
    if isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, int):
        s = f"{v}L"
    elif isinstance(v, float):
        s = f"{v}D"
    else:
        s = "'" + str(v).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": s}}}


def colour(hex_: str):
    return {"solid": {"color": lit(hex_)}}


def measure(table: str, name: str):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def column(table: str, name: str):
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def proj(field: dict, display: str | None = None) -> dict:
    kind = "Measure" if "Measure" in field else "Column"
    table = field[kind]["Expression"]["SourceRef"]["Entity"]
    prop = field[kind]["Property"]
    p = {"field": field, "queryRef": f"{table}.{prop}", "nativeQueryRef": prop}
    if display:
        p["displayName"] = display
    return p


def props(**kw) -> list:
    return [{"properties": {k: (v if isinstance(v, dict) else lit(v)) for k, v in kw.items()}}]


def container(title: str | None = None, background=True, border=True, bg: str = WHITE, title_colour=TEXT,
              title_size=11.0, radius=6.0) -> dict:
    """Visual frame: white card (#FFFFFF, border #E4E4E7), optional clean title, no auto subtitle."""
    o = {
        "background": [{"properties": {"show": lit(background), "color": colour(bg), "transparency": lit(0.0)}}],
        "border": [{"properties": {"show": lit(border), "color": colour(BORDER), "radius": lit(radius)}}],
        "dropShadow": props(show=False),
        "subTitle": props(show=False),
        "divider": props(show=False),
    }
    o["title"] = (props(show=True, text=title, fontColor=colour(title_colour), fontSize=title_size)
                  if title else props(show=False))
    return o


def visual(name: str, x, y, w, h, z: int, vis: dict) -> dict:
    return {"$schema": VC_SCHEMA, "name": name,
            "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z}, "visual": vis}


def box(name, x, y, w, h, z, fill) -> dict:
    """Solid colour block (header, accent strips, tab underline).

    Uses an empty text box coloured via its container background: Power BI ignored the fill colour of the
    'shape' visual (the header came out in the theme's red), while container backgrounds are applied reliably.
    """
    if h <= THIN_BOX_MAX_H:
        return thin_bar(name, x, y, w, h, z, fill)
    return visual(name, x, y, w, h, z, {
        "visualType": "textbox",
        "objects": {},
        "visualContainerObjects": container(background=True, border=False, bg=fill, radius=0.0),
        "drillFilterOtherVisuals": True})


THIN_BOX_MAX_H = 8


def thin_bar(name, x, y, w, h, z, fill) -> dict:
    """Thin colour strip (KPI accent strips, active-tab underline) drawn as a blank, non-clickable button.

    A text box this thin always shows a grey scrollbar stub in the PDF export (with 1 pt text and with no text),
    so the strip uses the button visual, whose fill rendered reliably (Reset button). Switches are global,
    colours per state, corners square (the theme rounds button corners by 4 px)."""
    def per_state(**kw):
        return [{"properties": {k: (v if isinstance(v, dict) else lit(v)) for k, v in kw.items()},
                 "selector": {"id": s}} for s in BUTTON_STATES]
    return visual(name, x, y, w, h, z, {
        "visualType": "actionButton",
        "objects": {"icon": [{"properties": {"show": lit(False)}}],
                    "text": [{"properties": {"show": lit(False)}}],
                    "outline": [{"properties": {"show": lit(False)}}],
                    "fill": [{"properties": {"show": lit(True)}}] + per_state(fillColor=colour(fill),
                                                                              transparency=0.0),
                    "shape": per_state(roundEdge=0)},
        "visualContainerObjects": container(background=False, border=False),
        "drillFilterOtherVisuals": True})


def textbox(name, x, y, w, h, z, runs: list[list[tuple[str, dict]]]) -> dict:
    paragraphs = [{"textRuns": [{"value": t, "textStyle": s} for t, s in para]} for para in runs]
    return visual(name, x, y, w, h, z, {
        "visualType": "textbox",
        "objects": {"general": [{"properties": {"paragraphs": paragraphs}}]},
        "visualContainerObjects": container(background=False, border=False),
        "drillFilterOtherVisuals": True})


def slicer(name, x, y, w, h, z, table, col, label) -> dict:
    return visual(name, x, y, w, h, z, {
        "visualType": "slicer",
        "query": {"queryState": {"Values": {"projections": [proj(column(table, col), label)]}}},
        "objects": {"data": props(mode="Dropdown"),
                    "header": props(show=True, fontColor=colour(TEXT2), textSize=9.0),
                    "selection": props(selectAllCheckboxEnabled=True)},
        "visualContainerObjects": container(),
        "drillFilterOtherVisuals": True})


def card(name, x, y, w, h, z, table, m, label, font_size=20.0) -> dict:
    """KPI card: small grey label on top (the visual's title), big number below, no bottom category label.
    20 pt + tight padding: at 22 pt with the theme's padding the number's bottom was clipped in the PDF
    export, cutting the tails off the commas (1,498,645 looked like 1.498.645)."""
    vco = container(label, title_colour=TEXT2, title_size=10.0)
    vco["padding"] = props(top=8.0, bottom=2.0, left=12.0, right=12.0)
    vco["spacing"] = props(customizeSpacing=True, spaceAbovePlotArea=0.0)
    return visual(name, x, y, w, h, z, {
        "visualType": "card",
        "query": {"queryState": {"Values": {"projections": [proj(measure(table, m), label)]}}},
        "objects": {"labels": props(color=colour(TEXT), fontSize=font_size, labelDisplayUnits=1.0),
                    "categoryLabels": props(show=False),
                    "wordWrap": props(show=True)},
        "visualContainerObjects": vco,
        "drillFilterOtherVisuals": True})


def bar_chart(name, x, y, w, h, z, kind, category, values, title, fill=None, fill_measure=None,
              sort_field=None, sort_dir="Descending", series_colours=None, value_axis_end=None,
              legend=False, category_label=None, series=None, series_label=None) -> dict:
    qs = {"Y": {"projections": [proj(f, d) for f, d in values]}}
    if category is not None:
        qs["Category"] = {"projections": [proj(category, category_label)]}
    if series is not None:   # stacked charts: one colour per series value (e.g. price range)
        qs["Series"] = {"projections": [proj(series, series_label)]}
    q = {"queryState": qs}
    if sort_field is not None:
        q["sortDefinition"] = {"sort": [{"field": sort_field, "direction": sort_dir}], "isDefaultSort": False}
    # Data labels sit outside the bar end on a small white background, so they stay readable even when a
    # bar fills the whole width (the base theme lets labels overflow into the bar: red on red).
    # innerPadding 20 (base theme default is 50) leaves room for 10 bars without a scrollbar.
    objects = {"labels": props(show=True, color=colour(TEXT2), fontSize=9.0, labelDisplayUnits=1.0,
                               labelPosition="OutsideEnd", enableBackground=True, backgroundColor=colour(WHITE),
                               backgroundTransparency=0.0),
               "categoryAxis": props(show=True, showAxisTitle=False, labelColor=colour(TEXT2), fontSize=8.0,
                                     innerPadding=15.0, preferredCategoryWidth=14.0),
               "valueAxis": props(show=False, showAxisTitle=False),
               "legend": props(show=legend, position="Bottom")}
    if value_axis_end is not None:  # fixed, visible axis from 0 to value_axis_end
        objects["valueAxis"] = props(show=True, showAxisTitle=False, labelColor=colour(TEXT2),
                                     start=0.0, end=float(value_axis_end))
    dp = []
    if fill:
        dp.append({"properties": {"fill": colour(fill)}})
    if fill_measure:
        dp.append({"properties": {"fill": {"solid": {"color": {"expr": fill_measure}}}},
                   "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}})
    for qref, hex_ in (series_colours or {}).items():
        dp.append({"properties": {"fill": colour(hex_)}, "selector": {"metadata": qref}})
    if dp:
        objects["dataPoint"] = dp
    return visual(name, x, y, w, h, z, {
        "visualType": kind, "query": q, "objects": objects,
        "visualContainerObjects": chart_container(title), "drillFilterOtherVisuals": True})


def chart_container(title: str) -> dict:
    """White card with tighter inner padding than the base theme (16/14/16/16 px) and a small gap above the
    plot (theme: 16 px), so every bar of a 10-bar chart fits without a scrollbar."""
    vco = container(title)
    vco["padding"] = props(top=6.0, bottom=6.0, left=10.0, right=10.0)
    vco["spacing"] = props(customizeSpacing=True, spaceAbovePlotArea=4.0)
    return vco


BAR_TRACK = "#EFEFF1"   # Theme B light grey, used for gridlines


def scatter(name, x, y, w, h, z, details, xm, ym, title, size=None, y_range=None, bubble_size=None) -> dict:
    """Scatter: one dot per `details` value; xm / ym / size are (field, axis title) pairs.
    y_range=(start, end) fixes the Y axis; bubble_size enlarges the markers; light gridlines on both axes."""
    qs = {"Category": {"projections": [proj(details)]},
          "X": {"projections": [proj(xm[0], xm[1])]}, "Y": {"projections": [proj(ym[0], ym[1])]}}
    if size:
        qs["Size"] = {"projections": [proj(size[0], size[1])]}
    axis = dict(show=True, showAxisTitle=True, labelColor=colour(TEXT2), titleColor=colour(TEXT2), fontSize=8.0,
                gridlineShow=True, gridlineColor=colour(BAR_TRACK))
    value_axis = dict(axis)
    if y_range:
        value_axis.update(start=float(y_range[0]), end=float(y_range[1]))
    objects = {"dataPoint": [{"properties": {"fill": colour(ACCENT)}}],
               "categoryAxis": props(**axis), "valueAxis": props(**value_axis),
               "categoryLabels": props(show=False), "legend": props(show=False)}
    if bubble_size is not None:
        objects["bubbles"] = props(bubbleSize=bubble_size)
    return visual(name, x, y, w, h, z, {
        "visualType": "scatterChart", "query": {"queryState": qs}, "objects": objects,
        "visualContainerObjects": chart_container(title), "drillFilterOtherVisuals": True})


def table(name, x, y, w, h, z, columns, title, sort_field=None, sort_dir="Descending") -> dict:
    """Plain table; columns = [(field, header)]."""
    q = {"queryState": {"Values": {"projections": [proj(f, d) for f, d in columns]}}}
    if sort_field is not None:
        q["sortDefinition"] = {"sort": [{"field": sort_field, "direction": sort_dir}], "isDefaultSort": False}
    return visual(name, x, y, w, h, z, {
        "visualType": "tableEx", "query": q,
        "objects": {"columnHeaders": props(fontColor=colour(TEXT), backColor=colour(PAGE_BG), fontSize=9.0),
                    "values": props(fontColor=colour(TEXT), fontSize=9.0),
                    "total": props(totals=False),
                    "grid": props(rowPadding=2.0)},   # compact rows: 10 rows fit the 288 px card
        "visualContainerObjects": chart_container(title), "drillFilterOtherVisuals": True})


def matrix(name, x, y, w, h, z, rows, columns, values, title, cell_colour=None, font_size=10.0) -> dict:
    """Matrix (rows x columns); rows / columns / values = (field, header).
    cell_colour = measure giving each cell's background (conditional formatting by field value)."""
    qs = {"Rows": {"projections": [proj(rows[0], rows[1])]},
          "Columns": {"projections": [proj(columns[0], columns[1])]},
          "Values": {"projections": [proj(f, d) for f, d in values]}}
    vals = [{"properties": {"fontColor": colour(TEXT), "fontSize": lit(font_size)}}]
    if cell_colour is not None:
        vals.append({"properties": {"backColor": {"solid": {"color": {"expr": cell_colour}}}},
                     "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}],
                                  "metadata": proj(values[0][0])["queryRef"]}})
    return visual(name, x, y, w, h, z, {
        "visualType": "pivotTable", "query": {"queryState": qs},
        "objects": {"columnHeaders": props(fontColor=colour(TEXT), backColor=colour(PAGE_BG), fontSize=font_size),
                    "rowHeaders": props(fontColor=colour(TEXT), fontSize=font_size),
                    "values": vals,
                    "grid": props(rowPadding=8.0)},
        "visualContainerObjects": chart_container(title), "drillFilterOtherVisuals": True})


BUTTON_STATES = ("default", "hover", "press", "selected", "disabled")


def button_objects(label: str, text_colour: str, font_size: float, bold: bool, fill: str | None) -> dict:
    """actionButton formatting in the structure Power BI's own base theme uses (Fluent2 BaseTheme file):
    on/off switches ('show') are set once WITHOUT a state selector; colours and text per state
    (default, hover, press, ...). Putting 'show' inside the 'default' state is ignored by Power BI:
    that is why the first tabs rendered as red blocks with no text."""
    def per_state(**kw):
        return [{"properties": {k: (v if isinstance(v, dict) else lit(v)) for k, v in kw.items()},
                 "selector": {"id": s}} for s in BUTTON_STATES]
    o = {"icon": [{"properties": {"show": lit(False)}}],
         "outline": [{"properties": {"show": lit(False)}}],
         "text": [{"properties": {"show": lit(True)}}] + per_state(text=label, fontColor=colour(text_colour),
                                                                   fontSize=font_size, bold=bold,
                                                                   fontFamily="Segoe UI")}
    if fill:
        o["fill"] = [{"properties": {"show": lit(True)}}] + per_state(fillColor=colour(fill), transparency=0.0)
    else:
        o["fill"] = [{"properties": {"show": lit(False)}}]
    return o


def tab_button(name, x, y, w, h, z, label, target_page: str | None, active: bool) -> dict:
    """Header tab: transparent, no border; white text when active, light grey (#A1A1AA) otherwise.
    Clicking it opens target_page (no link = tab does nothing until that page exists)."""
    vco = container(background=False, border=False)
    if target_page and not active:
        vco["visualLink"] = props(show=True, type="PageNavigation", navigationSection=target_page)
    return visual(name, x, y, w, h, z, {
        "visualType": "actionButton",
        "objects": button_objects(label, WHITE if active else TAB_INACTIVE, 10.0, active, None),
        "visualContainerObjects": vco, "drillFilterOtherVisuals": True})


def reset_button(name, x, y, w, h, z) -> dict:
    vco = container(background=False, border=False)
    vco["visualLink"] = props(show=True, type="ClearAllSlicers")
    return visual(name, x, y, w, h, z, {
        "visualType": "actionButton",
        "objects": button_objects("Reset", WHITE, 10.0, True, ACCENT),
        "visualContainerObjects": vco, "drillFilterOtherVisuals": True})


# ------------------------------------------------------------------ shared page frame (header + slicers)
GRID_X = [16 + i * (93 + 12) for i in range(12)]   # 12-column grid: margin 16, column 93, gap 12


def span(n: int) -> int:
    return n * 93 + (n - 1) * 12                     # span(4)=408, span(5)=513, span(7)=723


# Header tabs: (page number, label, width). Pages 2-4 get fixed ids now, so the tabs link to them
# as soon as those pages are generated; until then their tabs are shown but do nothing (disabled).
TABS = [(1, "Overview", 92), (2, "Customers and market", 166), (3, "Location intelligence", 168),
        (5, "India deep dive", 124), (4, "Success prediction", 150), (6, "Insights", 90)]
# Page-level filters: page number -> [(table, column, value)]
PAGE_FILTERS = {5: [("restaurants", "country", "India")]}
PAGE_DISPLAY = {6: "Insights and recommendations"}   # page name when it differs from the (short) tab label
TAB_GAP = 4
TAB_X0 = PAGE_W - 16 - sum(w for _, _, w in TABS) - TAB_GAP * (len(TABS) - 1)   # tabs end at the right margin
NO_DATA = "No data for this selection"


def page_ids() -> dict[int, str]:
    ids = {n: _tid("page", str(n)).replace("-", "")[:20] for n, _, _ in TABS if n != 1}
    ids[1] = _pages_meta()["pageOrder"][0]           # the page Power BI created ("Page 1")
    return ids


def page_frame(page_no: int, slicers: bool = True) -> list[dict]:
    ids, existing = page_ids(), set(_pages_meta()["pageOrder"])
    title = PAGE_DISPLAY.get(page_no) or dict((n, lbl) for n, lbl, _ in TABS)[page_no]
    v = [
        box("gen_hdr_bg", 0, 0, PAGE_W, 56, 0, SLATE),
        textbox("gen_hdr_title", 24, 4, min(520, TAB_X0 - 32), 50, 1, [
            [("Restaurant Intelligence", {"fontFamily": "Segoe UI Semibold", "fontSize": "16pt", "color": WHITE})],
            [(f"Zomato restaurants data (Kaggle, CC0) · {title}",
              {"fontFamily": "Segoe UI", "fontSize": "9pt", "color": WHITE})]]),
    ]
    x = TAB_X0
    for n, label, w in TABS:
        active = n == page_no
        target = ids[n] if ids[n] in existing else None
        v.append(tab_button(f"gen_hdr_tab{n}", x, 10, w, 40, 2 + n, label, target, active))
        if active:
            v.append(box(f"gen_hdr_tab{n}_underline", x + 10, 50, w - 20, 3, 7, ACTIVE))
        x += w + TAB_GAP
    if not slicers:   # text-only page (findings for the whole dataset): no slicer bar
        return v
    first = (slicer("gen_slc_locality", 24, 68, 270, 44, 8, "restaurants", "locality_city", "Locality (city)")
             if page_no in PAGE_FILTERS else       # India page: country is fixed, so filter by locality instead
             slicer("gen_slc_country", 24, 68, 270, 44, 8, "restaurants", "country", "Country"))
    v += [
        first,
        slicer("gen_slc_city", 306, 68, 270, 44, 9, "restaurants", "city", "City"),
        slicer("gen_slc_price", 588, 68, 270, 44, 10, "restaurants", "price_label", "Price range"),
        slicer("gen_slc_cuisine", 870, 68, 270, 44, 11, "restaurant_cuisines", "cuisine", "Cuisine"),
        reset_button("gen_btn_reset", 1152, 72, 104, 36, 12),
    ]
    return v


# Page 1 rows: KPI cards y124-208, row 2 y216-504, row 3 y516-704 (16 px bottom margin)
R2_Y, R2_H, R3_Y, R3_H = 216, 288, 516, 188


def kpi_row(page_no: int, kpis: list[tuple]) -> list[dict]:
    """5 KPI cards (table, measure, label[, font size]) with a red top strip."""
    v = []
    for i, (t, m, label, *fs) in enumerate(kpis):
        x = 16 + i * (240 + 12)
        v.append(card(f"gen_p{page_no}_kpi{i + 1}", x, 124, 240, 84, 20 + 2 * i, t, m, label, *fs))
        v.append(box(f"gen_p{page_no}_kpi{i + 1}_strip", x, 124, 240, 4, 21 + 2 * i, ACCENT))
    return v


def page1_visuals() -> list[dict]:
    v = page_frame(1)
    v += kpi_row(1, [("restaurants", "Restaurants", "Restaurants"), ("restaurants", "Cities", "Cities"),
                     ("restaurants", "Avg Rating", "Avg rating"), ("restaurants", "Total Votes", "Total votes"),
                     ("restaurants", "Online Delivery %", "Online delivery")])
    # Row 2: top cuisines (5/12) + restaurants by country (7/12)
    v.append(bar_chart("gen_p1_top_cuisines", GRID_X[0], R2_Y, span(5), R2_H, 40, "clusteredBarChart",
                       column("restaurant_cuisines", "cuisine"),
                       [(measure("restaurants", "Top 10 Cuisine Restaurants"), "Restaurants")],
                       "Top 10 cuisines (restaurants offering each)", fill=ACCENT, category_label="Cuisine",
                       sort_field=measure("restaurants", "Top 10 Cuisine Restaurants")))
    v.append(bar_chart("gen_p1_by_country", GRID_X[5], R2_Y, span(7), R2_H, 41, "clusteredBarChart",
                       column("restaurants", "country"),
                       [(measure("restaurants", "Top 10 Country Restaurants"), "Restaurants")],
                       "Restaurants by country (top 10)", fill=ACCENT, category_label="Country",
                       sort_field=measure("restaurants", "Top 10 Country Restaurants")))
    # Row 3: three equal cards
    v.append(bar_chart("gen_p1_rating_dist", GRID_X[0], R3_Y, span(4), R3_H, 42, "clusteredColumnChart",
                       column("restaurants", "rating_text"), [(measure("restaurants", "Restaurants"), None)],
                       "Rating distribution (Not rated in grey)", category_label="Rating",
                       fill_measure=measure("restaurants", "Rating Bar Color"),
                       sort_field=column("restaurants", "rating_text"), sort_dir="Ascending"))
    v.append(bar_chart("gen_p1_price_mix", GRID_X[4], R3_Y, span(4), R3_H, 43, "clusteredColumnChart",
                       column("restaurants", "price_label"), [(measure("restaurants", "Restaurants"), None)],
                       "Price range mix (1 = Budget, 4 = Luxury)", category_label="Price range",
                       fill_measure=measure("restaurants", "Price Bar Color"),
                       sort_field=column("restaurants", "price_label"), sort_dir="Ascending"))
    v.append(bar_chart("gen_p1_services", GRID_X[8], R3_Y, span(4), R3_H, 44, "clusteredBarChart",
                       column(SERVICES_TABLE, "service"),
                       [(measure("restaurants", "Service %"), "Share of restaurants")],
                       "Table booking and online delivery", fill=ACCENT, category_label="Service",
                       sort_field=column(SERVICES_TABLE, "service"), sort_dir="Ascending",
                       value_axis_end=1))
    return v


R = "restaurants"


def page2_visuals() -> list[dict]:
    """Customers and market."""
    v = page_frame(2)
    v += kpi_row(2, [(R, "Rated Restaurants", "Rated restaurants"), (R, "Unrated %", "Not rated"),
                     (R, "Avg Votes", "Avg votes per restaurant"), (R, "Table Booking %", "Table booking"),
                     (R, "Avg Price Range", "Avg price range (1-4)")])
    v.append(scatter("gen_p2_votes_rating", GRID_X[0], R2_Y, span(7), R2_H, 40, column(R, "restaurant_id"),
                     (measure(R, "Avg Rating"), "Rating"),
                     (measure(R, "Log10 Votes"), "log10(votes)"),
                     "Votes vs rating (one dot per rated restaurant; votes on log10 scale: 2 = 100, 3 = 1,000)"))
    v.append(bar_chart("gen_p2_rating_by_price", GRID_X[7], R2_Y, span(5), R2_H, 41, "clusteredColumnChart",
                       column(R, "price_label"), [(measure(R, "Avg Rating"), "Avg rating")],
                       "Average rating by price range", category_label="Price range",
                       fill_measure=measure(R, "Price Bar Color"), value_axis_end=5,
                       sort_field=column(R, "price_label"), sort_dir="Ascending"))
    v.append(bar_chart("gen_p2_delivery_rating", GRID_X[0], R3_Y, span(6), R3_H, 42, "clusteredBarChart",
                       column(R, "online_delivery_label"), [(measure(R, "Avg Rating (India)"), "Avg rating")],
                       "India only: average rating with (Yes) vs without (No) online delivery", fill=ACCENT,
                       category_label="Online delivery", value_axis_end=5,
                       sort_field=column(R, "online_delivery_label"), sort_dir="Ascending"))
    # Cost is in local currency (not comparable across countries), so price range (1-4) is used instead.
    v.append(bar_chart("gen_p2_booking_price", GRID_X[6], R3_Y, span(6), R3_H, 43, "clusteredBarChart",
                       column(R, "table_booking_label"), [(measure(R, "Avg Price Range"), "Avg price range")],
                       "Table booking vs cost level (avg price range 1-4; costs differ by currency)",
                       fill=HIGHLIGHT, category_label="Table booking", value_axis_end=4,
                       sort_field=column(R, "table_booking_label"), sort_dir="Ascending"))
    return v


def page3_visuals() -> list[dict]:
    """Location intelligence."""
    v = page_frame(3)
    v += kpi_row(3, [(R, "Restaurants", "Restaurants"), (R, "Cities", "Cities"), (R, "Localities", "Localities"),
                     (R, "Avg Rating", "Avg rating"), (R, "Avg Price Range", "Avg price range (1-4)")])
    v.append(bar_chart("gen_p3_competition", GRID_X[0], R2_Y, span(5), R2_H, 40, "clusteredBarChart",
                       column(R, "locality_city"), [(measure(R, "Top 10 Locality Restaurants"), "Restaurants")],
                       "Area competition: 10 most crowded localities", fill=ACCENT, category_label="Locality",
                       sort_field=measure(R, "Top 10 Locality Restaurants")))
    v.append(table("gen_p3_localities", GRID_X[5], R2_Y, span(7), R2_H, 41,
                   [(column(R, "locality_city"), "Locality (city)"),
                    (measure(R, "Top 10 Locality Restaurants"), "Restaurants"),
                    (measure(R, "T10 Locality Avg Rating"), "Avg rating"),
                    (measure(R, "T10 Locality Avg Votes"), "Avg votes"),
                    (measure(R, "T10 Locality Avg Price Range"), "Avg price range")],
                   "Top 10 localities by number of restaurants",
                   sort_field=measure(R, "Top 10 Locality Restaurants")))
    v.append(scatter("gen_p3_price_rating", GRID_X[0], R3_Y, span(7), R3_H, 42, column(R, "city"),
                     (measure(R, "Avg Price Range"), "Avg price range (1-4)"), (measure(R, "Avg Rating"), "Avg rating"),
                     "Price level vs rating by city (bubble size = restaurants)",
                     size=(measure(R, "Restaurants"), "Restaurants"), y_range=(1, 5), bubble_size=30))
    v.append(bar_chart("gen_p3_zones", GRID_X[7], R3_Y, span(5), R3_H, 43, "clusteredBarChart",
                       column(R, "zone"), [(measure(R, "Avg Rating"), "Avg rating")],
                       "Location comparison: average rating by zone", fill=ACCENT, category_label="Zone",
                       value_axis_end=5, sort_field=measure(R, "Avg Rating")))
    return v


def page4_visuals() -> list[dict]:
    """Success prediction (real model results from Phase 3)."""
    v = page_frame(4)
    mc = "model_comparison"
    # Best model card uses a smaller font (15 pt) so "Gradient Boosting" fits without truncation
    v += kpi_row(4, [(mc, "Best Model", "Best model", 15.0), (mc, "Best Accuracy", "Test accuracy"),
                     (mc, "Best Macro F1", "Macro F1"), (mc, "Best ROC AUC", "ROC-AUC (one-vs-rest)"),
                     (mc, "Baseline Accuracy", "Baseline accuracy (majority class)")])
    v.append(bar_chart("gen_p4_importance", GRID_X[0], R2_Y, span(7), R2_H, 40, "clusteredBarChart",
                       column("feature_importance", "feature_label"),
                       [(measure("feature_importance", "Top 10 Importance"), "Importance")],
                       "Feature importance: top 10 (permutation importance, test set)", fill=ACCENT,
                       category_label="Feature", sort_field=measure("feature_importance", "Top 10 Importance")))
    v.append(matrix("gen_p4_confusion", GRID_X[7], R2_Y, span(5), R2_H, 41,
                    (column("confusion_matrix", "actual"), "Actual"),
                    (column("confusion_matrix", "predicted"), "Predicted"),
                    [(measure("confusion_matrix", "Confusion Count"), "Restaurants")],
                    f"Predicted vs actual (test set, {_test_set_size():,} restaurants; red = correct)",
                    cell_colour=measure("confusion_matrix", "Confusion Cell Color"), font_size=13.0))
    v.append(table("gen_p4_metrics", GRID_X[0], R3_Y, span(7), R3_H, 42,
                   [(column(mc, "model"), "Model"), (column(mc, "test_accuracy"), "Accuracy"),
                    (column(mc, "test_precision_macro"), "Precision"), (column(mc, "test_recall_macro"), "Recall"),
                    (column(mc, "test_f1_macro"), "Macro F1"), (column(mc, "test_roc_auc_ovr_macro"), "ROC-AUC"),
                    (column(mc, "cv_f1_macro_mean"), "CV macro F1")],
                   "Model comparison (test set; macro averages)", sort_field=column(mc, "model"),
                   sort_dir="Ascending"))
    v.append(bar_chart("gen_p4_predicted_split", GRID_X[7], R3_Y, span(5), R3_H, 43, "clusteredColumnChart",
                       column("predictions", "predicted_class"),
                       [(measure("predictions", "Predicted Restaurants"), "Restaurants")],
                       "Predicted popularity class (rated restaurants)", category_label="Predicted class",
                       fill_measure=measure("predictions", "Predicted Class Color"),
                       sort_field=column("predictions", "predicted_class"), sort_dir="Ascending"))
    return v


def page5_visuals() -> list[dict]:
    """India deep dive (page filter country = India; slicers: locality, city, price range, cuisine)."""
    v = page_frame(5)
    v += kpi_row(5, [(R, "Restaurants", "Restaurants"), (R, "Localities", "Localities"),
                     (R, "Avg Rating", "Avg rating (rated)"), (R, "High Popularity %", "High popularity (rated)"),
                     (R, "Avg Cost for Two (local)", "Average cost for two (INR)")])
    v.append(table("gen_p5_cities", GRID_X[0], R2_Y, span(8), R2_H, 40,
                   [(column(R, "city"), "City"), (measure(R, "Restaurants"), "Restaurants"),
                    (measure(R, "Avg Rating"), "Avg rating"), (measure(R, "High Popularity %"), "High popularity"),
                    (measure(R, "Online Delivery %"), "Online delivery"), (measure(R, "Table Booking %"), "Table booking"),
                    (measure(R, "Avg Cost for Two (local)"), "Average cost for two (INR)"),
                    (measure(R, "Avg Cost for Two (US$ approx)"), "Average cost for two (US$, approx.)")],
                   "Indian cities: rating, popularity, services and cost (INR and approx. US$)",
                   sort_field=measure(R, "Restaurants")))
    v.append(bar_chart("gen_p5_price_mix", GRID_X[8], R2_Y, span(4), R2_H, 41, "hundredPercentStackedBarChart",
                       column(R, "city"), [(measure(R, "Top 10 City Restaurants by Price"), "Restaurants")],
                       "Price range mix: 10 largest cities", fill_measure=measure(R, "Price Bar Color"),
                       category_label="City", series=column(R, "price_label"), series_label="Price range",
                       legend=True, sort_field=measure(R, "Top 10 City Restaurants by Price")))
    v.append(table("gen_p5_localities", GRID_X[0], R3_Y, span(5), R3_H, 42,
                   [(column(R, "locality_city"), "Locality (city)"),
                    (measure(R, "Top 10 Locality Restaurants"), "Restaurants"),
                    (measure(R, "T10 Locality Avg Rating"), "Avg rating"),
                    (measure(R, "T10 Locality High Popularity %"), "High popularity"),
                    (measure(R, "T10 Locality Avg Cost (local)"), "Average cost for two (INR)")],
                   "Top 10 localities: rating, popularity and cost",
                   sort_field=measure(R, "Top 10 Locality Restaurants")))
    v.append(bar_chart("gen_p5_cuisines", GRID_X[5], R3_Y, span(4), R3_H, 43, "clusteredBarChart",
                       column("restaurant_cuisines", "cuisine"),
                       [(measure(R, "Top 10 Cuisine Restaurants"), "Restaurants")],
                       "Cuisine mix: top 10 cuisines in the selection", fill=ACCENT, category_label="Cuisine",
                       sort_field=measure(R, "Top 10 Cuisine Restaurants")))
    v.append(bar_chart("gen_p5_top_cities", GRID_X[9], R3_Y, span(3), R3_H, 44, "clusteredBarChart",
                       column(R, "city"), [(measure(R, "Top 10 City Restaurants"), "Restaurants")],
                       "Restaurants by city (top 10)", fill=HIGHLIGHT, category_label="City",
                       sort_field=measure(R, "Top 10 City Restaurants")))
    v.append(textbox("gen_p5_usd_note", 16, 704, 1248, 16, 50, [[(
        "US$ values are approximate, converted with World Bank 2017 annual average exchange rates.",
        {"fontFamily": "Segoe UI", "fontSize": "8pt", "color": TEXT2})]]))
    return v


def _page_filter_config(page_no: int) -> dict | None:
    """Page-level categorical filters (e.g. country = India), in the PBIR filterConfig form."""
    fs = []
    for i, (table, col, value) in enumerate(PAGE_FILTERS.get(page_no, [])):
        src = table[0]
        fs.append({
            "name": f"gen_page{page_no}_filter{i + 1}",
            "field": column(table, col),
            "type": "Categorical",
            "filter": {"Version": 2, "From": [{"Name": src, "Entity": table, "Type": 0}],
                       "Where": [{"Condition": {"In": {
                           "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": src}}, "Property": col}}],
                           "Values": [[{"Literal": {"Value": "'" + value.replace("'", "''") + "'"}}]]}}}]},
            "howCreated": "User"})
    return {"filters": fs} if fs else None


def _test_set_size() -> int:
    """Number of test-set restaurants, read from the saved confusion matrix (not typed in)."""
    import pandas as pd
    return int(pd.read_csv(config.PREDICTIONS_DIR / "confusion_matrix.csv", index_col=0).values.sum())


def insight_card(name, x, y, w, h, z, heading: str, body: str, accent: bool = False, body_pt: int = 9) -> dict:
    """White card with a bold heading and body text (text computed by src/insights.py)."""
    vis = textbox(name, x, y, w, h, z, [
        [(heading, {"fontFamily": "Segoe UI Semibold", "fontSize": "11pt", "color": ACCENT if accent else TEXT})],
        [(body, {"fontFamily": "Segoe UI", "fontSize": f"{body_pt}pt", "color": TEXT2})]])
    vis["visual"]["visualContainerObjects"] = container()
    vis["visual"]["visualContainerObjects"]["padding"] = props(top=6.0, bottom=4.0, left=12.0, right=12.0)
    return vis


def page6_visuals() -> list[dict]:
    """Insights and recommendations: 8 findings (2 columns x 4) and 6 recommendations, from outputs/insights."""
    import pandas as pd
    out = config.ROOT / "outputs" / "insights"
    f = pd.read_csv(out / "insights.csv")
    r = pd.read_csv(out / "recommendations.csv")
    v = page_frame(6, slicers=False)
    v.append(textbox("gen_p6_note", 16, 62, 1248, 26, 8, [[(
        f"Key findings for all {_restaurant_count():,} restaurants (no filters). Associations in observational "
        "data, not causes. Every number is computed from the data by src/insights.py.",
        {"fontFamily": "Segoe UI", "fontSize": "9pt", "color": TEXT2})]]))
    col_w, row_h, y0 = 404, 146, 94
    for i, row in enumerate(f.itertuples(index=False)):
        x = 16 + (i % 2) * (col_w + 12)
        y = y0 + (i // 2) * (row_h + 8)
        v.append(insight_card(f"gen_p6_f{i + 1}", x, y, col_w, row_h, 20 + i,
                              f"{row.id} · {row.theme}  ({row.key_number})", row.finding))
    rx, rw = 16 + 2 * (col_w + 12), PAGE_W - 16 - (16 + 2 * (col_w + 12))
    rh = (4 * row_h + 3 * 8 - 5 * 6) / 6
    for i, row in enumerate(r.itertuples(index=False)):
        v.append(insight_card(f"gen_p6_r{i + 1}", rx, y0 + i * (rh + 6), rw, rh, 40 + i,
                              # 6 short cards: 'based on' goes in the heading and the body is 8 pt, so the
                              # longest text (R1 with the sampling caveat) is not cut off in the PDF export
                              f"{row.id} · {row.title} ({row.based_on})", row.text, accent=True, body_pt=8))
    return v


def _restaurant_count() -> int:
    import pandas as pd
    return len(pd.read_csv(config.PROCESSED_DIR / "zomato_clean.csv", usecols=["restaurant_id"]))


PAGE_BUILDERS = {1: page1_visuals, 2: page2_visuals, 3: page3_visuals, 4: page4_visuals, 5: page5_visuals,
                 6: page6_visuals}


# ------------------------------------------------------------------ empty selections
def add_empty_state(visuals: list[dict]) -> tuple[list[dict], list[tuple]]:
    """Every titled visual that shows data gets a measure-driven title: the normal title, or
    'No data for this selection' when the slicers leave it empty (its first measure, or its table's row
    count, is blank). Returns the visuals and the title measures to add to the model."""
    measures = []
    for vis in visuals:
        body = vis["visual"]
        title = body.get("visualContainerObjects", {}).get("title", [{}])[0].get("properties", {})
        text = title.get("text", {}).get("expr", {}).get("Literal", {}).get("Value")
        qs = body.get("query", {}).get("queryState")
        if not text or not qs:
            continue
        fields = [p["field"] for role in qs.values() for p in role["projections"]]
        m = next((f["Measure"] for f in fields if "Measure" in f), None)
        if m:
            table, presence = m["Expression"]["SourceRef"]["Entity"], f"[{m['Property']}]"
        else:
            c = fields[0]["Column"]
            table = c["Expression"]["SourceRef"]["Entity"]
            presence = f"COUNTROWS ( '{table}' )"
        plain = text[1:-1].replace("''", "'")
        name = "Title " + vis["name"][len(GEN_PREFIX):]
        dax = f'IF ( ISBLANK ( {presence} ), "{NO_DATA}", "{plain.replace(chr(34), chr(34) * 2)}" )'
        measures.append((table, name, dax, None))
        title["text"] = {"expr": measure(table, name)}
    return visuals, measures


# ------------------------------------------------------------------ report-level writing
def register_theme() -> None:
    res = REPORT_DIR / "StaticResources" / "RegisteredResources"
    res.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(THEME_SRC, res / THEME_NAME)
    path = REPORT_DEF / "report.json"
    rep = json.loads(path.read_text(encoding="utf-8"))
    rep["themeCollection"]["customTheme"] = {
        "name": THEME_NAME, "reportVersionAtImport": rep["themeCollection"]["baseTheme"]["reportVersionAtImport"],
        "type": "RegisteredResources"}
    pkgs = [p for p in rep.get("resourcePackages", []) if p["name"] != "RegisteredResources"]
    pkgs.append({"name": "RegisteredResources", "type": "RegisteredResources",
                 "items": [{"name": THEME_NAME, "path": THEME_NAME, "type": "CustomTheme"}]})
    rep["resourcePackages"] = pkgs
    # Clicking a bar FILTERS the other visuals instead of cross-highlighting them (report-wide setting).
    rep.setdefault("settings", {})["defaultFilterActionIsDataFilter"] = True
    path.write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")


def _pages_meta() -> dict:
    return json.loads((REPORT_DEF / "pages" / "pages.json").read_text(encoding="utf-8"))


def write_page(page_id: str, display: str, visuals: list[dict], filters: dict | None = None) -> Path:
    pdir = REPORT_DEF / "pages" / page_id
    pdir.mkdir(parents=True, exist_ok=True)
    page_path = pdir / "page.json"
    page = json.loads(page_path.read_text(encoding="utf-8")) if page_path.exists() else {"$schema": PAGE_SCHEMA,
                                                                                         "name": page_id}
    page.update({"displayName": display, "displayOption": "FitToPage", "height": PAGE_H, "width": PAGE_W})
    if filters:
        page["filterConfig"] = filters
    else:
        page.pop("filterConfig", None)
    page_path.write_text(json.dumps(page, indent=2) + "\n", encoding="utf-8")
    vdir = pdir / "visuals"
    if vdir.exists():  # remove previously generated visuals only; keep anything added by hand
        for d in vdir.iterdir():
            if d.name.startswith(GEN_PREFIX):
                shutil.rmtree(d)
    for vis in visuals:
        assert vis["name"].startswith(GEN_PREFIX) and len(vis["name"]) <= 50
        (vdir / vis["name"]).mkdir(parents=True, exist_ok=True)
        (vdir / vis["name"] / "visual.json").write_text(json.dumps(vis, indent=2) + "\n", encoding="utf-8")
    meta = _pages_meta()
    if page_id not in meta["pageOrder"]:
        meta["pageOrder"].append(page_id)
    (REPORT_DEF / "pages" / "pages.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return pdir


def build(pages: list[int]) -> list[Path]:
    register_theme()
    ids = page_ids()
    labels = {n: PAGE_DISPLAY.get(n, lbl) for n, lbl, _ in TABS}
    existing = set(_pages_meta()["pageOrder"])
    # Register every requested page first, so the header tabs on all pages can link to them,
    # then (re)generate the visuals of every page that exists (tabs change when pages are added).
    for n in sorted(pages):
        if ids[n] not in existing:
            write_page(ids[n], labels[n], [])
    order = _pages_meta()["pageOrder"]
    built, title_measures = {}, []
    for n in PAGE_BUILDERS:
        if ids[n] in order:
            built[n], ms = add_empty_state(PAGE_BUILDERS[n]())
            title_measures += ms
    patch_model(title_measures)
    paths = [write_page(ids[n], labels[n], v, _page_filter_config(n)) for n, v in built.items()]
    meta = _pages_meta()   # page order = tab order
    meta["pageOrder"] = [ids[n] for n, _, _ in TABS if ids[n] in meta["pageOrder"]] + \
        [p for p in meta["pageOrder"] if p not in {ids[n] for n, _, _ in TABS}]
    (REPORT_DEF / "pages" / "pages.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return paths


# ------------------------------------------------------------------ schema validation (optional, needs internet)
def validate(paths: list[Path]) -> list[str]:
    import urllib.request

    from jsonschema import Draft7Validator
    from referencing import Registry, Resource

    cache: dict[str, dict] = {}

    def retrieve(uri: str):
        if uri not in cache:
            url = uri.replace("https://developer.microsoft.com/json-schemas/",
                              "https://raw.githubusercontent.com/microsoft/json-schemas/main/")
            with urllib.request.urlopen(url, timeout=30) as r:
                cache[uri] = json.loads(r.read())
        return Resource.from_contents(cache[uri])

    registry = Registry(retrieve=retrieve)
    errors = []
    files = [REPORT_DEF / "report.json", REPORT_DEF / "pages" / "pages.json"]
    for p in paths:
        files.append(p / "page.json")
        files += sorted((p / "visuals").glob("*/visual.json"))
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        schema = retrieve(doc["$schema"]).contents
        for e in Draft7Validator(schema, registry=registry).iter_errors(doc):
            errors.append(f"{f.relative_to(PBI_DIR)}: {e.message[:200]} at {list(e.absolute_path)}")
    print(f"Validated {len(files)} files against Microsoft's published schemas: {len(errors)} error(s).")
    return errors


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Generate PBIP pages (run with Power BI Desktop closed).")
    ap.add_argument("--page", type=int, action="append", required=True, help="Page number to generate (1-4)")
    ap.add_argument("--validate", action="store_true", help="Validate JSON against the published schemas")
    a = ap.parse_args()
    out = build(a.page)
    for p in out:
        print("wrote", p.relative_to(PBI_DIR), "-", len(list((p / "visuals").glob("*/visual.json"))), "visuals")
    if a.validate:
        for err in validate(out):
            print("  ERROR", err)
