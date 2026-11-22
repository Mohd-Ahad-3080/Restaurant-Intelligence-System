"""Generate the Tableau workbook (.twb) for Phase 5 directly as XML, with its data extracts (.hyper).

Format source: dashboards/tableau/starter_extract.twb, written by Tableau Public 2026.3 (workbook version 18.1):
a text connection to data/processed/zomato_clean.csv WITH an extract, and one sheet on a dashboard. Its root
element, format manifest and datasource block (connection + extract + object graph) are reused; the second
datasource, worksheets, dashboard and windows follow the same structure. Tableau Public only accepts extract
data sources, and the extract it made pointed to a Windows temp file, so the extracts are written here with
Tableau's Hyper API from the processed CSVs (always identical to the data) and referenced by a fixed path.

Run:  python -m src.tableau_twb --dashboard 1      (also validates against Tableau's own schema)
Data: zomato_clean.csv (restaurants) and restaurant_cuisines_city.csv (one row per restaurant-cuisine pair,
      written here from the processed files; row level only, all aggregation happens in Tableau).
"""
from __future__ import annotations

import argparse
import hashlib
import re
import uuid
from html import escape
from pathlib import Path

import pandas as pd

from src import config

TAB_DIR = config.ROOT / "dashboards" / "tableau"
STARTER = TAB_DIR / "starter_extract.twb"          # Tableau's own file: extract + dashboard structure
OUT = TAB_DIR / "RestaurantIntelligence.twb"
PROC = config.ROOT / "data" / "processed"
PAIRS_CITY_CSV = PROC / "restaurant_cuisines_city.csv"
HYPER_RESTAURANTS = TAB_DIR / "zomato_clean.hyper"
HYPER_PAIRS = TAB_DIR / "restaurant_cuisines_city.hyper"
PAIRS_COLUMNS = [("restaurant_id", "integer"), ("country", "string"), ("city", "string"), ("cuisine", "string"),
                 ("price_range", "integer"), ("aggregate_rating", "real")]
REMOTE_TYPE = {"integer": 20, "real": 5, "string": 129}          # as in Tableau's extract metadata records
DEFAULT_AGG = {"integer": "Sum", "real": "Sum", "string": "Count"}


def csv_columns(starter: str) -> list[tuple[str, str]]:
    """(name, Tableau type) of zomato_clean.csv, exactly as Tableau typed them in the starter."""
    rel = re.search(r"<columns character-set[^>]*>(.*?)</columns>", starter, re.S).group(1)
    return [(m.group(2), m.group(1)) for m in re.finditer(r"<column datatype='(\w+)' name='([^']+)'", rel)]


def write_hyper(csv: Path, hyper: Path, columns: list[tuple[str, str]]) -> int:
    """Write a Tableau extract (table Extract.Extract, as Tableau names it) from a CSV; returns row count."""
    from tableauhyperapi import (Connection, CreateMode, HyperProcess, Inserter, NULLABLE, SqlType,
                                 TableDefinition, TableName, Telemetry)
    sql = {"integer": SqlType.big_int(), "real": SqlType.double(), "string": SqlType.text()}
    df = pd.read_csv(csv, dtype=str, keep_default_na=False, encoding="utf-8")
    missing = [c for c, _ in columns if c not in df.columns]
    assert not missing, f"{csv.name}: columns missing for the workbook: {missing}"
    df = df[[c for c, _ in columns]]   # the workbook's columns in its order (extra CSV columns are not used)

    def conv(v: str, t: str):
        if v == "":
            return None
        return int(float(v)) if t == "integer" else float(v) if t == "real" else v

    rows = [[conv(v, t) for v, (_, t) in zip(r, columns)] for r in df.itertuples(index=False, name=None)]
    table = TableDefinition(TableName("Extract", "Extract"),
                            [TableDefinition.Column(c, sql[t], NULLABLE) for c, t in columns])
    import tempfile
    # logs go to the temp folder (by default Hyper writes hyperd.log into the working directory)
    with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU,
                      parameters={"log_dir": tempfile.gettempdir()}) as hp:
        with Connection(hp.endpoint, str(hyper), CreateMode.CREATE_AND_REPLACE) as con:
            con.catalog.create_schema("Extract")
            con.catalog.create_table(table)
            with Inserter(con, table) as ins:
                ins.add_rows(rows)
                ins.execute()
            n = con.execute_scalar_query("SELECT COUNT(*) FROM \"Extract\".\"Extract\"")
    assert n == len(df), f"{hyper.name}: {n} rows written, CSV has {len(df)}"
    return n


def extract_xml(hyper: Path, family: str, obj: str, columns: list[tuple[str, str]], csv: Path,
                indent: str = "      ") -> str:
    """<extract> element in the structure Tableau wrote in starter_extract.twb (incl. update-time, approx-count)."""
    import datetime as dt
    df = pd.read_csv(csv, dtype=str, keep_default_na=False, encoding="utf-8")
    approx = {c: int(df.loc[df[c] != "", c].nunique()) for c, _ in columns}
    updated = dt.datetime.fromtimestamp(csv.stat().st_mtime).strftime("%m/%d/%Y %I:%M:%S %p")
    recs = ""
    for i, (c, t) in enumerate(columns):
        coll = "\n            <collation flag='0' name='LEN_RUS' />" if t == "string" else ""
        recs += (f"\n          <metadata-record class='column'>\n            <remote-name>{c}</remote-name>\n"
                 f"            <remote-type>{REMOTE_TYPE[t]}</remote-type>\n            <local-name>[{c}]</local-name>\n"
                 f"            <parent-name>[Extract]</parent-name>\n            <remote-alias>{c}</remote-alias>\n"
                 f"            <ordinal>{i}</ordinal>\n            <family>{q(family)}</family>\n"
                 f"            <local-type>{t}</local-type>\n            <aggregation>{DEFAULT_AGG[t]}</aggregation>\n"
                 f"            <approx-count>{approx[c]}</approx-count>\n"
                 f"            <contains-null>true</contains-null>{coll}\n"
                 f"            <object-id>[{obj}]</object-id>\n          </metadata-record>")
    return (f"<extract count='-1' enabled='true' object-id='' units='records' user-specific='false'>\n"
            f"{indent}  <connection access_mode='readonly' author-locale='en_US' class='hyper' "
            f"dbname='{q(hyper.as_posix())}' default-settings='hyper' schema='Extract' sslmode='' "
            f"tablename='Extract' update-time='{updated}' username='tableau_internal_user'>\n"
            f"{indent}    <relation name='Extract' table='[Extract].[Extract]' type='table' />\n"
            f"{indent}    <metadata-records>{recs}\n{indent}    </metadata-records>\n"
            f"{indent}  </connection>\n{indent}</extract>")

# Theme B: the approved project colour theme (slate + brand red)
SLATE, WHITE, ACCENT, HIGHLIGHT, ACTIVE = "#1f2329", "#ffffff", "#cb202d", "#8e1520", "#e23744"
LIGHT1, LIGHT2, PAGE_BG, BORDER, TEXT, TEXT2 = "#e8838b", "#f5c6ca", "#f4f4f5", "#e4e4e7", "#18181b", "#5c5c66"
GREY = "#a1a1aa"
W, H = 1280, 720
CUR_H = H   # height of the dashboard being written (zones use it for their 1/100,000 units)

BIG_CITY_MIN = 50       # cuisine mix: cities with at least this many restaurants
RATED_CITY_MIN = 20     # city rating chart: cities with at least this many rated restaurants
TOP_CITIES = 15
TOP_CUISINES = 5


def q(s: str) -> str:
    """XML attribute/text escaping (quotes too, as Tableau writes them)."""
    return escape(s, quote=True).replace("&#x27;", "&apos;")


def _uuid(*parts: str) -> str:
    return "{" + str(uuid.uuid5(uuid.NAMESPACE_URL, "ri-tableau/" + "/".join(parts))).upper() + "}"


def _token(*parts: str, n: int = 28) -> str:
    return hashlib.sha1("/".join(parts).encode()).hexdigest()[:n]


# ------------------------------------------------------------------ data for Tableau
def write_pairs_with_city() -> pd.DataFrame:
    """One row per restaurant-cuisine pair, with the restaurant's country, city, price range and rating
    (row level, nothing aggregated; unrated restaurants keep an empty rating)."""
    d = pd.read_csv(PROC / "zomato_clean.csv", encoding="utf-8")
    p = pd.read_csv(PROC / "restaurant_cuisines.csv", encoding="utf-8")
    out = p.merge(d[["restaurant_id", "country", "city", "price_range", "aggregate_rating"]], on="restaurant_id",
                  how="inner", validate="many_to_one")[[c for c, _ in PAIRS_COLUMNS]]
    assert len(out) == len(p), "every cuisine pair must match a restaurant"
    out.to_csv(PAIRS_CITY_CSV, index=False, encoding="utf-8")
    return out


def big_city_top_cuisines(pairs: pd.DataFrame) -> list[str]:
    d = pd.read_csv(PROC / "zomato_clean.csv", encoding="utf-8")
    sizes = d["city"].value_counts()
    big = sizes[sizes >= BIG_CITY_MIN].index
    return pairs[pairs["city"].isin(big)]["cuisine"].value_counts().head(TOP_CUISINES).index.tolist()


# ------------------------------------------------------------------ datasources
class DS:
    """A datasource: its internal name and the column definitions worksheets must repeat."""

    def __init__(self, name: str, caption: str, columns: dict[str, str]):
        self.name, self.caption, self.columns = name, caption, columns   # columns: field -> <column .../> xml

    def ref(self, instance: str) -> str:
        return f"[{self.name}].[{instance}]"

    def deps(self, fields: list[str], instances: list[str]) -> str:
        cols = "".join(f"\n            {self.columns[f]}" for f in sorted(set(fields)))
        inst = "".join(f"\n            {i}" for i in instances)
        return (f"<datasource-dependencies datasource='{self.name}'>{cols}{inst}\n"
                "          </datasource-dependencies>")


def inst(field: str, derivation: str, kind: str, prefix: str | None = None) -> tuple[str, str]:
    """Column instance (name, xml). kind: nk / ok / qk."""
    prefix = prefix or {"None": "none", "Avg": "avg", "Sum": "sum", "CountD": "ctd", "Count": "cnt",
                        "User": "usr", "Min": "min"}[derivation]
    name = f"[{prefix}:{field}:{kind}]"
    t = {"nk": "nominal", "ok": "ordinal", "qk": "quantitative"}[kind]
    return name, (f"<column-instance column='[{field}]' derivation='{derivation}' name='{name}' pivot='key' "
                  f"type='{t}' />")


def calc_column(name: str, caption: str, datatype: str, role: str, typ: str, formula: str,
                default_format: str | None = None) -> str:
    fmt = f" default-format='{q(default_format)}'" if default_format else ""
    return (f"<column caption='{q(caption)}' datatype='{datatype}'{fmt} name='[{name}]' role='{role}' "
            f"type='{typ}'>\n              <calculation class='tableau' formula='{q(formula)}' />\n"
            "            </column>")


def restaurants_datasource(starter: str) -> tuple[str, DS]:
    """Reuse Tableau's own datasource block for zomato_clean.csv; patch formats, roles and calculations."""
    block = re.search(r"<datasources>\s*(<datasource .*?</datasource>)\s*</datasources>", starter, re.S).group(1)
    # Tableau's extract pointed to a Windows temp file: replace it with ours (same structure, fixed path)
    obj = re.search(r"<object caption='zomato_clean.csv' id='([^']+)'>", block).group(1)
    ext = extract_xml(HYPER_RESTAURANTS, "zomato_clean.csv", obj, csv_columns(starter), PROC / "zomato_clean.csv")
    block = re.sub(r"<extract .*?</extract>", lambda _: ext, block, count=1, flags=re.S)
    block = block.replace("directory='D:/restaurant-intelligence/data/processed'",
                          f"directory='{q(PROC.as_posix())}'")
    # Country holds names, not 2-letter ISO codes (Tableau guessed ISO3166_2)
    block = block.replace("semantic-role='[Country].[ISO3166_2]'", "semantic-role='[Country].[Name]'")
    formats = {"aggregate_rating": "n#,##0.00;-#,##0.00", "votes": "n#,##0;-#,##0",
               "has_online_delivery": "p0.0%"}
    for field, fmt in formats.items():
        block = re.sub(rf"(<column caption='[^']*' datatype='[^']*')( name='\[{field}\]')",
                       rf"\1 default-format='{q(fmt)}'\2", block, count=1)
    calcs = {
        "Calculation_city_rated20": calc_column(
            "Calculation_city_rated20", f"City has {RATED_CITY_MIN}+ rated restaurants", "boolean", "dimension",
            "nominal", f"{{ FIXED [city] : SUM([is_rated]) }} >= {RATED_CITY_MIN}"),
    }
    block = block.replace("      <drill-paths>", "".join(f"      {c}\n" for c in calcs.values()) + "      <drill-paths>",
                          1)
    name = re.search(r"<datasource caption='[^']*' inline='true' name='([^']+)'", block).group(1)
    # the datasource-level <column .../> definitions (6-space indent), which worksheets repeat as dependencies
    columns = {m.group(2): m.group(1) for m in re.finditer(r"^      (<column [^>]*name='\[([^\]]+)\]'[^>]*/>)$",
                                                          block, re.M) if "datatype='table'" not in m.group(1)}
    columns.update(calcs)
    return block, DS(name, "zomato_clean", columns)


def csv_datasource(key: str, caption: str, csv: Path, csv_cols: list[tuple[str, str]], columns: dict[str, str],
                   hyper: Path, style: str = "") -> tuple[str, DS]:
    """Datasource for a processed CSV with its .hyper extract, in the structure Tableau wrote for zomato_clean."""
    name = "federated." + _token("ds", key)
    conn = "textscan." + _token("conn", key)
    obj = csv.name + "_" + _token("obj", key, n=32).upper()
    cols = [(c, t, REMOTE_TYPE[t], DEFAULT_AGG[t]) for c, t in csv_cols]
    colnames = "".join(f"\n            <column datatype='{t}' name='{c}' ordinal='{i}' />"
                       for i, (c, t, _, _) in enumerate(cols))
    relation = (f"<relation connection='{conn}' name='{csv.name}' table='[{csv.stem}#csv]' type='table'>\n"
                f"          <columns character-set='UTF-8' header='yes' locale='en_US' separator=','>{colnames}\n"
                "          </columns>\n        </relation>")
    recs = ""
    for i, (c, t, rt, agg) in enumerate(cols):
        extra = ("\n            <scale>1</scale>\n            <width>1073741823</width>" if t == "string" else "")
        coll = "\n            <collation flag='0' name='LEN_RUS' />" if t == "string" else ""
        recs += (f"\n          <metadata-record class='column'>\n            <remote-name>{c}</remote-name>\n"
                 f"            <remote-type>{rt}</remote-type>\n            <local-name>[{c}]</local-name>\n"
                 f"            <parent-name>[{csv.name}]</parent-name>\n"
                 f"            <remote-alias>{c}</remote-alias>\n            <ordinal>{i}</ordinal>\n"
                 f"            <local-type>{t}</local-type>\n            <aggregation>{agg}</aggregation>{extra}\n"
                 f"            <contains-null>true</contains-null>{coll}\n"
                 f"            <object-id>[{obj}]</object-id>\n          </metadata-record>")
    block = (f"<datasource caption='{q(caption)}' inline='true' name='{name}' version='18.1'>\n"
             "      <connection class='federated'>\n        <named-connections>\n"
             f"          <named-connection caption='{q(caption)}' name='{conn}'>\n"
             f"            <connection class='textscan' directory='{q(csv.parent.as_posix())}' "
             f"filename='{q(csv.name)}' password='' server='' />\n"
             "          </named-connection>\n        </named-connections>\n"
             f"        {relation}\n        <metadata-records>{recs}\n        </metadata-records>\n"
             "      </connection>\n      <aliases enabled='yes' />\n"
             f"      <column caption='{q(csv.name)}' datatype='table' "
             f"name='[__tableau_internal_object_id__].[{obj}]' role='measure' type='quantitative' />\n"
             + "".join(f"      {c}\n" for c in columns.values()) +
             f"      {extract_xml(hyper, csv.name, obj, csv_cols, csv)}\n"
             "      <layout dim-ordering='alphabetic' measure-ordering='alphabetic' show-structure='true' />\n"
             + style +
             "      <object-graph>\n        <objects>\n"
             f"          <object caption='{q(csv.name)}' id='{obj}'>\n"
             f"            <properties context=''>\n              {relation}\n            </properties>\n"
             "            <properties context='extract'>\n"
             "              <relation name='Extract' table='[Extract].[Extract]' type='table' />\n"
             "            </properties>\n"
             "          </object>\n        </objects>\n      </object-graph>\n    </datasource>")
    return block, DS(name, caption, columns)


def pairs_datasource(top_cuisines: list[str]) -> tuple[str, DS]:
    """Datasource for restaurant_cuisines_city.csv (row level, one row per restaurant-cuisine pair)."""
    in_list = ", ".join('"' + c.replace('"', '""') + '"' for c in top_cuisines)
    dark_list = ", ".join('"' + c.replace('"', '""') + '"' for c in top_cuisines[:N_DARK])
    columns = {
        "city": "<column caption='City' datatype='string' name='[city]' role='dimension' "
                "semantic-role='[City].[Name]' type='nominal' />",
        "country": "<column caption='Country' datatype='string' name='[country]' role='dimension' "
                   "semantic-role='[Country].[Name]' type='nominal' />",
        "cuisine": "<column caption='Cuisine' datatype='string' name='[cuisine]' role='dimension' type='nominal' />",
        "restaurant_id": "<column caption='Restaurant Id' datatype='integer' name='[restaurant_id]' "
                         "role='dimension' type='ordinal' />",
        "price_range": "<column caption='Price Range' datatype='integer' default-format='n#,##0.00;-#,##0.00' "
                       "name='[price_range]' role='measure' type='quantitative' />",
        "aggregate_rating": "<column caption='Aggregate Rating' datatype='real' default-format='n#,##0.00;-#,##0.00' "
                            "name='[aggregate_rating]' role='measure' type='quantitative' />",
        "Calculation_city_group": calc_column(
            "Calculation_city_group", "City group", "string", "dimension", "nominal",
            f'IF {{ FIXED [city] : COUNTD([restaurant_id]) }} >= {BIG_CITY_MIN} THEN [city] ELSE "Other cities" END'),
        "Calculation_cuisine_group": calc_column(
            "Calculation_cuisine_group", "Cuisine group", "string", "dimension", "nominal",
            f'IF [cuisine] IN ({in_list}) THEN [cuisine] ELSE "Other" END'),
        "Calculation_big_city": calc_column(
            "Calculation_big_city", f"City has {BIG_CITY_MIN}+ restaurants", "boolean", "dimension", "nominal",
            f"{{ FIXED [city] : COUNTD([restaurant_id]) }} >= {BIG_CITY_MIN}"),
        "Calculation_listing_share": calc_column(
            "Calculation_listing_share", "Share of cuisine listings", "real", "measure", "quantitative",
            "COUNT([restaurant_id]) / MIN({ FIXED [city] : COUNT([restaurant_id]) })", "p0%"),
        # Labels: white text on the 3 dark reds, dark text on the light shades and grey (two label fields,
        # each blank where the other one applies)
        "Calculation_label_dark": calc_column(
            "Calculation_label_dark", "Label (dark bars)", "real", "measure", "quantitative",
            f"IF MIN([Calculation_cuisine_group]) IN ({dark_list}) THEN [Calculation_listing_share] END", "p0%"),
        "Calculation_label_light": calc_column(
            "Calculation_label_light", "Label (light bars)", "real", "measure", "quantitative",
            f"IF MIN([Calculation_cuisine_group]) IN ({dark_list}) THEN NULL ELSE [Calculation_listing_share] END",
            "p0%"),
    }
    # Theme B colours per cuisine group. Tableau keeps colour assignments in the datasource's <style>.
    maps = "".join(f"\n            <map to='{c}'>\n              <bucket>&quot;{q(n)}&quot;</bucket>\n            </map>"
                   for n, c in zip(top_cuisines + ["Other"], CUISINE_COLOURS + [GREY]))
    palette = ("      <style>\n        <style-rule element='mark'>\n"
               f"          <encoding attr='color' field='[none:Calculation_cuisine_group:nk]' type='palette'>{maps}\n"
               "          </encoding>\n        </style-rule>\n      </style>\n")
    return csv_datasource("pairs", "restaurant_cuisines_city", PAIRS_CITY_CSV, PAIRS_COLUMNS, columns, HYPER_PAIRS,
                          palette)


# ------------------------------------------------------------------ worksheets
def title_xml(text: str, size: int = 11, colour: str = TEXT) -> str:
    return (f"<layout-options>\n        <title>\n          <formatted-text>\n"
            f"            <run fontcolor='{colour}' fontsize='{size}'>{q(text)}</run>\n"
            "          </formatted-text>\n        </title>\n      </layout-options>")


def worksheet(name: str, ds: DS, deps: str, title: str, *, rows: str = "", cols: str = "", mark: str = "Automatic",
              encodings: str = "", filters: str = "", sort: str = "", pane_style: str = "", table_style: str = "",
              label: str = "", title_size: int = 11, title_colour: str = TEXT) -> str:
    return f"""    <worksheet name='{q(name)}'>
      {title_xml(title, title_size, title_colour)}
      <table>
        <view>
          <datasources>
            <datasource caption='{q(ds.caption)}' name='{ds.name}' />
          </datasources>
          <mapsources>
            <mapsource name='Tableau' />
          </mapsources>
          {deps}{filters}{sort}
          <aggregation value='true' />
        </view>
        <style>{table_style}
        </style>
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view>
              <breakdown value='auto' />
            </view>
            <mark class='{mark}' />
            <encodings>{encodings}
            </encodings>{label}
            <style>
              <style-rule element='mark'>{pane_style}
              </style-rule>
            </style>
          </pane>
        </panes>
        <rows>{rows}</rows>
        <cols>{cols}</cols>
      </table>
      <simple-id uuid='{_uuid("ws", name)}' />
    </worksheet>
"""


def fmt(attr: str, value: str) -> str:
    return f"\n                <format attr='{attr}' value='{q(value)}' />"


def kpi_sheet(name: str, ds: DS, field: str, derivation: str, label: str, filters: str = "",
              extra_fields: tuple[str, ...] = (), extra_instances: tuple[str, ...] = ()) -> str:
    iname, ixml = inst(field, derivation, "qk")
    ref = ds.ref(iname[1:-1])
    lab = (f"\n            <customized-label>\n              <formatted-text>\n"
           f"                <run fontcolor='{TEXT}' fontsize='20'>&lt;{q(ref)}&gt;</run>\n"
           "              </formatted-text>\n            </customized-label>")
    # small grey label (sheet title) on top, large number below, both left-aligned (as in Power BI)
    left = ("\n          <style-rule element='cell'>\n            <format attr='text-align' value='left' />\n"
            "          </style-rule>")
    return worksheet(name, ds, ds.deps([field, *extra_fields], [ixml, *extra_instances]), label, mark="Text",
                     filters=filters,
                     encodings=f"\n              <text column='{ref}' />", label=lab, table_style=left,
                     pane_style=fmt("mark-labels-show", "true") + fmt("text-align", "left"),
                     title_size=10, title_colour=TEXT2)


def dashboard1_sheets(rds: DS, pds: DS) -> list[tuple[str, str]]:
    sheets = [
        ("KPI - Restaurants", kpi_sheet("KPI - Restaurants", rds, "restaurant_id", "CountD", "Restaurants")),
        ("KPI - Cities", kpi_sheet("KPI - Cities", rds, "city", "CountD", "Cities")),
        ("KPI - Average rating", kpi_sheet("KPI - Average rating", rds, "aggregate_rating", "Avg", "Avg rating")),
        ("KPI - Total votes", kpi_sheet("KPI - Total votes", rds, "votes", "Sum", "Total votes")),
        ("KPI - Online delivery", kpi_sheet("KPI - Online delivery", rds, "has_online_delivery", "Avg",
                                          "Online delivery")),
    ]
    # --- city bubble map (valid coordinates only; bubble size = restaurants)
    lat, lat_x = inst("latitude", "Avg", "qk")
    lon, lon_x = inst("longitude", "Avg", "qk")
    city, city_x = inst("city", "None", "nk")
    cnt, cnt_x = inst("restaurant_id", "CountD", "qk")
    valid, valid_x = inst("has_valid_coords", "None", "qk")
    avgr, avgr_x = inst("aggregate_rating", "Avg", "qk")
    flt = (f"\n          <filter class='quantitative' column='{rds.ref(valid[1:-1])}' included-values='in-range'>\n"
           "            <min>1</min>\n            <max>1</max>\n          </filter>")
    sheets.append(("Restaurants by city (map)", worksheet(
        "Restaurants by city (map)", rds,
        rds.deps(["latitude", "longitude", "city", "restaurant_id", "has_valid_coords", "aggregate_rating"],
                 [lat_x, lon_x, city_x, cnt_x, valid_x, avgr_x]),
        "Restaurants by city (bubble size = number of restaurants; valid coordinates only)",
        rows=rds.ref(lat[1:-1]), cols=rds.ref(lon[1:-1]), mark="Circle", filters=flt,
        encodings=(f"\n              <lod column='{rds.ref(city[1:-1])}' />"
                   f"\n              <size column='{rds.ref(cnt[1:-1])}' />"
                   f"\n              <tooltip column='{rds.ref(avgr[1:-1])}' />"),
        # Size range "by range": the smallest city gets MAP_MIN_SIZE of the largest bubble instead of a dot
        table_style=(f"\n          <style-rule element='mark'>\n            <encoding attr='size' "
                     f"field='{rds.ref(cnt[1:-1])}' max-size='{MAP_MAX_SIZE}' min-size='{MAP_MIN_SIZE}' "
                     "type='rangesize' />\n          </style-rule>"),
        pane_style=fmt("mark-color", ACCENT) + fmt("mark-transparency", "200"))))
    # --- city average rating: top 15 among cities with 20+ rated restaurants
    big, big_x = inst("Calculation_city_rated20", "None", "nk")
    flt = (f"\n          <filter class='categorical' column='{rds.ref(big[1:-1])}' context='true'>\n"
           f"            <groupfilter function='member' level='{big}' member='true' user:ui-domain='database' "
           "user:ui-enumeration='inclusive' user:ui-marker='enumerate' />\n          </filter>"
           f"\n          <filter class='categorical' column='{rds.ref(city[1:-1])}'>\n"
           f"            <groupfilter count='{TOP_CITIES}' end='top' function='end' units='records' "
           "user:ui-marker='end' user:ui-top-by-field='true'>\n"
           f"              <groupfilter direction='DESC' expression='AVG([aggregate_rating])' function='order' "
           "user:ui-marker='order'>\n"
           f"                <groupfilter function='level-members' level='{city}' user:ui-enumeration='all' "
           "user:ui-marker='enumerate' />\n              </groupfilter>\n            </groupfilter>\n"
           "          </filter>")
    srt = (f"\n          <sort class='computed' column='{rds.ref(city[1:-1])}' direction='DESC' "
           f"using='{rds.ref(avgr[1:-1])}' />")
    sheets.append(("Average rating by city (top 15)", worksheet(
        "Average rating by city (top 15)", rds,
        rds.deps(["city", "aggregate_rating", "Calculation_city_rated20"], [city_x, avgr_x, big_x]),
        f"Average rating: top {TOP_CITIES} cities (cities with {RATED_CITY_MIN}+ rated restaurants)",
        rows=rds.ref(city[1:-1]), cols=rds.ref(avgr[1:-1]), mark="Bar", filters=flt, sort=srt,
        encodings=f"\n              <text column='{rds.ref(avgr[1:-1])}' />",
        table_style=axis_title(rds.ref(avgr[1:-1]), "cols", "Average rating") + hide_field_labels(),
        pane_style=fmt("mark-color", ACCENT) + fmt("mark-labels-show", "true"))))
    # --- cuisine mix in the cities with 50+ restaurants (stacked share of cuisine listings)
    pcity, pcity_x = inst("city", "None", "nk")
    grp, grp_x = inst("Calculation_cuisine_group", "None", "nk")
    pbig, pbig_x = inst("Calculation_big_city", "None", "nk")
    share, share_x = inst("Calculation_listing_share", "User", "qk")
    pcnt, pcnt_x = inst("restaurant_id", "CountD", "qk")
    flt = (f"\n          <filter class='categorical' column='{pds.ref(pbig[1:-1])}'>\n"
           f"            <groupfilter function='member' level='{pbig}' member='true' user:ui-domain='database' "
           "user:ui-enumeration='inclusive' user:ui-marker='enumerate' />\n          </filter>")
    srt = (f"\n          <sort class='computed' column='{pds.ref(pcity[1:-1])}' direction='DESC' "
           f"using='{pds.ref(pcnt[1:-1])}' />")
    return sheets,(pds, pcity, pcity_x, grp, grp_x, pbig_x, share, share_x, pcnt_x, flt, srt)


def cuisine_sheet(parts, top_cuisines: list[str]) -> tuple[str, str]:
    """Stacked columns: one per city, share of cuisine listings by cuisine group (colours from the datasource)."""
    pds, pcity, pcity_x, grp, grp_x, pbig_x, share, share_x, pcnt_x, flt, srt = parts
    dark, dark_x = inst("Calculation_label_dark", "User", "qk")
    light, light_x = inst("Calculation_label_light", "User", "qk")
    lab = (f"\n            <customized-label>\n              <formatted-text>\n"
           f"                <run fontcolor='{WHITE}' fontsize='9'>&lt;{q(pds.ref(dark[1:-1]))}&gt;</run>\n"
           f"                <run fontcolor='{TEXT}' fontsize='9'>&lt;{q(pds.ref(light[1:-1]))}&gt;</run>\n"
           "              </formatted-text>\n            </customized-label>")
    name = "Cuisine mix by city (share of listings)"
    return name, worksheet(
        name, pds,
        pds.deps(["city", "Calculation_cuisine_group", "Calculation_big_city", "Calculation_listing_share",
                  "Calculation_label_dark", "Calculation_label_light", "restaurant_id"],
                 [pcity_x, grp_x, pbig_x, share_x, pcnt_x, dark_x, light_x]),
        f"Cuisine mix in the {BIG_CITY_MIN}+ restaurant cities",
        rows=pds.ref(share[1:-1]), cols=pds.ref(pcity[1:-1]), mark="Bar", filters=flt, sort=srt, label=lab,
        table_style=axis_title(pds.ref(share[1:-1]), "rows", "Share of cuisine listings") + hide_field_labels(),
        encodings=(f"\n              <color column='{pds.ref(grp[1:-1])}' />"
                   f"\n              <text column='{pds.ref(dark[1:-1])}' />"
                   f"\n              <text column='{pds.ref(light[1:-1])}' />"),
        pane_style=fmt("mark-labels-show", "true"))


CUISINE_COLOURS = [HIGHLIGHT, ACCENT, ACTIVE, LIGHT1, LIGHT2]   # top 5 cuisines, then grey for "Other"
N_DARK = 3   # the first 3 colours are dark (white labels); the light shades and grey get dark labels
MAP_MIN_SIZE, MAP_MAX_SIZE = 0.25, 1.0   # bubble size range (fractions of the largest mark size)


def axis_title(field_ref: str, scope: str, text: str, fixed_max: int | None = None) -> str:
    """Axis title; with fixed_max: fixed range 0..fixed_max, a tick every 1 and whole-number tick labels
    (automatic ticks '0.00 0.50 1.00 ...' overlapped on the narrow cuisine charts). Bar labels keep 2 decimals."""
    extra = ""
    if fixed_max is not None:   # same <encoding attr='space'> structure as in Tableau's own starter file
        extra = (f"\n            <encoding attr='space' class='0' field='{field_ref}' field-type='quantitative' "
                 f"major-origin='0' major-spacing='1' max='{fixed_max}' min='0' range-type='fixed' "
                 f"scope='{scope}' type='space' />"
                 f"\n            <format attr='text-format' field='{field_ref}' scope='{scope}' "
                 "value='n#,##0;-#,##0' />")
    return (f"\n          <style-rule element='axis'>\n            <format attr='title' field='{field_ref}' "
            f"scope='{scope}' value='{q(text)}' />{extra}\n          </style-rule>")


def hide_field_labels() -> str:
    """Hides the 'City' field-label header above/next to the axis (rows and columns)."""
    return ("\n          <style-rule element='worksheet'>\n"
            "            <format attr='display-field-labels' scope='rows' value='false' />\n"
            "            <format attr='display-field-labels' scope='cols' value='false' />\n"
            "          </style-rule>")


# ------------------------------------------------------------------ Dashboard 2: cuisine and pricing
def top_n_filter(ds: DS, level: str, n: int, expression: str) -> str:
    """Top-N filter on a dimension (same XML as the working top-15 city filter in Dashboard 1)."""
    return (f"\n          <filter class='categorical' column='{ds.ref(level[1:-1])}'>\n"
            f"            <groupfilter count='{n}' end='top' function='end' units='records' "
            "user:ui-marker='end' user:ui-top-by-field='true'>\n"
            f"              <groupfilter direction='DESC' expression='{q(expression)}' function='order' "
            "user:ui-marker='order'>\n"
            f"                <groupfilter function='level-members' level='{level}' user:ui-enumeration='all' "
            "user:ui-marker='enumerate' />\n              </groupfilter>\n            </groupfilter>\n"
            "          </filter>")


def dashboard2_sheets(rds: DS, pds: DS) -> list[tuple[str, str]]:
    """KPI cards (cuisines + 4 price ranges) and four bar charts on the 15 most common cuisines.

    Price is compared with price range (1-4), not cost for two, because costs are in local currencies.
    Bars use one Theme B colour each; the city stack uses Tableau's default palette (no custom mapping).
    """
    sheets = [("KPI - Individual cuisines", kpi_sheet("KPI - Individual cuisines", pds, "cuisine", "CountD", "Individual cuisines"))]
    pr, pr_x = inst("price_range", "None", "qk")
    for n, label in PRICE_LABELS.items():
        flt = (f"\n          <filter class='quantitative' column='{rds.ref(pr[1:-1])}' included-values='in-range'>\n"
               f"            <min>{n}</min>\n            <max>{n}</max>\n          </filter>")
        name = f"KPI - Price range {n} ({label})"
        sheets.append((name, kpi_sheet(name, rds, "restaurant_id", "CountD",
                                       f"{label} ({n})", filters=flt,   # one line: longer labels wrapped
                                       # and pushed the number out of the card
                                       extra_fields=("price_range",), extra_instances=(pr_x,))))
    cui, cui_x = inst("cuisine", "None", "nk")
    cnt, cnt_x = inst("restaurant_id", "CountD", "qk")
    top = top_n_filter(pds, cui, TOP_CUISINES_D2, "COUNTD([restaurant_id])")
    charts = [  # (sheet, title, measure field, derivation, axis title, colour, fixed axis max or None)
        ("Restaurants by cuisine (top 15)", f"Top {TOP_CUISINES_D2} cuisines: restaurants offering each",
         "restaurant_id", "CountD", "Restaurants", ACCENT, None),
        ("Average rating by cuisine", "Average rating by cuisine (rated restaurants)",
         "aggregate_rating", "Avg", "Average rating", ACCENT, 5),
        ("Average price range by cuisine", "Average price range by cuisine (1 = Budget, 4 = Luxury)",
         "price_range", "Avg", "Average price range (1-4)", HIGHLIGHT, 4),
    ]
    for name, title, field, deriv, axis, colour, axis_max in charts:
        m, m_x = inst(field, deriv, "qk")
        srt = (f"\n          <sort class='computed' column='{pds.ref(cui[1:-1])}' direction='DESC' "
               f"using='{pds.ref(m[1:-1])}' />")
        fields = ["cuisine", "restaurant_id"] + ([field] if field != "restaurant_id" else [])
        insts = [cui_x, cnt_x] + ([m_x] if m != cnt else [])
        sheets.append((name, worksheet(
            name, pds, pds.deps(fields, insts), title,
            rows=pds.ref(cui[1:-1]), cols=pds.ref(m[1:-1]), mark="Bar", filters=top, sort=srt,
            encodings=f"\n              <text column='{pds.ref(m[1:-1])}' />",
            table_style=axis_title(pds.ref(m[1:-1]), "cols", axis, axis_max) + hide_field_labels(),
            pane_style=fmt("mark-color", colour) + fmt("mark-labels-show", "true"))))
    # city-stacked cuisines: 4 big cities + "Other cities" (default palette, legend on the dashboard)
    grp, grp_x = inst("Calculation_city_group", "None", "nk")
    srt = (f"\n          <sort class='computed' column='{pds.ref(cui[1:-1])}' direction='DESC' "
           f"using='{pds.ref(cnt[1:-1])}' />")
    name = "Cuisines by city group"
    sheets.append((name, worksheet(
        name, pds, pds.deps(["cuisine", "restaurant_id", "Calculation_city_group"], [cui_x, cnt_x, grp_x]),
        f"Top {TOP_CUISINES_D2} cuisines by city group (restaurants offering each)",
        rows=pds.ref(cui[1:-1]), cols=pds.ref(cnt[1:-1]), mark="Bar", filters=top, sort=srt,
        encodings=f"\n              <color column='{pds.ref(grp[1:-1])}' />",
        table_style=axis_title(pds.ref(cnt[1:-1]), "cols", "Restaurants") + hide_field_labels())))
    return sheets


# ------------------------------------------------------------------ dashboard
def _u(px: float, total: int) -> int:
    return round(px / total * 100000)


def zone_style(bg: str, border: bool = True, padding: int = 6) -> str:
    s = "\n          <zone-style>" + fmt("background-color", bg).replace("                ", "            ")
    if border:
        s += (fmt("border-color", BORDER) + fmt("border-style", "solid") + fmt("border-width", "1")) \
            .replace("                ", "            ")
    else:
        s += fmt("border-style", "none").replace("                ", "            ")
    s += (fmt("margin", "0") + fmt("padding", str(padding))).replace("                ", "            ")
    return s + "\n          </zone-style>"


def zone(zid: int, x, y, w, h, *, name: str | None = None, ztype: str | None = None, inner: str = "",
         bg: str = WHITE, border: bool = True, padding: int = 6, param: str | None = None,
         mode: str | None = None) -> str:
    attrs = f"floating='true' h='{_u(h, CUR_H)}' id='{zid}'"
    attrs += f" mode='{mode}'" if mode else ""
    attrs += f" name='{q(name)}'" if name else ""
    attrs += f" param='{q(param)}'" if param else ""
    attrs += f" type-v2='{ztype}'" if ztype else ""
    attrs += f" w='{_u(w, W)}' x='{_u(x, W)}' y='{_u(y, CUR_H)}'"
    return f"\n        <zone {attrs}>{inner}{zone_style(bg, border, padding)}\n        </zone>"


def text_run(text: str, size: int, bold: bool = False, colour: str = WHITE) -> str:
    b = " bold='true'" if bold else ""
    return ("\n          <formatted-text>\n"
            f"            <run{b} fontcolor='{colour}' fontsize='{size}'>{q(text)}</run>\n"
            "          </formatted-text>")


def text_lines(lines: list[str], size: int = 9, colour: str = TEXT, bold_first: bool = False) -> str:
    """Several paragraphs in one text zone (Tableau writes a line break as a run holding 'Æ&#10;')."""
    runs = "".join(f"\n            <run{' bold=' + chr(39) + 'true' + chr(39) if bold_first and i == 0 else ''} "
                   f"fontcolor='{colour}' fontsize='{size + 1 if bold_first and i == 0 else size}'>{q(t)}</run>"
                   + ("\n            <run>Æ&#10;</run>" if i < len(lines) - 1 else "")
                   for i, t in enumerate(lines))
    return "\n          <formatted-text>" + runs + "\n          </formatted-text>"


def dashboard_xml(name: str, subtitle: str, placements: list[tuple[str, tuple]],
                  legends: list[tuple[str, str, tuple]] = (), notes: list[tuple[list[str], tuple]] = (),
                  controls: list[tuple[str, tuple]] = (), height: int = H) -> str:
    global CUR_H
    CUR_H = height
    # Header: slate band + two one-line text zones (one zone holding both lines was clipped to
    # "Restaurant Intelligence.." in Tableau, so each line gets its own zone with enough height)
    zones = zone(2, 0, 0, W, 56, ztype="empty", bg=SLATE, border=False, padding=0)
    zones += zone(3, 16, 4, 700, 28, ztype="text", inner=text_run("Restaurant Intelligence", 15, bold=True),
                  bg=SLATE, border=False, padding=2)
    zones += zone(4, 16, 32, 700, 22, ztype="text", inner=text_run(subtitle, 9), bg=SLATE, border=False, padding=2)
    zid = 5
    for sheet, (x, y, w, h) in placements:
        zones += zone(zid, x, y, w, h, name=sheet)
        zid += 1
        if sheet.startswith("KPI "):  # red accent strip on top of each KPI card
            zones += zone(zid, x, y, w, 4, ztype="empty", bg=ACCENT, border=False, padding=0)
            zid += 1
    for sheet, field, (x, y, w, h) in legends:   # colour legend of a sheet (Tableau zone type 'color')
        zones += zone(zid, x, y, w, h, name=sheet, ztype="color", param=field, border=False)
        zid += 1
    for param, (x, y, w, h) in controls:          # parameter controls (drop-down lists)
        zones += zone(zid, x, y, w, h, ztype="paramctrl", param=param, mode="compact")
        zid += 1
    for lines, (x, y, w, h), *opt in notes:      # white text boxes (explanations computed from the outputs)
        zones += zone(zid, x, y, w, h, ztype="text", inner=text_lines(lines, bold_first=bool(opt and opt[0])))
        zid += 1
    return f"""    <dashboard name='{q(name)}'>
      <style>
        <style-rule element='table'>
          <format attr='background-color' value='{PAGE_BG}' />
        </style-rule>
      </style>
      <size maxheight='{height}' maxwidth='{W}' minheight='{height}' minwidth='{W}' />
      <zones>
        <zone h='100000' id='1' type-v2='layout-basic' w='100000' x='0' y='0'>{zones}
          <zone-style>
            <format attr='border-color' value='#444444' />
            <format attr='border-style' value='none' />
            <format attr='border-width' value='0' />
            <format attr='margin' value='0' />
          </zone-style>
        </zone>
      </zones>
      <simple-id uuid='{_uuid("db", name)}' />
    </dashboard>
"""


def windows_xml(sheets: list[str], dashboards: list[tuple[str, list[str]]], fits: dict[str, str]) -> str:
    """One window per worksheet, then one per dashboard (viewpoints = its sheets); the first one is open."""
    ws = ""
    for s in sheets:
        # hidden='true': every worksheet sits on a dashboard, so only the dashboard tabs are shown
        ws += f"""    <window class='worksheet' hidden='true' name='{q(s)}'>
      <cards>
        <edge name='left'>
          <strip size='160'>
            <card type='pages' />
            <card type='filters' />
            <card type='marks' />
          </strip>
        </edge>
        <edge name='top'>
          <strip size='2147483647'>
            <card type='columns' />
          </strip>
          <strip size='2147483647'>
            <card type='rows' />
          </strip>
          <strip size='31'>
            <card type='title' />
          </strip>
        </edge>
      </cards>
      <simple-id uuid='{_uuid("win", s)}' />
    </window>
"""
    for i, (dashboard, dsheets) in enumerate(dashboards):
        vps = "".join(f"\n        <viewpoint name='{q(s)}'>\n          <zoom type='{fits.get(s, 'entire-view')}' />\n"
                      "        </viewpoint>" for s in dsheets)
        maxed = " maximized='true'" if i == 0 else ""
        ws += f"""    <window class='dashboard'{maxed} name='{q(dashboard)}'>
      <viewpoints>{vps}
      </viewpoints>
      <active id='-1' />
      <simple-id uuid='{_uuid("win", dashboard)}' />
    </window>
"""
    return ws


DASH1 = "Location intelligence"
DASH2 = "Cuisine and pricing"
PRICE_LABELS = {1: "Budget", 2: "Moderate", 3: "Expensive", 4: "Luxury"}   # same labels as the Power BI report
TOP_CUISINES_D2 = 15
EXPECTED_MD = TAB_DIR / "expected_values.md"


def write_expected(pairs: pd.DataFrame, top_cuisines: list[str]) -> None:
    """Numbers the Tableau dashboard must show (computed from the same CSVs Tableau reads)."""
    d = pd.read_csv(PROC / "zomato_clean.csv", encoding="utf-8")
    rated = d[d["is_rated"] == 1]
    g = rated.groupby("city")["aggregate_rating"].agg(["size", "mean"])
    top = g[g["size"] >= RATED_CITY_MIN].sort_values("mean", ascending=False).head(TOP_CITIES)
    sizes = d["city"].value_counts()
    big = sizes[sizes >= BIG_CITY_MIN].index.tolist()
    bp = pairs[pairs["city"].isin(big)].assign(
        group=lambda x: x["cuisine"].where(x["cuisine"].isin(top_cuisines), "Other"))
    share = bp.groupby(["city", "group"]).size() / bp.groupby("city").size()
    valid = d[d["has_valid_coords"] == 1]
    lines = ["# Expected values: Tableau Dashboard 1 (Location intelligence)", "",
             "*Generated by `src/tableau_twb.py` from the CSVs the workbook reads.*", "",
             "KPI row: " + " · ".join([f"Restaurants {len(d):,}", f"Cities {d['city'].nunique():,}",
                                       f"Avg rating {rated['aggregate_rating'].mean():.2f}",
                                       f"Total votes {int(d['votes'].sum()):,}",
                                       f"Online delivery {100 * d['has_online_delivery'].mean():.1f}%"]), "",
             f"Map: {valid['city'].nunique()} city bubbles from {len(valid):,} restaurants with valid coordinates "
             f"({len(d) - len(valid):,} with (0,0) coordinates are left out). Largest: "
             + ", ".join(f"{c} {n:,}" for c, n in valid["city"].value_counts().head(4).items()) + ".", "",
             f"Average rating, top {TOP_CITIES} cities with {RATED_CITY_MIN}+ rated restaurants: "
             + ", ".join(f"{c} {m:.2f}" for c, m in top["mean"].items()) + ".", "",
             f"Cuisine mix ({', '.join(big)}; share of each city's cuisine listings):", "",
             "| City | " + " | ".join(top_cuisines + ["Other"]) + " |",
             "|---|" + "---|" * (len(top_cuisines) + 1)]
    for c in big:
        lines.append(f"| {c} | " + " | ".join(f"{100 * share.get((c, k), 0):.0f}%"
                                               for k in top_cuisines + ["Other"]) + " |")
    # ---- Dashboard 2 (Cuisine and pricing)
    pc = pairs if "price_range" in pairs else pairs.merge(d[["restaurant_id", "price_range", "aggregate_rating"]],
                                                          on="restaurant_id")
    g = pc.groupby("cuisine").agg(restaurants=("restaurant_id", "nunique"), rating=("aggregate_rating", "mean"),
                                  price=("price_range", "mean")).sort_values("restaurants", ascending=False)
    top = g.head(TOP_CUISINES_D2)
    pc = pc.assign(group=pc["city"].where(pc["city"].isin(big), "Other cities"))
    stack = pc[pc["cuisine"].isin(top.index)].groupby(["cuisine", "group"])["restaurant_id"].nunique().unstack(
        fill_value=0)
    pcount = d["price_range"].value_counts().sort_index()
    lines += ["", "# Expected values: Tableau Dashboard 2 (Cuisine and pricing)", "",
              "KPI row: " + " · ".join([f"Individual cuisines {pairs['cuisine'].nunique()}"]
                                       + [f"Price range {n} · {PRICE_LABELS[n]} {pcount[n]:,}" for n in pcount.index]),
              "", f"Top {TOP_CUISINES_D2} cuisines (restaurants offering each · average rating of rated restaurants · "
                  "average price range 1-4):", "",
              "| Cuisine | Restaurants | Avg rating | Avg price range |", "|---|---|---|---|"]
    lines += [f"| {c} | {int(r.restaurants):,} | {r.rating:.2f} | {r.price:.2f} |" for c, r in top.iterrows()]
    cols = [c for c in big if c in stack.columns] + ["Other cities"]
    lines += ["", "Cuisines by city group (restaurants offering each cuisine):", "",
              "| Cuisine | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    lines += [f"| {c} | " + " | ".join(f"{int(stack.loc[c, k]):,}" for k in cols) + " |" for c in top.index]
    EXPECTED_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build() -> Path:
    starter = STARTER.read_text(encoding="utf-8")
    pairs = write_pairs_with_city()
    # Extracts: rebuilt from the processed CSVs on every run, so they always match the data
    write_hyper(PROC / "zomato_clean.csv", HYPER_RESTAURANTS, csv_columns(starter))
    write_hyper(PAIRS_CITY_CSV, HYPER_PAIRS, PAIRS_COLUMNS)
    top_cuisines = big_city_top_cuisines(pairs)
    write_expected(pairs, top_cuisines)
    rblock, rds = restaurants_datasource(starter)
    pblock, pds = pairs_datasource(top_cuisines)
    sheets, parts = dashboard1_sheets(rds, pds)
    sheets.append(cuisine_sheet(parts, top_cuisines))

    kpi_x = [16 + i * 252 for i in range(5)]
    placements = [(n, (kpi_x[i], 68, 240, 80)) for i, (n, _) in enumerate(sheets[:5])]
    # Row below the KPIs (y 160-704): map | top-15 ratings (full height: ~33 px per bar) | cuisine mix + legend
    placements += [("Restaurants by city (map)", (16, 160, 600, 544)), ("Average rating by city (top 15)", (628, 160, 312, 544)),
                   ("Cuisine mix by city (share of listings)", (952, 160, 312, 404))]
    legends = [("Cuisine mix by city (share of listings)", f"[{pds.name}].[none:Calculation_cuisine_group:nk]", (952, 564, 312, 140))]
    d1_sheets = [n for n, _ in sheets]

    # Dashboard 2: 5 KPI cards, then four full-height columns (15 bars each, ~33 px per bar)
    sheets2 = dashboard2_sheets(rds, pds)
    placements2 = [(n, (kpi_x[i], 68, 240, 80)) for i, (n, _) in enumerate(sheets2[:5])]
    col_x, col_w = [16 + i * 315 for i in range(4)], 303
    placements2 += [(n, (col_x[i], 160, col_w, 544 if n != "Cuisines by city group" else 424))
                    for i, (n, _) in enumerate(sheets2[5:])]
    legends2 = [("Cuisines by city group", f"[{pds.name}].[none:Calculation_city_group:nk]", (col_x[3], 584, col_w, 120))]
    sheets = sheets + sheets2

    # Dashboard 3: Success prediction (from the model outputs)
    from src.tableau_success import (DASH3, HYPER_SUCCESS, SUCCESS_COLUMNS, SUCCESS_CSV, success_datasource,
                                     success_layout, success_sheets, write_success_data)
    write_success_data()
    write_hyper(SUCCESS_CSV, HYPER_SUCCESS, SUCCESS_COLUMNS)
    sblock, sds = success_datasource()
    sheets3 = success_sheets(sds)
    placements3, notes3 = success_layout(sheets3)
    sheets = sheets + sheets3

    # Dashboard 'India deep dive' (City / Locality parameters, a 'No data' message above every chart)
    from src.india import india as india_rows, tableau_rows
    from src.tableau_india import (DASH5, HYPER_INDIA, INDIA_COLUMNS, INDIA_H, TABLEAU_CSV, india_datasource, india_layout,
                                   india_sheets, parameters_datasource)
    tableau_rows(india_rows(pd.read_csv(PROC / "zomato_clean.csv", encoding="utf-8")),
                 pd.read_csv(PROC / "restaurant_cuisines.csv", encoding="utf-8"))
    write_hyper(TABLEAU_CSV, HYPER_INDIA, INDIA_COLUMNS)
    param_block, pdeps = parameters_datasource()
    iblock, ids_ = india_datasource()
    sheets5, msgs5 = india_sheets(ids_, pdeps)
    placements5, legends5, controls5 = india_layout(sheets5, msgs5, ids_)
    sheets = sheets + sheets5 + msgs5
    fits = {"Average rating by city (top 15)": "fit-height", "Cuisine mix by city (share of listings)": "entire-view",
            **{n: "fit-height" for n, _ in sheets2[5:]}, **{n: "entire-view" for n, _ in sheets3},
            **{n: "entire-view" for n, _ in sheets5 + msgs5}}
    head = starter[:starter.index("<datasources>")]
    # Format changes this workbook uses beyond the starter's: dashboard zones written with 'type-v2'
    # (the schema only declares 'type-v2' when SetMembershipControl is listed in the manifest).
    for flag in EXTRA_FORMAT_FLAGS:
        if f"<{flag} />" not in head:
            head = head.replace("    <SheetIdentifierTracking />", f"    <{flag} />\n    <SheetIdentifierTracking />", 1)
    xml = (head + "<datasources>\n    " + param_block + "\n    " + rblock + "\n    " + pblock + "\n    " + sblock
           + "\n    " + iblock + "\n  </datasources>\n"
           "  <mapsources>\n    <mapsource name='Tableau' />\n  </mapsources>\n  <worksheets>\n"
           + "".join(x for _, x in sheets) + "  </worksheets>\n  <dashboards>\n"
           + dashboard_xml(DASH1, f"Zomato restaurants data (Kaggle, CC0) · {DASH1}", placements, legends)
           + dashboard_xml(DASH2, f"Zomato restaurants data (Kaggle, CC0) · {DASH2}", placements2, legends2)
           + dashboard_xml(DASH5, f"Zomato restaurants data (Kaggle, CC0) · {DASH5}", placements5, legends5,
                           controls=controls5, height=INDIA_H)
           + dashboard_xml(DASH3, f"Zomato restaurants data (Kaggle, CC0) · {DASH3}", placements3, notes=notes3)
           + dashboard_xml(DASH4, f"Zomato restaurants data (Kaggle, CC0) · {DASH4}", [], notes=insights_notes())
           + "  </dashboards>\n  <windows source-height='30'>\n"
           + windows_xml([n for n, _ in sheets], [(DASH1, d1_sheets), (DASH2, [n for n, _ in sheets2]),
                                                       (DASH5, [n for n, _ in sheets5 + msgs5]),
                                                       (DASH3, [n for n, _ in sheets3]), (DASH4, [])], fits)
           + "  </windows>\n</workbook>\n")
    OUT.write_text(xml, encoding="utf-8")
    return OUT


EXTRA_FORMAT_FLAGS = ["SetMembershipControl"]
DASH4 = "Insights and recommendations"
TWBX = TAB_DIR / "RestaurantIntelligence.twbx"


def package_twbx(twb: Path = OUT, out: Path = TWBX) -> Path:
    """Packaged workbook, in the layout Tableau itself wrote (checked against the Tableau-made .twbx of Phase 5):
    the .twb at the root, every extract under Data/tableau/, and the extracts' dbname attributes rewritten to
    those relative paths. The CSV connections keep their directory (as Tableau left them); the extracts are used."""
    import zipfile
    text = twb.read_text(encoding="utf-8")
    hypers = sorted({Path(m) for m in re.findall(r"dbname='([^']+\.hyper)'", text)})
    for h in hypers:
        text = text.replace(f"dbname='{q(h.as_posix())}'", f"dbname='Data/tableau/{h.name}'")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(twb.name, text.encode("utf-8"))
        for h in hypers:
            z.write(h, f"Data/tableau/{h.name}")
    return out


def insights_notes() -> list[tuple]:
    """Text boxes for dashboard 4 from outputs/insights (computed by src/insights.py): a note line, 8 findings
    in two columns and the recommendations in a third column. The dashboard has no filters (whole dataset)."""
    out = config.ROOT / "outputs" / "insights"
    f = pd.read_csv(out / "insights.csv")
    r = pd.read_csv(out / "recommendations.csv")
    n = len(pd.read_csv(PROC / "zomato_clean.csv", usecols=["restaurant_id"]))
    notes = [([f"Key findings for all {n:,} restaurants (no filters). Associations in observational data, not "
               "causes. Every number is computed from the data by src/insights.py."], (16, 62, 1248, 28))]
    col_w, row_h, y0 = 404, 146, 96
    for i, row in enumerate(f.itertuples(index=False)):
        x, y = 16 + (i % 2) * (col_w + 12), y0 + (i // 2) * (row_h + 8)
        notes.append(([f"{row.id} · {row.theme}  ({row.key_number})", row.finding], (x, y, col_w, row_h), True))
    rx = 16 + 2 * (col_w + 12)
    rw, rh = W - 16 - rx, (4 * row_h + 3 * 8 - 5 * 6) / 6
    for i, row in enumerate(r.itertuples(index=False)):
        notes.append(([f"{row.id} · {row.title}", f"{row.text} (based on {row.based_on})"],
                      (rx, y0 + i * (rh + 6), rw, rh), True))
    return notes


def validate_against_tableau(path: Path = OUT) -> list[str]:
    """Validate with the schema shipped inside the installed Tableau Public (scripts/validate_twb.py)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("validate_twb", config.ROOT / "scripts" / "validate_twb.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.validate(path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Generate the Tableau workbook (run with Tableau closed).")
    ap.add_argument("--dashboard", type=int, action="append", required=True, choices=[1, 2],
                    help="accepted for clarity; the workbook always contains every finished dashboard")
    ap.parse_args()
    print("wrote", build().relative_to(config.ROOT))
    errors = validate_against_tableau()
    print(f"Tableau schema check: {'VALID' if not errors else f'{len(errors)} error(s)'}")
    for e in errors:
        print("  " + e)
    if not errors:
        print("wrote", package_twbx().relative_to(config.ROOT), "(workbook + extracts)")
    raise SystemExit(1 if errors else 0)
