"""Build the Excel analysis workbook with openpyxl.

Summary sheets use live Excel formulas (COUNTIF/COUNTIFS/AVERAGEIF/SUMIF) that point at
the Cleaned_Data and Cuisine_Pairs sheets, so every figure is recalculated by Excel from the
data in the workbook. Row lists (countries, cities, cuisines, price ranges) are read from the
data, never typed in.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

SHEETS = ["Raw_Sample", "Data_Dictionary", "Quality_Checks", "Cleaning_Log", "Cleaned_Data",
          "Cuisine_Pairs", "Summary_By_Country", "Summary_By_City", "Summary_By_Cuisine",
          "Summary_By_Price_Range", "Charts"]
RAW_SAMPLE_ROWS = 200
TOP_CUISINES_IN_CHART = 15
# Neutral placeholder colour for workbook charts (dashboard theme not yet confirmed).
CHART_COLOUR = "2A78D6"

HEADER_FONT = Font(bold=True)
HEADER_FILL = PatternFill("solid", fgColor="E7E6E2")
PCT, DEC2, DEC1, INT = "0.0%", "0.00", "0.0", "#,##0"


# ---------------------------------------------------------------- helpers
def _py(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, str):
        v = ILLEGAL_CHARACTERS_RE.sub("", v)
    return v


def _write_df(ws, df: pd.DataFrame) -> None:
    ws.append([str(c) for c in df.columns])
    for row in df.itertuples(index=False):
        ws.append([_py(v) for v in row])
    _style_header(ws, len(df.columns))


def _style_header(ws, n_cols: int, row: int = 1, freeze: bool = True) -> None:
    for c in range(1, n_cols + 1):
        cell = ws.cell(row=row, column=c)
        cell.font, cell.fill = HEADER_FONT, HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    if freeze:
        # Set once only: setting and then clearing freeze_panes leaves an orphan
        # <selection pane="bottomLeft"> that Excel 2010 refuses to open.
        ws.freeze_panes = ws.cell(row=row + 1, column=1)


def _widths(ws, widths: dict[int, int] | None = None, default: int = 14) -> None:
    for c in range(1, ws.max_column + 1):
        ws.column_dimensions[get_column_letter(c)].width = (widths or {}).get(c, default)


def _fmt(ws, col: int, fmt: str, first: int, last: int) -> None:
    for r in range(first, last + 1):
        ws.cell(row=r, column=col).number_format = fmt


class Ref:
    """Absolute range references into a data sheet, by column name."""

    def __init__(self, sheet: str, columns: list[str], n_rows: int):
        self.sheet, self.cols, self.last = sheet, columns, n_rows + 1

    def __call__(self, name: str) -> str:
        L = get_column_letter(self.cols.index(name) + 1)
        return f"{self.sheet}!${L}$2:${L}${self.last}"


def _bar(ws, title: str, data_ws, cat_col: int, val_col: int, first: int, last: int,
         anchor: str, horizontal: bool = True, number_format: str | None = None):
    ch = BarChart()
    ch.type = "bar" if horizontal else "col"
    ch.title, ch.legend, ch.gapWidth = title, None, 60
    ch.title.overlay = False  # title above the plot area, not drawn over the bars
    ch.add_data(Reference(data_ws, min_col=val_col, min_row=first, max_row=last), titles_from_data=False)
    ch.set_categories(Reference(data_ws, min_col=cat_col, min_row=first, max_row=last))
    s = ch.series[0]
    s.graphicalProperties.solidFill = CHART_COLOUR
    s.graphicalProperties.line.solidFill = CHART_COLOUR
    ch.x_axis.delete = False
    ch.y_axis.delete = False
    # No axis titles: Excel 2010 overlaps them with tick labels; the chart title names the measure.
    ch.y_axis.majorGridlines = None
    ch.y_axis.scaling.min = 0  # bars must start at zero (Excel may otherwise truncate the axis)
    if number_format:
        ch.y_axis.number_format = number_format
    if horizontal:
        ch.x_axis.scaling.orientation = "maxMin"  # largest at top
        ch.y_axis.crosses = "max"                 # keep value axis at the bottom
    rows = last - first + 1
    ch.height = max(7.5, 0.5 * rows + 2) if horizontal else 7.5
    ch.width = 16
    ws.add_chart(ch, anchor)


# ---------------------------------------------------------------- summary sheets
def _summary_country(wb, clean: pd.DataFrame, R: Ref) -> int:
    ws = wb.create_sheet("Summary_By_Country")
    hdr = ["Country", "Restaurants", "Rated restaurants", "Avg rating (rated only)", "Total votes",
           "Online delivery %", "Table booking %", "Avg price range (1-4)", "Currency",
           "Average cost for two (local currency)", "Average cost for two (US$, approx., World Bank 2017 rates)"]
    ws.append(hdr)
    countries = clean["country"].value_counts().index.tolist()
    currencies = clean.groupby("country")["currency"].agg(lambda s: " / ".join(sorted(s.dropna().unique())))
    for i, c in enumerate(countries, start=2):
        a = f"$A{i}"
        ws.append([
            c,
            f"=COUNTIF({R('country')},{a})",
            f"=COUNTIFS({R('country')},{a},{R('is_rated')},1)",
            f'=IFERROR(AVERAGEIF({R("country")},{a},{R("aggregate_rating")}),"")',
            f"=SUMIF({R('country')},{a},{R('votes')})",
            f"=IFERROR(COUNTIFS({R('country')},{a},{R('has_online_delivery')},1)/B{i},\"\")",
            f"=IFERROR(COUNTIFS({R('country')},{a},{R('has_table_booking')},1)/B{i},\"\")",
            f'=IFERROR(AVERAGEIF({R("country")},{a},{R("price_range")}),"")',
            _py(currencies.get(c)),
            f'=IFERROR(AVERAGEIF({R("country")},{a},{R("avg_cost_for_two")}),"")',
            f'=IFERROR(AVERAGEIF({R("country")},{a},{R("avg_cost_for_two_usd")}),"")',
        ])
    last = len(countries) + 1
    t = last + 1
    ws.append([
        "TOTAL (all countries)", f"=SUM(B2:B{last})", f"=SUM(C2:C{last})",
        f'=IFERROR(AVERAGE({R("aggregate_rating")}),"")', f"=SUM(E2:E{last})",
        f"=COUNTIF({R('has_online_delivery')},1)/B{t}", f"=COUNTIF({R('has_table_booking')},1)/B{t}",
        f"=AVERAGE({R('price_range')})", "mixed", "n/a (different currencies)",
        f"=AVERAGE({R('avg_cost_for_two_usd')})",
    ])
    for c in range(1, len(hdr) + 1):
        ws.cell(row=t, column=c).font = HEADER_FONT
    _style_header(ws, len(hdr))
    for col, f in [(2, INT), (3, INT), (4, DEC2), (5, INT), (6, PCT), (7, PCT), (8, DEC2), (10, INT), (11, DEC2)]:
        _fmt(ws, col, f, 2, t)
    _widths(ws, {1: 22, 9: 26, 10: 18, 11: 22})
    return last


def _summary_city(wb, clean: pd.DataFrame, R: Ref) -> int:
    ws = wb.create_sheet("Summary_By_City")
    hdr = ["Country", "City", "Restaurants", "Rated restaurants", "Avg rating (rated only)",
           "Total votes", "Online delivery %", "Table booking %", "Avg price range (1-4)"]
    ws.append(hdr)
    pairs = (clean.groupby(["country", "city"]).size().reset_index(name="n")
             .sort_values(["n", "country", "city"], ascending=[False, True, True]))
    for i, (country, city) in enumerate(zip(pairs["country"], pairs["city"]), start=2):
        k = f"{R('country')},$A{i},{R('city')},$B{i}"
        ws.append([
            _py(country), _py(city),
            f"=COUNTIFS({k})",
            f"=COUNTIFS({k},{R('is_rated')},1)",
            f'=IFERROR(AVERAGEIFS({R("aggregate_rating")},{k}),"")',
            f"=SUMIFS({R('votes')},{k})",
            f"=IFERROR(COUNTIFS({k},{R('has_online_delivery')},1)/C{i},\"\")",
            f"=IFERROR(COUNTIFS({k},{R('has_table_booking')},1)/C{i},\"\")",
            f'=IFERROR(AVERAGEIFS({R("price_range")},{k}),"")',
        ])
    last = len(pairs) + 1
    _style_header(ws, len(hdr))
    for col, f in [(3, INT), (4, INT), (5, DEC2), (6, INT), (7, PCT), (8, PCT), (9, DEC2)]:
        _fmt(ws, col, f, 2, last)
    _widths(ws, {1: 18, 2: 22})
    return last


def _summary_cuisine(wb, pairs_df: pd.DataFrame, P: Ref, n_restaurants_ref: str) -> int:
    ws = wb.create_sheet("Summary_By_Cuisine")
    hdr = ["Cuisine", "Restaurants serving it", "% of all restaurants", "Avg rating (rated only)",
           "Avg price range (1-4)", "Online delivery %"]
    ws.append(hdr)
    cuisines = pairs_df["cuisine"].value_counts().index.tolist()
    for i, c in enumerate(cuisines, start=2):
        a = f"$A{i}"
        ws.append([
            _py(c),
            f"=COUNTIF({P('cuisine')},{a})",
            f"=B{i}/{n_restaurants_ref}",
            f'=IFERROR(AVERAGEIF({P("cuisine")},{a},{P("aggregate_rating")}),"")',
            f'=IFERROR(AVERAGEIF({P("cuisine")},{a},{P("price_range")}),"")',
            f"=IFERROR(COUNTIFS({P('cuisine')},{a},{P('has_online_delivery')},1)/B{i},\"\")",
        ])
    last = len(cuisines) + 1
    _style_header(ws, len(hdr))
    for col, f in [(2, INT), (3, PCT), (4, DEC2), (5, DEC2), (6, PCT)]:
        _fmt(ws, col, f, 2, last)
    _widths(ws, {1: 22})
    return last


def _summary_price(wb, clean: pd.DataFrame, R: Ref) -> int:
    ws = wb.create_sheet("Summary_By_Price_Range")
    hdr = ["Price range", "Restaurants", "% of restaurants", "Rated restaurants", "Avg rating (rated only)",
           "Avg votes", "Online delivery %", "Table booking %"]
    ws.append(hdr)
    ranges = sorted(int(v) for v in clean["price_range"].dropna().unique())
    for i, p in enumerate(ranges, start=2):
        a = f"$A{i}"
        ws.append([
            p,
            f"=COUNTIF({R('price_range')},{a})",
            f"=B{i}/COUNT({R('restaurant_id')})",
            f"=COUNTIFS({R('price_range')},{a},{R('is_rated')},1)",
            f'=IFERROR(AVERAGEIF({R("price_range")},{a},{R("aggregate_rating")}),"")',
            f'=IFERROR(AVERAGEIF({R("price_range")},{a},{R("votes")}),"")',
            f"=IFERROR(COUNTIFS({R('price_range')},{a},{R('has_online_delivery')},1)/B{i},\"\")",
            f"=IFERROR(COUNTIFS({R('price_range')},{a},{R('has_table_booking')},1)/B{i},\"\")",
        ])
    last = len(ranges) + 1
    _style_header(ws, len(hdr))
    for col, f in [(2, INT), (3, PCT), (4, INT), (5, DEC2), (6, DEC1), (7, PCT), (8, PCT)]:
        _fmt(ws, col, f, 2, last)
    _widths(ws)
    return last


def _charts(wb, clean: pd.DataFrame, R: Ref, last_country: int, last_cuisine: int, last_price: int):
    ws = wb.create_sheet("Charts")
    ws["A1"] = "Charts are drawn from the Summary_* sheets and the helper tables below (all live formulas)."
    ws["A1"].font = Font(italic=True)

    # helper table 1: rating bands, ordered by the band's mean rating (Not rated first)
    ws["A3"], ws["B3"] = "Rating band", "Restaurants"
    order = (clean.assign(r=clean["aggregate_rating"].fillna(-1))
             .groupby("rating_text")["r"].mean().sort_values().index.tolist())
    r = 4
    for band in order:
        ws.cell(row=r, column=1, value=_py(band))
        ws.cell(row=r, column=2, value=f"=COUNTIF({R('rating_text')},A{r})")
        r += 1
    band_last = r - 1

    # helper table 2: popularity class
    pc0 = band_last + 2
    ws.cell(row=pc0, column=1, value="Popularity class (rated only)")
    ws.cell(row=pc0, column=2, value="Restaurants")
    for j, lab in enumerate(["Low", "Medium", "High"], start=1):
        ws.cell(row=pc0 + j, column=1, value=lab)
        ws.cell(row=pc0 + j, column=2, value=f"=COUNTIF({R('popularity_class')},A{pc0 + j})")
    for rr in (3, pc0):
        _style_header(ws, 2, row=rr, freeze=False)
    _widths(ws, {1: 28, 2: 14})

    sc, scu, sp = wb["Summary_By_Country"], wb["Summary_By_Cuisine"], wb["Summary_By_Price_Range"]
    top = min(last_cuisine, TOP_CUISINES_IN_CHART + 1)
    _bar(ws, "Number of restaurants by country", sc, 1, 2, 2, last_country, "D3")
    _bar(ws, f"Top {top - 1} cuisines: number of restaurants serving each", scu, 1, 2, 2, top, "N3")
    _bar(ws, "Number of restaurants by rating band", ws, 1, 2, 4, band_last, "D25", horizontal=False)
    _bar(ws, "Number of restaurants by price range (1 = cheapest)", sp, 1, 2, 2, last_price, "N25",
         horizontal=False)
    _bar(ws, "Average rating (0-5) by price range, rated only", sp, 1, 5, 2, last_price, "D42",
         horizontal=False, number_format="0.0")
    _bar(ws, "Popularity class split (rated only)", ws, 1, 2, pc0 + 1, pc0 + 3, "N42",
         horizontal=False)


# ---------------------------------------------------------------- main builder
def build_workbook(raw: pd.DataFrame, dictionary: pd.DataFrame, checks: pd.DataFrame,
                   log: pd.DataFrame, clean: pd.DataFrame, pairs: pd.DataFrame, out_path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Raw_Sample"
    _write_df(ws, raw.head(RAW_SAMPLE_ROWS))
    _widths(ws)

    for name, df in [("Data_Dictionary", dictionary), ("Quality_Checks", checks), ("Cleaning_Log", log)]:
        ws = wb.create_sheet(name)
        _write_df(ws, df)
        _widths(ws, default=20)

    ws = wb.create_sheet("Cleaned_Data")
    _write_df(ws, clean)
    _widths(ws)
    R = Ref("Cleaned_Data", list(clean.columns), len(clean))

    pairs_full = pairs.merge(clean[["restaurant_id", "country", "aggregate_rating", "price_range",
                                    "has_online_delivery"]], on="restaurant_id", how="left")
    ws = wb.create_sheet("Cuisine_Pairs")
    _write_df(ws, pairs_full)
    _widths(ws)
    P = Ref("Cuisine_Pairs", list(pairs_full.columns), len(pairs_full))

    last_country = _summary_country(wb, clean, R)
    _summary_city(wb, clean, R)
    last_cuisine = _summary_cuisine(wb, pairs_full, P, f"COUNT({R('restaurant_id')})")
    last_price = _summary_price(wb, clean, R)
    _charts(wb, clean, R, last_country, last_cuisine, last_price)

    wb.calculation.fullCalcOnLoad = True  # Excel recalculates every formula when opened
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path
