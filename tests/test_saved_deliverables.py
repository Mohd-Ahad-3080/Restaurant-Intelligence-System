"""Files saved by hand from Power BI Desktop (.pbix, PDF export) must match the generated project.

Guards against saving from a Power BI session that was opened before the latest regeneration (that happened
once: the .pbix kept the old Insights text and layout)."""
import json
import zipfile

import pandas as pd
import pytest

from src import config
from src.powerbi_pbip import PAGE_DISPLAY, REPORT_DEF, TABS

PBI = config.ROOT / "dashboards" / "powerbi"
PBIX = PBI / "RestaurantIntelligence.pbix"
PDF = PBI / "exports" / "RestaurantIntelligence.pdf"
PAGE_NAMES = [PAGE_DISPLAY.get(n, label) for n, label, _ in TABS]


def _texts(read, names) -> dict[str, str]:
    """visual name -> all text of that textbox visual."""
    out = {}
    for n in names:
        if n.endswith("visual.json") and "/visuals/" in n:
            v = json.loads(read(n))["visual"]
            paras = v.get("objects", {}).get("general", [{}])[0].get("properties", {}).get("paragraphs", [])
            if paras:
                out[n.split("/")[-2]] = " ".join(r["value"] for p in paras for r in p["textRuns"])
    return out


def test_pbix_matches_generated_report():
    if not PBIX.exists():
        pytest.skip("No .pbix saved yet")
    with zipfile.ZipFile(PBIX) as z:
        names = z.namelist()
        pages = {json.loads(z.read(n))["displayName"] for n in names if n.endswith("/page.json")}
        saved = _texts(z.read, names)
    assert pages == set(PAGE_NAMES)
    files = [str(p.relative_to(REPORT_DEF.parent.parent)).replace("\\", "/")
             for p in REPORT_DEF.glob("pages/*/visuals/gen_p6_*/visual.json")]
    generated = _texts(lambda n: (REPORT_DEF.parent.parent / n).read_text(encoding="utf-8"), files)
    assert generated and all(saved.get(k) == v for k, v in generated.items()), \
        "the .pbix Insights page differs from the generated one: re-open the .pbip, Save as .pbix again"


def test_pdf_and_page_images_have_all_pages_in_tab_order():
    pymupdf = pytest.importorskip("pymupdf")          # Windows-only helper package
    if not PDF.exists():
        pytest.skip("No PDF exported yet")
    doc = pymupdf.open(PDF)
    assert doc.page_count == len(PAGE_NAMES)
    for page, name in zip(doc, PAGE_NAMES):
        assert f"· {name}" in " ".join(page.get_text().split())
    f = pd.read_csv(config.ROOT / "outputs" / "insights" / "insights.csv")
    last = " ".join(doc[-1].get_text().split())
    assert all(" ".join(x.split())[:60] in last for x in f["finding"])
    import importlib.util
    spec = importlib.util.spec_from_file_location("x", config.ROOT / "scripts" / "export_dashboard_pngs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert [t for _, t in mod.PAGES] == PAGE_NAMES
    assert all((PBI / "exports" / f).exists() for f, _ in mod.PAGES)
