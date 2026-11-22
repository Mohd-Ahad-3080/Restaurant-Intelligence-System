"""Tests for the generated Power BI Project (PBIP): model measures and report visuals."""
from __future__ import annotations

import json
import re

import pytest

from src.powerbi_pbip import (GEN_PREFIX, MEASURES, MODEL_DIR, PAGE_H, PAGE_W, REPORT_DEF, REPORT_DIR, THEME_NAME,
                              _pages_meta)

PAGES_DIR = REPORT_DEF / "pages"


def _visuals():
    return [(p, json.loads(p.read_text(encoding="utf-8"))) for p in sorted(PAGES_DIR.glob("*/visuals/*/visual.json"))]


@pytest.fixture(scope="module")
def visuals():
    v = _visuals()
    if not v:
        pytest.skip("Run `python -m src.powerbi_pbip --page 1` first")
    return v


def _tmdl_measures() -> set[tuple[str, str]]:
    found = set()
    for f in (MODEL_DIR / "tables").glob("*.tmdl"):
        for m in re.finditer(r"^\tmeasure (?:'((?:[^']|'')+)'|([A-Za-z_]\w*)) =", f.read_text(encoding="utf-8"), re.M):
            found.add((f.stem, (m.group(1) or m.group(2)).replace("''", "'")))
    return found


def test_all_measures_are_in_the_model_once():
    """Model = the MEASURES list + one generated 'Title ...' measure per data visual (empty-selection titles)."""
    expected = {(t, n) for t, n, _, _ in MEASURES}
    found = _tmdl_measures()
    assert {m for m in found if not m[1].startswith("Title ")} == expected
    text = "".join(f.read_text(encoding="utf-8") for f in (MODEL_DIR / "tables").glob("*.tmdl"))
    assert len(re.findall(r"^\tmeasure ", text, re.M)) == len(found)  # no duplicates after re-runs


def test_only_needed_relationships_both_directions():
    rel = (MODEL_DIR / "relationships.tmdl").read_text(encoding="utf-8")
    assert rel.count("relationship ") == 2
    assert rel.count("crossFilteringBehavior: bothDirections") == 2


def test_theme_registered():
    rep = json.loads((REPORT_DEF / "report.json").read_text(encoding="utf-8"))
    assert rep["themeCollection"]["customTheme"]["name"] == THEME_NAME
    assert (REPORT_DIR / "StaticResources" / "RegisteredResources" / THEME_NAME).exists()


def test_pages_are_1280x720_and_listed():
    meta = _pages_meta()
    for pid in meta["pageOrder"]:
        page = json.loads((PAGES_DIR / pid / "page.json").read_text(encoding="utf-8"))
        assert (page["width"], page["height"]) == (PAGE_W, PAGE_H)


def test_visuals_fit_on_page_and_have_unique_names(visuals):
    for path, v in visuals:
        pos = v["position"]
        assert 0 <= pos["x"] and pos["x"] + pos["width"] <= PAGE_W, path
        assert 0 <= pos["y"] and pos["y"] + pos["height"] <= PAGE_H, path
        assert v["name"] == path.parent.name and len(v["name"]) <= 50
    for page in PAGES_DIR.iterdir():
        if page.is_dir():
            names = [p.parent.name for p in page.glob("visuals/*/visual.json")]
            assert len(names) == len(set(names))


def test_visual_fields_exist_in_model(visuals):
    """Every measure a visual uses must be defined; every column must exist in its table."""
    measures = _tmdl_measures()
    for path, v in visuals:
        text = json.dumps(v)
        for m in re.finditer(r'\{"Measure": \{"Expression": \{"SourceRef": \{"Entity": "([^"]+)"\}\}, '
                             r'"Property": "([^"]+)"\}\}', text):
            assert (m.group(1), m.group(2)) in measures, f"{path}: unknown measure {m.groups()}"
        for c in re.finditer(r'\{"Column": \{"Expression": \{"SourceRef": \{"Entity": "([^"]+)"\}\}, '
                             r'"Property": "([^"]+)"\}\}', text):
            tmdl = (MODEL_DIR / "tables" / f"{c.group(1)}.tmdl").read_text(encoding="utf-8")
            assert re.search(rf"^\tcolumn {re.escape(c.group(2))}( = .*)?$", tmdl, re.M), \
                f"{path}: unknown column {c.groups()}"


def test_pages_in_tab_order_and_tab_links():
    from src.powerbi_pbip import PAGE_DISPLAY, TABS, page_ids
    meta, ids = _pages_meta(), page_ids()
    nums = [n for n, _, _ in TABS]
    assert meta["pageOrder"] == [ids[n] for n in nums]
    for n, label, _ in TABS:
        page = json.loads((PAGES_DIR / ids[n] / "page.json").read_text(encoding="utf-8"))
        assert page["displayName"] == PAGE_DISPLAY.get(n, label)
        for m in nums:
            tab = json.loads((PAGES_DIR / ids[n] / "visuals" / f"gen_hdr_tab{m}" / "visual.json").read_text(
                encoding="utf-8"))
            link = tab["visual"]["visualContainerObjects"].get("visualLink")
            if m == n:
                assert link is None and (PAGES_DIR / ids[n] / "visuals" / f"gen_hdr_tab{m}_underline").exists()
            else:
                assert link[0]["properties"]["navigationSection"]["expr"]["Literal"]["Value"] == f"'{ids[m]}'"


def test_every_chart_has_scrollbar_fix(visuals):
    """All bar/column charts: small minimum category width and tight padding (10 bars fit, no scrollbar)."""
    n = 0
    for path, d in visuals:
        if d["visual"]["visualType"] in ("clusteredBarChart", "clusteredColumnChart", "hundredPercentStackedBarChart"):
            ax = d["visual"]["objects"]["categoryAxis"][0]["properties"]
            assert ax["preferredCategoryWidth"]["expr"]["Literal"]["Value"] == "14.0D", path
            assert "padding" in d["visual"]["visualContainerObjects"], path
            n += 1
    assert n == 15   # Page 1: 5, Page 2: 3, Page 3: 2, Page 4: 2, India page: 3


def test_india_page_filter_slicers_and_usd():
    """India deep dive: page filter country = India; locality and city slicers; US$ column in the model."""
    import json as _json
    from src.powerbi_pbip import page_ids
    page = _json.loads((PAGES_DIR / page_ids()[5] / "page.json").read_text(encoding="utf-8"))
    f = page["filterConfig"]["filters"][0]
    assert f["field"]["Column"]["Property"] == "country"
    assert f["filter"]["Where"][0]["Condition"]["In"]["Values"] == [[{"Literal": {"Value": "'India'"}}]]
    v = _page_visuals(5)
    assert {"gen_slc_locality", "gen_slc_city"} <= set(v) and "gen_slc_country" not in v
    cities = v["gen_p5_cities"]["visual"]["query"]["queryState"]["Values"]["projections"]
    assert "Avg Cost for Two (US$ approx)" in [p["field"].get("Measure", {}).get("Property") for p in cities]
    tmdl = (MODEL_DIR / "tables" / "restaurants.tmdl").read_text(encoding="utf-8")
    assert tmdl.count("\tcolumn avg_cost_for_two_usd\n") == 1 and tmdl.count('{"avg_cost_for_two_usd", type number}') == 1


def test_page1_has_required_elements(visuals):
    page1 = _pages_meta()["pageOrder"][0]
    v = {p.parent.name: d for p, d in visuals if p.parts[-4] == page1}
    types = [d["visual"]["visualType"] for d in v.values()]
    assert types.count("card") == 5 and types.count("slicer") == 4
    clickable = [n for n, d in v.items() if d["visual"]["visualType"] == "actionButton"
                 and not n.endswith(("_strip", "_underline"))]
    from src.powerbi_pbip import TABS
    assert len(clickable) == len(TABS) + 1              # header tabs + Reset (strips are blank buttons)
    assert "shape" not in types                         # shape ignored our fill colour; boxes are used instead
    kpis = [d["visual"]["query"]["queryState"]["Values"]["projections"][0]["field"]["Measure"]["Property"]
            for d in v.values() if d["visual"]["visualType"] == "card"]
    assert kpis == ["Restaurants", "Cities", "Avg Rating", "Total Votes", "Online Delivery %"]
    assert all(n.startswith(GEN_PREFIX) for n in v)
    assert "gen_p1_map_placeholder" not in v and "gen_p1_by_country" in v


def test_page1_theme_b_layout(visuals):
    page1 = _pages_meta()["pageOrder"][0]
    v = {p.parent.name: d for p, d in visuals if p.parts[-4] == page1}
    bg = lambda d: d["visual"]["visualContainerObjects"]["background"][0]["properties"]["color"]["solid"]["color"]
    lit_ = lambda e: e["expr"]["Literal"]["Value"]
    assert lit_(bg(v["gen_hdr_bg"])) == "'#1F2329'"                       # slate header, not red
    assert v["gen_hdr_tab1_underline"]["position"]["height"] == 3
    # thin strips = blank buttons (a text box this thin showed a grey scrollbar stub in the PDF export)
    for name, colour in [("gen_hdr_tab1_underline", "'#E23744'")] + [(f"gen_p1_kpi{i}_strip", "'#CB202D'")
                                                                    for i in range(1, 6)]:
        o = v[name]["visual"]["objects"]
        assert v[name]["visual"]["visualType"] == "actionButton", name
        assert lit_(o["text"][0]["properties"]["show"]) == "false"
        fills = {s["selector"]["id"]: lit_(s["properties"]["fillColor"]["solid"]["color"])
                 for s in o["fill"] if "selector" in s}
        assert set(fills.values()) == {colour}, name
        assert all(lit_(s["properties"]["roundEdge"]) == "0L" for s in o["shape"])
    for name, d in v.items():                                              # no auto subtitles anywhere
        assert lit_(d["visual"]["visualContainerObjects"]["subTitle"][0]["properties"]["show"]) == "false", name
    for d in v.values():
        if d["visual"]["visualType"] == "card":                            # label on top, nothing clipped below
            assert lit_(d["visual"]["objects"]["categoryLabels"][0]["properties"]["show"]) == "false"
            assert d["visual"]["visualContainerObjects"]["title"][0]["properties"]["text"]
    charts = [d for d in v.values() if d["visual"]["visualType"] in ("clusteredBarChart", "clusteredColumnChart")]
    assert len(charts) == 5
    for d in charts:                                                       # white cards with grey border
        assert lit_(bg(d)) == "'#FFFFFF'"
        b = d["visual"]["visualContainerObjects"]["border"][0]["properties"]
        assert lit_(b["color"]["solid"]["color"]) == "'#E4E4E7'"
    svc = v["gen_p1_services"]["visual"]
    assert svc["query"]["queryState"]["Category"]["projections"][0]["field"]["Column"]["Property"] == "service"
    assert lit_(svc["objects"]["legend"][0]["properties"]["show"]) == "false"
    ax = svc["objects"]["valueAxis"][0]["properties"]
    assert (lit_(ax["start"]), lit_(ax["end"])) == ("0.0D", "1.0D")


def test_page1_buttons_labels_and_interactions(visuals):
    page1 = _pages_meta()["pageOrder"][0]
    v = {p.parent.name: d for p, d in visuals if p.parts[-4] == page1}
    lit_ = lambda e: e["expr"]["Literal"]["Value"]
    for n in range(1, 5):
        o = v[f"gen_hdr_tab{n}"]["visual"]["objects"]
        # on/off switches must be global (no state selector), otherwise Power BI ignores them
        assert o["fill"] == [{"properties": {"show": {"expr": {"Literal": {"Value": "false"}}}}}]
        assert "selector" not in o["text"][0] and lit_(o["text"][0]["properties"]["show"]) == "true"
        assert "selector" not in o["outline"][0] and lit_(o["outline"][0]["properties"]["show"]) == "false"
        default = next(s for s in o["text"] if s.get("selector", {}).get("id") == "default")["properties"]
        assert lit_(default["fontColor"]["solid"]["color"]) == ("'#FFFFFF'" if n == 1 else "'#A1A1AA'")
    for d in v.values():
        if d["visual"]["visualType"] in ("clusteredBarChart", "clusteredColumnChart"):
            lab = d["visual"]["objects"]["labels"][0]["properties"]
            assert lit_(lab["labelPosition"]) == "'OutsideEnd'" and lit_(lab["enableBackground"]) == "true"
            assert lit_(d["visual"]["objects"]["categoryAxis"][0]["properties"]["innerPadding"]) == "15.0D"
    rep = json.loads((REPORT_DEF / "report.json").read_text(encoding="utf-8"))
    assert rep["settings"]["defaultFilterActionIsDataFilter"] is True   # filter, not highlight


def test_top10_measures_use_skip_ranking():
    """Dense ranking lets ties through (Brazil/UAE/South Africa tie at 60 -> 14 countries)."""
    for _, name, dax, _ in MEASURES:
        if name.startswith("Top 10"):
            assert "Skip )" in dax and "Dense" not in dax


def test_services_table_defined():
    text = (MODEL_DIR / "tables" / "services.tmdl").read_text(encoding="utf-8")
    assert '"Table booking", 1' in text and '"Online delivery", 2' in text
    assert "ref table services\n" in (MODEL_DIR / "model.tmdl").read_text(encoding="utf-8")


def _page_visuals(n: int) -> dict:
    from src.powerbi_pbip import page_ids
    pid = page_ids()[n]
    return {p.parent.name: json.loads(p.read_text(encoding="utf-8"))
            for p in (PAGES_DIR / pid / "visuals").glob("*/visual.json")}


def _lit(e):
    return e["expr"]["Literal"]["Value"]


def _measure_dax(table: str, name: str) -> str:
    text = (MODEL_DIR / "tables" / f"{table}.tmdl").read_text(encoding="utf-8")
    quoted = "'" + name.replace("'", "''") + "'"
    return re.search(rf"^\tmeasure {re.escape(quoted)} = (.*)$", text, re.M).group(1)


def _title_text(vis: dict) -> str:
    """A visual's title: literal text, or the DAX of its measure-driven title."""
    t = vis["visualContainerObjects"]["title"][0]["properties"]["text"]["expr"]
    if "Literal" in t:
        return t["Literal"]["Value"]
    m = t["Measure"]
    return _measure_dax(m["Expression"]["SourceRef"]["Entity"], m["Property"])


def test_every_data_visual_shows_no_data_message(visuals):
    """Client request: a chart left empty by the slicers says 'No data for this selection' (measure-driven title)."""
    from src.powerbi_pbip import NO_DATA
    n = 0
    for path, d in visuals:
        vis = d["visual"]
        title = vis.get("visualContainerObjects", {}).get("title", [{}])[0].get("properties", {})
        if not vis.get("query") or "text" not in title:
            continue
        m = title["text"]["expr"]["Measure"]           # never a fixed literal on a data visual
        dax = _measure_dax(m["Expression"]["SourceRef"]["Entity"], m["Property"])
        assert dax.startswith("IF ( ISBLANK (") and f'"{NO_DATA}"' in dax, path
        n += 1
    assert n >= 30   # 4 data pages: 5 KPI cards + 4-6 charts each (37 when written)


def test_page4_confusion_title_uses_real_test_size():
    import pandas as pd
    from src import config
    total = int(pd.read_csv(config.PREDICTIONS_DIR / "confusion_matrix.csv", index_col=0).values.sum())
    assert f"test set, {total:,} restaurants" in _title_text(_page_visuals(4)["gen_p4_confusion"]["visual"])


def test_insights_page_matches_generated_findings():
    import pandas as pd
    from src import config
    v = _page_visuals(6)
    f = pd.read_csv(config.ROOT / "outputs" / "insights" / "insights.csv")
    r = pd.read_csv(config.ROOT / "outputs" / "insights" / "recommendations.csv")
    texts = {n: " ".join(run["value"] for para in d["visual"]["objects"]["general"][0]["properties"]["paragraphs"]
                         for run in para["textRuns"]) for n, d in v.items() if n.startswith(("gen_p6_f", "gen_p6_r"))}
    assert len([n for n in texts if n.startswith("gen_p6_f")]) == len(f) and 6 <= len(f) <= 8
    assert len([n for n in texts if n.startswith("gen_p6_r")]) == len(r)
    for i, row in enumerate(f.itertuples(index=False), start=1):
        assert row.finding in texts[f"gen_p6_f{i}"]
    assert not any(n.startswith("gen_slc_") for n in v)   # whole-dataset findings: no slicers on this page


def test_page2_log10_votes_and_india_delivery():
    v = _page_visuals(2)
    y = v["gen_p2_votes_rating"]["visual"]["query"]["queryState"]["Y"]["projections"][0]
    assert y["field"]["Measure"]["Property"] == "Log10 Votes" and y["displayName"] == "log10(votes)"
    d = v["gen_p2_delivery_rating"]["visual"]
    assert d["query"]["queryState"]["Y"]["projections"][0]["field"]["Measure"]["Property"] == "Avg Rating (India)"
    assert "India only" in _title_text(d)
    dax = {n: x for _, n, x, _ in MEASURES}
    assert 'KEEPFILTERS ( restaurants[country] = "India" )' in dax["Avg Rating (India)"]


def test_page3_table_top10_and_bubbles():
    v = _page_visuals(3)
    cols = v["gen_p3_localities"]["visual"]["query"]["queryState"]["Values"]["projections"]
    measures = [c["field"]["Measure"]["Property"] for c in cols if "Measure" in c["field"]]
    # every value column is blank outside the top 10, so the table has exactly 10 rows
    assert measures and all(m.startswith(("Top 10 Locality", "T10 Locality")) for m in measures)
    s = v["gen_p3_price_rating"]["visual"]["objects"]
    ax = s["valueAxis"][0]["properties"]
    assert (_lit(ax["start"]), _lit(ax["end"]), _lit(ax["gridlineShow"])) == ("1.0D", "5.0D", "true")
    assert _lit(s["bubbles"][0]["properties"]["bubbleSize"]) == "30L"


def test_page4_card_font_and_matrix_formatting():
    v = _page_visuals(4)
    assert _lit(v["gen_p4_kpi1"]["visual"]["objects"]["labels"][0]["properties"]["fontSize"]) == "15.0D"
    assert _lit(v["gen_p4_kpi2"]["visual"]["objects"]["labels"][0]["properties"]["fontSize"]) == "20.0D"
    vals = v["gen_p4_confusion"]["visual"]["objects"]["values"]
    cf = [x for x in vals if "backColor" in x["properties"]]
    assert cf[0]["properties"]["backColor"]["solid"]["color"]["expr"]["Measure"]["Property"] == "Confusion Cell Color"
    assert cf[0]["selector"]["metadata"] == "confusion_matrix.Confusion Count"
    dax = {n: x for _, n, x, _ in MEASURES}
    assert '"#F5C6CA"' in dax["Confusion Cell Color"] and '"#FFFFFF"' in dax["Confusion Cell Color"]


def test_every_page_has_five_kpi_cards():
    for n in (1, 2, 3, 4):
        assert sum(d["visual"]["visualType"] == "card" for d in _page_visuals(n).values()) == 5, f"page {n}"


def test_india_page_usd_footnote_and_cost_labels():
    v = _page_visuals(5)
    note = v["gen_p5_usd_note"]["visual"]["objects"]["general"][0]["properties"]["paragraphs"][0]["textRuns"][0]["value"]
    assert note == "US$ values are approximate, converted with World Bank 2017 annual average exchange rates."
    pos = v["gen_p5_usd_note"]["position"]
    assert pos["y"] + pos["height"] <= 720
    headers = [p.get("displayName") for n in ("gen_p5_cities", "gen_p5_localities")
               for p in v[n]["visual"]["query"]["queryState"]["Values"]["projections"]]
    assert "Average cost for two (INR)" in headers and "Average cost for two (US$, approx.)" in headers
    assert not any(h and h.startswith("Avg cost") for h in headers)
