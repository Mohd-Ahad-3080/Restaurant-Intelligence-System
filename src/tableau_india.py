"""Tableau dashboard 'India deep dive' (matches the Power BI India page).

Data: data/processed/tableau_india.csv (written by src/india.py): one row per restaurant-cuisine pair for Indian
restaurants; `is_primary_row` = 1 on exactly one row per restaurant, so restaurant-level measures count each restaurant
once (e.g. Restaurants = SUM([is_primary_row]), average rating = AVG(IF [is_primary_row] = 1 THEN [aggregate_rating] END)).

Filters: two parameters, City and Locality (city), shown as drop-down controls. Every chart sheet keeps only
rows where [In selection] is true; that filter is a context filter, so FIXED shares respect it.

Empty selections: above each chart sits a one-line message sheet that is NOT filtered, so it always has a row.
It shows 'No data for this selection' when the chart's selection is empty (for example a locality that is not
in the chosen city), and nothing otherwise.
"""
from __future__ import annotations

import pandas as pd

from src.india import PRICE_COLOURS, TABLEAU_CSV
from src.tableau_twb import (ACCENT, DS, HIGHLIGHT, TAB_DIR, TEXT2, axis_title, calc_column, csv_datasource, fmt,
                             hide_field_labels, inst, kpi_sheet, q, top_n_filter, worksheet)

HYPER_INDIA = TAB_DIR / "tableau_india.hyper"
INDIA_COLUMNS = [("restaurant_id", "integer"), ("is_primary_row", "integer"), ("city", "string"), ("locality", "string"),
                 ("locality_city", "string"), ("cuisine", "string"), ("price_range", "integer"),
                 ("price_label", "string"), ("has_online_delivery", "integer"), ("has_table_booking", "integer"),
                 ("aggregate_rating", "real"), ("votes", "integer"), ("is_rated", "integer"), ("is_high", "integer"),
                 ("avg_cost_for_two", "real"), ("avg_cost_for_two_usd", "real")]
DASH5 = "India deep dive"
ALL_CITIES, ALL_LOCALITIES = "All cities", "All localities"
P_CITY, P_LOC = "[Parameter 1]", "[Parameter 2]"
NO_DATA = "No data for this selection"
TOP = 10


def _lit(s: str) -> str:
    return '"' + s.replace('"', '""') + '"'


def parameters_datasource() -> tuple[str, dict[str, str]]:
    """Tableau's 'Parameters' datasource with the City and Locality list parameters."""
    d = pd.read_csv(TABLEAU_CSV, encoding="utf-8")
    cities = [ALL_CITIES] + sorted(d["city"].dropna().unique())
    locs = [ALL_LOCALITIES] + sorted(d["locality_city"].dropna().unique())

    def param(name: str, caption: str, values: list[str]) -> tuple[str, str]:
        members = "".join(f"\n          <member value='{q(_lit(v))}' />" for v in values)
        head = (f"<column caption='{q(caption)}' datatype='string' name='{name}' param-domain-type='list' "
                f"role='measure' type='nominal' value='{q(_lit(values[0]))}'>\n"
                f"        <calculation class='tableau' formula='{q(_lit(values[0]))}' />")
        full = head + f"\n        <members>{members}\n        </members>\n      </column>"
        return full, full   # worksheets repeat the full definition (with its members), as Tableau writes it

    city_full, city_dep = param(P_CITY, "City", cities)
    loc_full, loc_dep = param(P_LOC, "Locality (city)", locs)
    block = ("<datasource hasconnection='false' inline='true' name='Parameters' version='18.1'>\n"
             "      <aliases enabled='yes' />\n      " + city_full + "\n      " + loc_full + "\n    </datasource>")
    return block, {P_CITY: city_dep, P_LOC: loc_dep}


def with_parameters(ws_xml: str, param_deps: dict[str, str]) -> str:
    """Add the Parameters datasource to a worksheet that uses [In selection] (which reads both parameters)."""
    # Order matters: Tableau takes the FIRST datasource of a sheet as its primary one. With 'Parameters' first,
    # the India data became a secondary (blended) source with nothing to link on, and every sheet was empty.
    ws_xml = ws_xml.replace("          </datasources>\n",
                            "            <datasource caption='Parameters' name='Parameters' />\n          </datasources>\n",
                            1)
    deps = ("\n          <datasource-dependencies datasource='Parameters'>\n            "
            + "\n            ".join(param_deps.values()) + "\n          </datasource-dependencies>")
    end = ws_xml.index("</datasource-dependencies>") + len("</datasource-dependencies>")   # after the India deps
    return ws_xml[:end] + deps + ws_xml[end:]


def india_datasource() -> tuple[str, DS]:
    sel = (f'([Parameters].{P_CITY} = {_lit(ALL_CITIES)} OR [city] = [Parameters].{P_CITY}) AND '
           f'([Parameters].{P_LOC} = {_lit(ALL_LOCALITIES)} OR [locality_city] = [Parameters].{P_LOC})')
    m = lambda name, cap, f, fmt_=None: calc_column(name, cap, "real", "measure", "quantitative", f, fmt_)
    cols = {
        "restaurant_id": "<column caption='Restaurant Id' datatype='integer' name='[restaurant_id]' role='dimension' "
                         "type='ordinal' />",
        "is_primary_row": "<column caption='Primary row' datatype='integer' name='[is_primary_row]' role='measure' "
                   "type='quantitative' />",
        "city": "<column caption='City' datatype='string' name='[city]' role='dimension' type='nominal' />",
        "locality_city": "<column caption='Locality (city)' datatype='string' name='[locality_city]' "
                         "role='dimension' type='nominal' />",
        "cuisine": "<column caption='Cuisine' datatype='string' name='[cuisine]' role='dimension' type='nominal' />",
        "price_label": "<column caption='Price range' datatype='string' name='[price_label]' role='dimension' "
                       "type='nominal' />",
        "Calculation_in_selection": calc_column("Calculation_in_selection", "In selection", "boolean", "dimension",
                                                "nominal", sel),
        "Calculation_restaurants": calc_column("Calculation_restaurants", "Restaurants", "integer", "measure",
                                               "quantitative", "SUM([is_primary_row])", "n#,##0"),
        "Calculation_avg_rating": m("Calculation_avg_rating", "Average rating (rated)",
                                    "AVG(IF [is_primary_row] = 1 THEN [aggregate_rating] END)", "n#,##0.00"),
        "Calculation_high_pct": m("Calculation_high_pct", "High popularity (rated)",
                                  "AVG(IF [is_primary_row] = 1 AND [is_rated] = 1 THEN [is_high] END)", "p0.0%"),
        "Calculation_delivery_pct": m("Calculation_delivery_pct", "Online delivery",
                                      "AVG(IF [is_primary_row] = 1 THEN [has_online_delivery] END)", "p0.0%"),
        "Calculation_booking_pct": m("Calculation_booking_pct", "Table booking",
                                     "AVG(IF [is_primary_row] = 1 THEN [has_table_booking] END)", "p0.0%"),
        "Calculation_cost_inr": m("Calculation_cost_inr", "Average cost for two (INR)",
                                  "AVG(IF [is_primary_row] = 1 THEN [avg_cost_for_two] END)", "n#,##0"),
        "Calculation_cost_usd": m("Calculation_cost_usd", "Average cost for two (US$, approx.)",
                                  "AVG(IF [is_primary_row] = 1 THEN [avg_cost_for_two_usd] END)", "n#,##0.00"),
        "Calculation_price_share": m("Calculation_price_share", "Share of city's restaurants",
                                     "SUM([is_primary_row]) / MIN({ FIXED [city] : SUM([is_primary_row]) })", "p0%"),
        "Calculation_msg_any": calc_column(
            "Calculation_msg_any", "Message", "string", "measure", "nominal",
            f'IF ZN(SUM(IF [Calculation_in_selection] THEN [is_primary_row] END)) = 0 THEN {_lit(NO_DATA)} ELSE "" END'),
        "Calculation_msg_rated": calc_column(
            "Calculation_msg_rated", "Message (rated)", "string", "measure", "nominal",
            "IF ZN(SUM(IF [Calculation_in_selection] AND [is_rated] = 1 THEN [is_primary_row] END)) = 0 THEN "
            f'{_lit(NO_DATA)} ELSE "" END'),
    }
    for c, t in INDIA_COLUMNS:   # declare every other CSV column (strings = dimensions, numbers = measures)
        if c not in cols:
            role, typ = ("dimension", "nominal") if t == "string" else ("measure", "quantitative")
            cap = c.replace("_", " ").capitalize()
            cols[c] = f"<column caption='{q(cap)}' datatype='{t}' name='[{c}]' role='{role}' type='{typ}' />"
    maps = "".join(f"\n            <map to='{c}'>\n              <bucket>&quot;{q(lab)}&quot;</bucket>\n            </map>"
                   for lab, c in zip(["1 Budget", "2 Moderate", "3 Expensive", "4 Luxury"], PRICE_COLOURS))
    style = ("      <style>\n        <style-rule element='mark'>\n"
             f"          <encoding attr='color' field='[none:price_label:nk]' type='palette'>{maps}\n"
             "          </encoding>\n        </style-rule>\n      </style>\n")
    return csv_datasource("india", "tableau_india", TABLEAU_CSV, INDIA_COLUMNS, cols, HYPER_INDIA, style)


def _sel_filter(ds: DS) -> str:
    """Keep rows in the City/Locality selection (context filter, so FIXED shares respect it)."""
    return (f"\n          <filter class='categorical' column='{ds.ref('none:Calculation_in_selection:nk')}' "
            "context='true'>\n"
            "            <groupfilter function='member' level='[none:Calculation_in_selection:nk]' member='true' "
            "user:ui-domain='database' user:ui-enumeration='inclusive' user:ui-marker='enumerate' />\n"
            "          </filter>")


def india_sheets(ds: DS, pdeps: dict[str, str]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(chart and KPI sheets, message sheets). Each chart has a message sheet named 'Message - <chart>'."""
    sel, sel_x = inst("Calculation_in_selection", "None", "nk")
    city, city_x = inst("city", "None", "nk")
    loc, loc_x = inst("locality_city", "None", "nk")
    cui, cui_x = inst("cuisine", "None", "nk")
    pl, pl_x = inst("price_label", "None", "nk")
    cnt, cnt_x = inst("restaurant_id", "CountD", "qk")
    U = {k: inst(f"Calculation_{k}", "User", "qk") for k in
         ("restaurants", "avg_rating", "high_pct", "delivery_pct", "booking_pct", "cost_inr", "cost_usd",
          "price_share")}
    r = lambda i: ds.ref(i[1:-1])
    flt = _sel_filter(ds)
    top_city = top_n_filter(ds, city, TOP, "SUM([is_primary_row])")
    sheets: list[tuple[str, str]] = []

    kpis = [("KPI - India restaurants", "restaurants", "Restaurants"),
            ("KPI - India average rating", "avg_rating", "Average rating (rated)"),
            ("KPI - India High popularity", "high_pct", "High popularity (rated)"),
            ("KPI - India online delivery", "delivery_pct", "Online delivery"),
            ("KPI - India average cost for two (INR)", "cost_inr", "Average cost for two (INR)")]
    for name, key, label in kpis:
        xml = kpi_sheet(name, ds, f"Calculation_{key}", "User", label, filters=flt,
                        extra_fields=("Calculation_in_selection", "is_primary_row", "city", "locality_city"), extra_instances=(sel_x,))
        sheets.append((name, with_parameters(xml, pdeps)))

    def chart(name, title, rows, cols, fields, insts, filters, enc="", style="", pane="", labels=True):
        """labels=False for charts with several measures side by side: each bar showed every measure's label
        (overlapping); their axes carry the values instead."""
        xml = worksheet(name, ds, ds.deps(["Calculation_in_selection", "is_primary_row", "city", "locality_city", *fields], [sel_x, *insts]), title,
                        rows=rows, cols=cols, mark="Bar", filters=flt + filters, encodings=enc,
                        table_style=style + hide_field_labels(),
                        pane_style=pane + fmt("mark-labels-show", "true" if labels else "false"))
        sheets.append((name, with_parameters(xml, pdeps)))

    sort = lambda dim, by: (f"\n          <sort class='computed' column='{r(dim)}' direction='DESC' using='{r(by)}' />")
    rs, rs_x = U["restaurants"]
    chart("India - Restaurants by city (top 10)", "Restaurants by city (10 largest in the selection)",
          r(city), r(rs), ["city", "Calculation_restaurants"], [city_x, rs_x], top_city + sort(city, rs),
          enc=f"\n              <text column='{r(rs)}' />", style=axis_title(r(rs), "cols", "Restaurants"),
          pane=fmt("mark-color", ACCENT))
    ar, ar_x = U["avg_rating"]
    hp, hp_x = U["high_pct"]
    chart("India - Rating and High popularity by city", "Average rating and High-popularity share (10 largest cities)",
          r(city), f"({r(ar)} + {r(hp)})", ["city", "Calculation_avg_rating", "Calculation_high_pct",
                                            "aggregate_rating", "is_rated", "is_high", "Calculation_restaurants"],
          [city_x, ar_x, hp_x, rs_x], top_city + sort(city, rs),
          labels=False,
          style=axis_title(r(ar), "cols", "Average rating") + axis_title(r(hp), "cols", "High popularity"),
          pane=fmt("mark-color", HIGHLIGHT))
    ps, ps_x = U["price_share"]
    chart("India - Price range mix by city", "Price range mix (share of each city's restaurants, 10 largest cities)",
          r(city), r(ps), ["city", "price_label", "Calculation_price_share", "Calculation_restaurants"],
          [city_x, pl_x, ps_x, rs_x], top_city + sort(city, rs),
          enc=f"\n              <color column='{r(pl)}' />",
          style=axis_title(r(ps), "cols", "Share of restaurants"))
    dp, dp_x = U["delivery_pct"]
    bp, bp_x = U["booking_pct"]
    chart("India - Online delivery and table booking by city", "Online delivery and table booking (10 largest cities)",
          r(city), f"({r(dp)} + {r(bp)})", ["city", "Calculation_delivery_pct", "Calculation_booking_pct",
                                            "has_online_delivery", "has_table_booking", "Calculation_restaurants"],
          [city_x, dp_x, bp_x, rs_x], top_city + sort(city, rs),
          labels=False,
          style=axis_title(r(dp), "cols", "Online delivery") + axis_title(r(bp), "cols", "Table booking"),
          pane=fmt("mark-color", ACCENT))
    chart("India - Top 10 localities (rating and High popularity)",
          "Top 10 localities: restaurants, average rating, High popularity",
          r(loc), f"({r(rs)} + {r(ar)} + {r(hp)})",
          ["locality_city", "Calculation_restaurants", "Calculation_avg_rating", "Calculation_high_pct",
           "aggregate_rating", "is_rated", "is_high"], [loc_x, rs_x, ar_x, hp_x],
          top_n_filter(ds, loc, TOP, "SUM([is_primary_row])") + sort(loc, rs),
          labels=False,
          style=(axis_title(r(rs), "cols", "Restaurants") + axis_title(r(ar), "cols", "Avg rating")
                 + axis_title(r(hp), "cols", "High popularity")),
          pane=fmt("mark-color", HIGHLIGHT))
    chart("India - Cuisine mix (top 10 cuisines)", "Cuisine mix: restaurants offering each cuisine (top 10)",
          r(cui), r(cnt), ["cuisine", "restaurant_id"], [cui_x, cnt_x],
          top_n_filter(ds, cui, TOP, "COUNTD([restaurant_id])") + sort(cui, cnt),
          enc=f"\n              <text column='{r(cnt)}' />", style=axis_title(r(cnt), "cols", "Restaurants"),
          pane=fmt("mark-color", ACCENT))
    ci, ci_x = U["cost_inr"]
    cu, cu_x = U["cost_usd"]
    chart("India - Cost for two by city (INR and US$)", "Average cost for two: INR and approx. US$ (10 largest cities)",
          r(city), f"({r(ci)} + {r(cu)})", ["city", "Calculation_cost_inr", "Calculation_cost_usd",
                                            "avg_cost_for_two", "avg_cost_for_two_usd", "Calculation_restaurants"],
          [city_x, ci_x, cu_x, rs_x], top_city + sort(city, rs),
          labels=False,
          style=axis_title(r(ci), "cols", "Average cost for two (INR)") + axis_title(r(cu), "cols", "Average cost for two (US$, approx.)"),
          pane=fmt("mark-color", TEXT2))

    # one unfiltered message sheet per chart (and one for the KPI row)
    rated_charts = {"India - Rating and High popularity by city", "India - Top 10 localities (rating and High popularity)"}
    msgs = []
    targets = ["KPI row"] + [n for n, _ in sheets if not n.startswith("KPI")]
    for target in targets:
        key = "msg_rated" if target in rated_charts else "msg_any"
        mi, mi_x = inst(f"Calculation_{key}", "User", "nk")
        name = f"Message - {target.replace('India - ', '')}"
        lab = (f"\n            <customized-label>\n              <formatted-text>\n"
               f"                <run bold='true' fontcolor='{ACCENT}' fontsize='10'>&lt;{q(r(mi))}&gt;</run>\n"
               "              </formatted-text>\n            </customized-label>")
        fields = ["Calculation_in_selection", "is_primary_row", "city", "locality_city", f"Calculation_{key}"] + (["is_rated"] if key == "msg_rated"
                                                                                 else [])
        xml = worksheet(name, ds, ds.deps(fields, [mi_x]), "", mark="Text",
                        encodings=f"\n              <text column='{r(mi)}' />", label=lab,
                        pane_style=fmt("mark-labels-show", "true"))
        msgs.append((name, with_parameters(xml, pdeps)))
    return sheets, msgs


INDIA_H = 1400   # taller page (scrolls) so each chart has room: max 2 charts per row


def india_layout(sheets, msgs, ds: DS) -> tuple[list, list, list]:
    """Placements, legends and parameter controls on the 1280 x 1400 page: controls, 5 KPI cards (80 px, as on
    the other dashboards), then 7 charts in rows of two (the last one full width), each under its message line."""
    kpi_x = [16 + i * 252 for i in range(5)]
    place = [(n, (kpi_x[i], 116, 240, 80)) for i, (n, _) in enumerate(sheets[:5])]
    place.append((msgs[0][0], (760, 66, 504, 40)))
    charts = [n for n, _ in sheets[5:]]
    col_x, col_w, row_h, gap, y0 = (16, 648), 616, 286, 10, 208
    slots = [(col_x[i % 2], y0 + (i // 2) * (row_h + gap), col_w, row_h) for i in range(len(charts))]
    if len(charts) % 2:                       # odd number: the last chart takes the full width
        x, y, _, h = slots[-1]
        slots[-1] = (16, y, 1248, h)
    legends = []
    for i, (name, (x, y, w, h)) in enumerate(zip(charts, slots)):
        place.append((msgs[i + 1][0], (x, y, w, 20)))
        cw = w
        if name == "India - Price range mix by city":   # legend beside the chart, tall enough for 4 entries
            legends.append((name, f"[{ds.name}].[none:price_label:nk]", (x + w - 150, y + 20, 150, 120)))
            cw = w - 156
        place.append((name, (x, y + 20, cw, h - 20)))
    controls = [("[Parameters].[Parameter 1]", (16, 64, 300, 44)), ("[Parameters].[Parameter 2]", (328, 64, 420, 44))]
    return place, legends, controls
