"""Central project paths. Uses pathlib so it works on Windows and macOS."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"

DOCS_DIR = ROOT / "docs"
EXCEL_DIR = ROOT / "excel"
SQL_DIR = ROOT / "sql"
MODELS_DIR = ROOT / "models"
OUTPUTS_DIR = ROOT / "outputs"
FIGURES_DIR = OUTPUTS_DIR / "figures"
PREDICTIONS_DIR = OUTPUTS_DIR / "predictions"
FIXTURES_DIR = ROOT / "tests" / "fixtures"

RAW_ZOMATO_CSV = RAW_DIR / "zomato.csv"
RAW_COUNTRY_XLSX = RAW_DIR / "Country-Code.xlsx"


@dataclass(frozen=True)
class RunPaths:
    """Where the data-preparation outputs are written (tests point this at a temporary folder)."""
    processed: Path
    docs: Path
    excel: Path

    @classmethod
    def default(cls) -> "RunPaths":
        """Official project locations."""
        return cls(PROCESSED_DIR, DOCS_DIR, EXCEL_DIR)

    def make_dirs(self) -> None:
        for p in (self.processed, self.docs, self.excel):
            p.mkdir(parents=True, exist_ok=True)

    @property
    def clean_csv(self) -> Path:
        return self.processed / "zomato_clean.csv"

    @property
    def cuisines_csv(self) -> Path:
        return self.processed / "restaurant_cuisines.csv"

    @property
    def cleaning_log_csv(self) -> Path:
        return self.processed / "cleaning_log.csv"

    @property
    def data_dictionary_md(self) -> Path:
        return self.docs / "data_dictionary.md"

    @property
    def quality_report_md(self) -> Path:
        return self.docs / "data_quality_report.md"

    @property
    def excel_report(self) -> Path:
        return self.excel / "zomato_phase1_analysis.xlsx"


DEFAULT_PATHS = RunPaths.default()
