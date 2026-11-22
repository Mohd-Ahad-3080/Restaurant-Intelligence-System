"""Convert the Power BI PDF export into one high-resolution PNG per page, for the project report.

Usage (after exporting the PDF from Power BI Desktop, see dashboards/powerbi/POWERBI_GUIDE.md):
    python scripts/export_dashboard_pngs.py [path/to/RestaurantIntelligence.pdf] [--dpi 300]

Checks that the PDF has exactly 6 pages (tab order) and that each page's header subtitle matches the expected
page, so the PNG names cannot end up on the wrong pages.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "dashboards" / "powerbi" / "exports"
DEFAULT_PDF = EXPORT_DIR / "RestaurantIntelligence.pdf"
PAGES = [  # (file name, text that appears in that page's header subtitle)
    ("page1_overview.png", "Overview"),
    ("page2_customers_market.png", "Customers and market"),
    ("page3_location.png", "Location intelligence"),
    ("page4_india.png", "India deep dive"),
    ("page5_prediction.png", "Success prediction"),
    ("page6_insights.png", "Insights and recommendations"),
]


def export(pdf: Path, dpi: int = 300) -> list[Path]:
    doc = pymupdf.open(pdf)
    if doc.page_count != len(PAGES):
        raise SystemExit(f"{pdf.name} has {doc.page_count} pages; expected {len(PAGES)}.")
    out = []
    for page, (name, label) in zip(doc, PAGES):
        text = page.get_text()
        if text.strip() and label not in text:  # a fully rasterised page has no text; then skip the check
            raise SystemExit(f"PDF page {page.number + 1} does not look like '{label}'. Check the page order.")
        pix = page.get_pixmap(dpi=dpi)
        target = EXPORT_DIR / name
        pix.save(target)
        out.append(target)
        print(f"{name}: {pix.width} x {pix.height} px"
              + ("" if text.strip() else " (page has no text layer: order not verified)"))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf", nargs="?", type=Path, default=DEFAULT_PDF)
    ap.add_argument("--dpi", type=int, default=300)
    a = ap.parse_args()
    if not a.pdf.exists():
        sys.exit(f"Not found: {a.pdf}. Export the PDF from Power BI first (POWERBI_GUIDE.md, 'Export').")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    export(a.pdf, a.dpi)
