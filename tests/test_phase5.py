"""Phase 5: generated Tableau workbook (dashboards/tableau/RestaurantIntelligence.twb)."""
from __future__ import annotations

import re
from pathlib import Path
import xml.etree.ElementTree as ET

import pandas as pd
import pytest

from src import tableau_twb as tw


@pytest.fixture(scope="module")
def wb():
    if not tw.OUT.exists():
        pytest.skip("Run `python -m src.tableau_twb --dashboard 1` first")
    return tw.OUT.read_text(encoding="utf-8"), ET.parse(tw.OUT).getroot()


def test_same_format_as_tableau_wrote(wb):
    text, root = wb
    starter = ET.parse(tw.STARTER).getroot()
    assert root.get("version") == starter.get("version") == "18.1"
    assert root.get("source-build") == starter.get("source-build")
    assert "ISO3166_2" not in text           # country = names
    assert "TableauTemp" not in text         # no extract in a Windows temp folder
    # compare file names only: the .twb is generated on Windows (absolute D:/ paths), tests also run on macOS
    dbs = sorted(Path(e.get("dbname")).name for e in root.iter("connection") if e.get("class") == "hyper")
    from src.tableau_india import HYPER_INDIA
    from src.tableau_success import HYPER_SUCCESS
    assert dbs == sorted([tw.HYPER_RESTAURANTS.name, tw.HYPER_PAIRS.name, HYPER_SUCCESS.name,
                          HYPER_INDIA.name])  # Tableau Public needs extracts


def test_extracts_match_the_csvs():
    """The .hyper extracts hold exactly the rows and totals of the processed CSVs."""
    from tableauhyperapi import Connection, HyperProcess, Telemetry
    import tempfile
    d = pd.read_csv(tw.PROC / "zomato_clean.csv", encoding="utf-8")
    pairs = pd.read_csv(tw.PAIRS_CITY_CSV, encoding="utf-8")
    with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU,
                      parameters={"log_dir": tempfile.gettempdir()}) as hp:
        with Connection(hp.endpoint, str(tw.HYPER_RESTAURANTS)) as c:
            n, cities, votes, rated = c.execute_list_query(
                'SELECT COUNT(*), COUNT(DISTINCT city), SUM(votes), COUNT(aggregate_rating) FROM "Extract"."Extract"')[0]
        with Connection(hp.endpoint, str(tw.HYPER_PAIRS)) as c:
            npairs = c.execute_scalar_query('SELECT COUNT(*) FROM "Extract"."Extract"')
    assert (n, cities, votes, rated) == (len(d), d["city"].nunique(), d["votes"].sum(), d["aggregate_rating"].notna().sum())
    assert npairs == len(pairs)


def test_dashboard1_sheets_and_layout(wb):
    _, root = wb
    names = [w.get("name") for w in root.find("worksheets")]
    d1 = ["KPI - Restaurants", "KPI - Cities", "KPI - Average rating", "KPI - Total votes", "KPI - Online delivery",
          "Restaurants by city (map)", "Average rating by city (top 15)", "Cuisine mix by city (share of listings)"]
    d2 = ["KPI - Individual cuisines", "KPI - Price range 1 (Budget)", "KPI - Price range 2 (Moderate)", "KPI - Price range 3 (Expensive)", "KPI - Price range 4 (Luxury)",
          "Restaurants by cuisine (top 15)", "Average rating by cuisine", "Average price range by cuisine", "Cuisines by city group"]
    d3 = ["Model comparison (test set)", "Confusion matrix (test set)", "Predicted vs actual class split",
          "Feature importance (top 15)"]
    d5 = [n for n in names[len(d1 + d2 + d3):]]
    assert names[:len(d1 + d2 + d3)] == d1 + d2 + d3
    assert d5 and all(n.startswith(("KPI - India", "India - ", "Message - ")) for n in d5)
    dashes = root.find("dashboards").findall("dashboard")
    assert [d.get("name") for d in dashes] == ["Location intelligence", "Cuisine and pricing", "India deep dive",
                                               "Success prediction", "Insights and recommendations"]
    for dash, expected in zip(dashes, (d1, d2, d5, d3)):
        size = dash.find("size")
        from src.tableau_india import INDIA_H   # India deep dive is taller (scrolls); all others 1280 x 720
        height = str(INDIA_H) if dash.get("name") == "India deep dive" else "720"
        assert (size.get("maxwidth"), size.get("maxheight")) == ("1280", height)
        zones = list(dash.find("zones").iter("zone"))      # nested inside the root layout zone, as Tableau does
        placed = {z.get("name") for z in zones if z.get("name")}
        assert placed == set(expected)       # every sheet of that dashboard is on it
        for z in zones:                      # inside the dashboard (units of 1/100,000)
            x, y, w, h = (int(z.get(k)) for k in ("x", "y", "w", "h"))
            assert 0 <= x and x + w <= 100000 and 0 <= y and y + h <= 100000


def test_every_used_field_is_declared(wb):
    """Each field a worksheet references must have a column-instance in that worksheet's dependencies."""
    _, root = wb
    for ws in root.find("worksheets"):
        declared = {f"[{d.get('datasource')}].{ci.get('name')}"
                    for d in ws.iter("datasource-dependencies") for ci in d.findall("column-instance")}
        cols = {f"[{d.get('datasource')}].{c.get('name')}" for d in ws.iter("datasource-dependencies")
                for c in d.findall("column")}
        used = set(re.findall(r"\[federated\.[^\]]+\]\.\[[^\]]+\]", ET.tostring(ws, encoding="unicode")))
        assert used, ws.get("name")
        for u in used:
            assert u in declared, f"{ws.get('name')}: {u} not declared"
        for ci in ws.iter("column-instance"):
            ds = next(d.get("datasource") for d in ws.iter("datasource-dependencies") if ci in list(d))
            assert f"[{ds}].{ci.get('column')}" in cols, f"{ws.get('name')}: column {ci.get('column')} missing"


def test_theme_b_colours(wb):
    text, _ = wb
    for colour in (tw.SLATE, tw.ACCENT, tw.HIGHLIGHT, tw.PAGE_BG, tw.BORDER, tw.TEXT2):
        assert colour in text.lower(), colour


def test_pairs_file_matches_source():
    pairs = pd.read_csv(tw.PAIRS_CITY_CSV, encoding="utf-8")
    src = pd.read_csv(tw.PROC / "restaurant_cuisines.csv", encoding="utf-8")
    assert list(pairs.columns) == ["restaurant_id", "country", "city", "cuisine", "price_range", "aggregate_rating"]
    assert len(pairs) == len(src) and pairs["city"].notna().all()


def test_cuisine_groups_are_real_top_cuisines(wb):
    text, _ = wb
    top = tw.big_city_top_cuisines(pd.read_csv(tw.PAIRS_CITY_CSV, encoding="utf-8"))
    assert top == ["North Indian", "Chinese", "Fast Food", "Mughlai", "Bakery"]
    assert all(f"&quot;{c}&quot;" in text for c in top + ["Other"])


def test_valid_against_tableaus_own_schema(wb):
    """The schema shipped inside Tableau Public (the same check Tableau runs when it opens a workbook)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("validate_twb", tw.config.ROOT / "scripts" / "validate_twb.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not mod.RCC_CANDIDATES:   # Windows install folder or macOS app bundle
        pytest.skip("Tableau Public not installed on this machine")
    assert tw.validate_against_tableau(tw.STARTER) == []      # sanity: Tableau's own file passes
    assert tw.validate_against_tableau(tw.OUT) == []


def _ws(root, name):
    return next(w for w in root.find("worksheets") if w.get("name") == name)


def test_dashboard1_fixes_round2(wb):
    """Theme B cuisine colours + legend, readable labels, clean axis/field labels, map sizes, KPI alignment."""
    _, root = wb
    pairs_ds = next(d for d in root.find("datasources") if d.get("caption") == "restaurant_cuisines_city")
    enc = pairs_ds.find("style/style-rule/encoding")
    colours = {m.find("bucket").text.strip('"'): m.get("to") for m in enc.findall("map")}
    assert colours == {"North Indian": "#8e1520", "Chinese": "#cb202d", "Fast Food": "#e23744",
                       "Mughlai": "#e8838b", "Bakery": "#f5c6ca", "Other": "#a1a1aa"}
    zones = list(root.find("dashboards/dashboard/zones").iter("zone"))
    assert any(z.get("type-v2") == "color" and z.get("name") == "Cuisine mix by city (share of listings)" for z in zones)  # legend
    runs = _ws(root, "Cuisine mix by city (share of listings)").findall(".//customized-label/formatted-text/run")
    assert [r.get("fontcolor") for r in runs] == ["#ffffff", "#18181b"]     # white on dark, dark on light
    rating = _ws(root, "Average rating by city (top 15)")
    assert rating.find(".//style-rule[@element='axis']/format[@attr='title']").get("value") == "Average rating"
    for name in ("Average rating by city (top 15)", "Cuisine mix by city (share of listings)"):
        hidden = _ws(root, name).findall(".//style-rule[@element='worksheet']/format[@attr='display-field-labels']")
        assert {f.get("scope") for f in hidden} == {"rows", "cols"} and all(f.get("value") == "false" for f in hidden)
    size = _ws(root, "Restaurants by city (map)").find(".//style-rule[@element='mark']/encoding[@attr='size']")
    assert float(size.get("min-size")) > 0 and float(size.get("max-size")) >= float(size.get("min-size"))
    for k in ("KPI - Restaurants", "KPI - Online delivery"):
        assert _ws(root, k).find(".//style-rule[@element='cell']/format[@attr='text-align']").get("value") == "left"
    rz = next(z for z in zones if z.get("name") == "Average rating by city (top 15)")
    assert int(rz.get("h")) >= 70000                                        # full-height column for 15 bars


def test_dashboard2_contents(wb):
    """Price cards filter one price range each; cuisine charts share the same top-15 filter; legend present."""
    _, root = wb
    for n in (1, 2, 3, 4):
        f = _ws(root, [w.get("name") for w in root.find("worksheets") if w.get("name").startswith(f"KPI - Price range {n}")][0])
        flt = f.find(".//filter[@class='quantitative']")
        assert (flt.find("min").text, flt.find("max").text) == (str(n), str(n))
    for name in ("Restaurants by cuisine (top 15)", "Average rating by cuisine", "Average price range by cuisine", "Cuisines by city group"):
        g = _ws(root, name).find(".//groupfilter[@function='end']")
        assert g.get("count") == "15" and g.find("groupfilter").get("expression") == "COUNTD([restaurant_id])"
    d2 = root.find("dashboards").findall("dashboard")[1]
    assert any(z.get("type-v2") == "color" and z.get("name") == "Cuisines by city group" for z in d2.iter("zone"))
    assert "<map to=" not in ET.tostring(_ws(root, "Cuisines by city group"), encoding="unicode")   # default palette


def test_dashboard2_fixes_round1(wb):
    """Price cards: one-line labels. Rating/price charts: fixed 0-5 / 0-4 axis, tick every 1, whole-number ticks."""
    _, root = wb
    titles = [_ws(root, w.get("name")).find(".//title/formatted-text/run").text
              for w in root.find("worksheets") if w.get("name").startswith("KPI - Price range")]
    assert titles == ["Budget (1)", "Moderate (2)", "Expensive (3)", "Luxury (4)"]
    for name, mx in (("Average rating by cuisine", "5"), ("Average price range by cuisine", "4")):
        enc = _ws(root, name).find(".//style-rule[@element='axis']/encoding[@attr='space']")
        assert (enc.get("min"), enc.get("max"), enc.get("major-spacing")) == ("0", mx, "1")
        assert _ws(root, name).find(".//style-rule[@element='axis']/format[@attr='text-format']") is not None


def test_sheet_names_are_readable(wb):
    """Client request: clean, readable sheet names (no cryptic abbreviations, no truncation)."""
    _, root = wb
    for w in root.find("worksheets"):
        n = w.get("name")
        assert n[0].isupper() and "  " not in n and not n.endswith((" ", "-")), n
        assert not re.search(r"\b(avg|Avg|Sheet \d+)\b", n), n


def test_success_dashboard_data_matches_model_outputs():
    from src import config
    from src.tableau_success import SUCCESS_CSV, success_notes
    from src.target import TARGET_DEFINITION
    if not SUCCESS_CSV.exists():
        pytest.skip("Run `python -m src.tableau_twb --dashboard 1` first")
    d = pd.read_csv(SUCCESS_CSV)
    P = config.PREDICTIONS_DIR
    cm = pd.read_csv(P / "confusion_matrix.csv", index_col=0)
    conf = d[d["section"] == "confusion"]
    assert conf["count"].sum() == cm.values.sum()
    assert conf.set_index(["item", "series"])["count"].loc[("Medium", "Medium")] == cm.loc["Medium", "Medium"]
    split = d[d["section"] == "class_split"]
    n = len(pd.read_csv(P / "popularity_predictions.csv"))
    assert split.groupby("series")["count"].sum().eq(n).all()
    comp = pd.read_csv(P / "model_comparison.csv")
    assert set(d.loc[d["section"] == "comparison", "item"]) == set(comp["model"])
    imp = pd.read_csv(P / "feature_importance.csv").head(15)
    from src.powerbi_export import _feature_label
    assert list(d.loc[d["section"] == "importance", "item"]) == [_feature_label(f) for f in imp["feature"]]
    assert success_notes()[0] == TARGET_DEFINITION


def test_insights_dashboard_uses_generated_findings(wb):
    """Dashboard 4: text only (no filters, so no empty-chart state); findings come from outputs/insights."""
    from src import config
    _, root = wb
    dash = next(d for d in root.find("dashboards") if d.get("name") == tw.DASH4)
    text = " ".join(r.text or "" for r in dash.iter("run"))
    f = pd.read_csv(config.ROOT / "outputs" / "insights" / "insights.csv")
    r = pd.read_csv(config.ROOT / "outputs" / "insights" / "recommendations.csv")
    assert all(row.finding in text for row in f.itertuples()) and all(row.title in text for row in r.itertuples())
    assert not any(z.get("name") for z in dash.iter("zone"))   # no worksheets, so nothing can be left empty


def test_only_the_india_dashboard_has_user_controls(wb):
    """Item 6b: only 'India deep dive' lets users filter (City / Locality parameters); every other dashboard has
    no filter or parameter controls, so a selection can never leave one of its charts empty."""
    _, root = wb
    for d in root.find("dashboards"):
        controls = [z for z in d.iter("zone") if z.get("type-v2") in ("filter", "paramctrl")]
        if d.get("name") == "India deep dive":
            assert sorted(z.get("param") for z in controls) == ["[Parameters].[Parameter 1]",
                                                                "[Parameters].[Parameter 2]"]
        else:
            assert not controls, d.get("name")


def test_india_every_chart_has_a_no_data_message_above_it(wb):
    from src.tableau_india import NO_DATA
    text, root = wb
    dash = next(d for d in root.find("dashboards") if d.get("name") == "India deep dive")
    zones = {z.get("name"): z for z in dash.iter("zone") if z.get("name") and z.get("type-v2") is None}
    charts = [n for n in zones if n.startswith("India - ")]
    assert len(charts) == 7
    for c in charts:
        msg = zones[f"Message - {c.replace('India - ', '')}"]
        assert msg.get("x") == zones[c].get("x") and int(msg.get("y")) < int(zones[c].get("y"))
    assert "Message - KPI row" in zones
    assert f"&quot;{NO_DATA}&quot;" in text
    for ws in root.find("worksheets"):   # charts and KPIs filtered by the selection (context filter); messages not
        n = ws.get("name")
        f = [x for x in ws.iter("filter") if "Calculation_in_selection" in (x.get("column") or "")]
        if n.startswith(("India - ", "KPI - India")):
            assert f and f[0].get("context") == "true", n
        elif n.startswith("Message - "):
            assert not f, n


def test_india_tableau_rows_count_each_restaurant_once():
    from src.tableau_india import TABLEAU_CSV
    d = pd.read_csv(TABLEAU_CSV)
    clean = pd.read_csv(tw.PROC / "zomato_clean.csv")
    india = clean[clean["country"] == "India"]
    assert d["is_primary_row"].sum() == len(india) == d["restaurant_id"].nunique()
    assert d.groupby("restaurant_id")["is_primary_row"].sum().eq(1).all()
    prim = d[d["is_primary_row"] == 1].set_index("restaurant_id")
    assert prim["aggregate_rating"].mean() == pytest.approx(india["aggregate_rating"].mean())


def test_india_sheets_use_india_data_as_primary_source(wb):
    """Tableau's first datasource in a sheet is its primary one; 'Parameters' first made every India sheet empty."""
    _, root = wb
    n = 0
    for ws in root.find("worksheets"):
        if ws.get("name").startswith(("India - ", "KPI - India", "Message - ")):
            names = [d.get("name") for d in ws.find("table/view/datasources")]
            deps = [d.get("datasource") for d in ws.find("table/view").findall("datasource-dependencies")]
            assert names[0].startswith("federated.") and names[-1] == "Parameters", ws.get("name")
            assert deps[0].startswith("federated.") and deps[-1] == "Parameters", ws.get("name")
            n += 1
    assert n == 5 + 7 + 8


def test_india_dashboard_is_tall_with_two_charts_per_row(wb):
    from src.tableau_india import INDIA_H
    _, root = wb
    dash = next(d for d in root.find("dashboards") if d.get("name") == "India deep dive")
    size = dash.find("size")
    assert (size.get("maxwidth"), size.get("maxheight")) == ("1280", str(INDIA_H))
    charts = [z for z in dash.iter("zone") if (z.get("name") or "").startswith("India - ") and z.get("type-v2") is None]
    rows = {}
    for z in charts:
        rows.setdefault(z.get("y"), []).append(z)
    assert max(len(r) for r in rows.values()) <= 2
    kpis = [z for z in dash.iter("zone") if (z.get("name") or "").startswith("KPI - India") and z.get("type-v2") is None]
    other = next(d for d in root.find("dashboards") if d.get("name") == "Location intelligence")
    k1 = next(z for z in other.iter("zone") if z.get("name") == "KPI - Restaurants" and z.get("type-v2") is None)
    assert round(int(kpis[0].get("h")) * INDIA_H / 100000) == round(int(k1.get("h")) * 720 / 100000)   # same 80 px


def test_india_multi_measure_charts_have_no_overlapping_labels(wb):
    _, root = wb
    for n in ("India - Rating and High popularity by city", "India - Online delivery and table booking by city",
              "India - Top 10 localities (rating and High popularity)", "India - Cost for two by city (INR and US$)"):
        ws = _ws(root, n)
        assert not ws.findall(".//encodings/text"), n
        assert ws.find(".//format[@attr='mark-labels-show']").get("value") == "false", n


def test_twbx_packages_workbook_and_extracts():
    import zipfile
    if not tw.TWBX.exists():
        pytest.skip("Run `python -m src.tableau_twb --dashboard 1` first")
    with zipfile.ZipFile(tw.TWBX) as z:
        names = set(z.namelist())
        twb = z.read("RestaurantIntelligence.twb").decode("utf-8")
    dbs = set(re.findall(r"dbname='([^']+\.hyper)'", twb))
    assert dbs and all(d.startswith("Data/tableau/") for d in dbs)
    assert dbs <= names and len(dbs) == 4
    assert twb.count("<dashboard name=") == 5


def test_only_dashboard_tabs_visible(wb):
    """All worksheets are hidden (each one is used on a dashboard); the 5 dashboards are the only tabs."""
    _, root = wb
    on_dash = {z.get("name") for d in root.find("dashboards") for z in d.iter("zone")
               if z.get("name") and z.get("type-v2") is None}
    sheets = {w.get("name") for w in root.find("worksheets")}
    assert sheets <= on_dash                                    # hiding is only allowed for sheets on a dashboard
    wins = root.find("windows")
    assert all(w.get("hidden") == "true" for w in wins if w.get("class") == "worksheet")
    assert [w.get("name") for w in wins if w.get("class") == "dashboard" and w.get("hidden") != "true"] == \
        [d.get("name") for d in root.find("dashboards")] or len([w for w in wins if w.get("class") == "dashboard"]) == 5
