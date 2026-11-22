"""Run the analysis.

Usage (from the project folder, with .venv active):
    python run_pipeline.py              # full run on the Kaggle files in data/raw/
    python run_pipeline.py --no-excel   # skip the Excel workbook
    python run_pipeline.py --no-mysql   # skip MySQL, SQL and EDA
    python run_pipeline.py --no-model   # skip recommender examples and model
    python run_pipeline.py --input data/samples/zomato_sample_india_3cities.csv
                                        # run on ANOTHER file with the same columns as the Kaggle file

Kaggle run
  Preparation: validate + load -> quality checks -> clean -> KPIs -> data dictionary + quality report -> Excel.
  Database:    load MySQL -> run analytical SQL queries -> EDA (figures, statistics, findings).
  Modelling:   recommendation engine examples -> popularity model (comparison, metrics, predictions).
  Dashboards:  Power BI data workbook (dashboards/powerbi/powerbi_data.xlsx).

New-file run (--input)
  Same preparation steps, then recommendations (top 5 per city) and popularity predictions with the SAVED
  model. Everything is written to outputs/runs/<file name>/. The MySQL database, SQL results, EDA
  figures, trained model and dashboards are NOT changed: they belong to the Kaggle analysis in the report.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from src import config
from src.cleaning import clean
from src.data_dictionary import build_dictionary, write_markdown
from src.data_loading import detect_encoding, load_raw_zomato, load_validated
from src.data_quality import run_checks, write_report
from src.excel_report import build_workbook
from src.kpis import format_kpis, headline_kpis
from src.schema import SchemaError

RUNS_DIR = config.OUTPUTS_DIR / "runs"


class Steps:
    """Prints numbered step headers: [3/12] ..."""

    def __init__(self, total: int, say):
        self.n, self.total, self.say = 0, total, say

    def __call__(self, text: str) -> None:
        self.n += 1
        self.say(f"[{self.n}/{self.total}] {text}")


def run_phase1(src: Path, paths: config.RunPaths, excel: bool, step: Steps, say) -> dict:
    step(f"Validating and loading {src.name} ...")
    res = load_validated(src)
    raw = res.df
    paths.make_dirs()                      # only after the file has passed validation
    for w in res.warnings:
        say(f"      WARNING: {w}")
    say(f"      {len(raw):,} rows, {raw.shape[1]} columns, encoding {detect_encoding(src)}")

    step("Data quality checks ...")
    checks, details = run_checks(raw)
    details["encoding"] = detect_encoding(src)
    say(f"      {len(checks)} checks run")

    step("Cleaning ...")
    cleaned, pairs, log = clean(raw)
    cleaned.to_csv(paths.clean_csv, index=False, encoding="utf-8")
    pairs.to_csv(paths.cuisines_csv, index=False, encoding="utf-8")
    log.to_csv(paths.cleaning_log_csv, index=False, encoding="utf-8")
    say(f"      {len(cleaned):,} clean rows, {len(pairs):,} restaurant-cuisine pairs")

    step("Headline KPIs:")
    kpis = headline_kpis(cleaned, pairs)
    say(format_kpis(kpis))

    step("Writing data dictionary and quality report ...")
    dictionary = build_dictionary(raw)
    write_markdown(dictionary, raw, out_path=paths.data_dictionary_md)
    write_report(checks, details, paths.quality_report_md)

    if excel:
        step("Building Excel workbook ...")
        build_workbook(load_raw_zomato(src), dictionary, checks, log, cleaned, pairs, paths.excel_report)
    else:
        step("Excel workbook skipped (--no-excel)")
    return {"raw": raw, "clean": cleaned, "pairs": pairs, "log": log, "checks": checks, "kpis": kpis}


def run(excel: bool = True, paths: config.RunPaths = config.DEFAULT_PATHS, verbose: bool = True,
        mysql: bool = True, model: bool = True) -> dict:
    """Full run on the Kaggle files in data/raw/."""
    say = print if verbose else (lambda *a, **k: None)
    t0 = time.time()
    paths.make_dirs()
    step = Steps(12, say)
    out = run_phase1(config.RAW_ZOMATO_CSV, paths, excel, step, say)
    from src.currency import write_doc as write_currency_doc
    write_currency_doc(out["clean"])
    say("      cost in US$ (approx., World Bank 2017 rates) -> docs/currency_and_costs.md")
    if mysql:
        from src.db import DatabaseError
        try:
            out.update(run_phase2(out["clean"], out["pairs"], step, say))
        except DatabaseError as e:
            say("\n      MySQL is not available, so the pipeline continues WITHOUT MySQL.\n"
                f"      Reason: {str(e).splitlines()[0]}\n"
                "      To set MySQL up: docs/MAC_SETUP.md (Mac) or docs/HOW_TO_RUN.md (Windows).\n"
                "      To skip this check next time: python run_pipeline.py --no-mysql\n")
            mysql = False
            step.n = 6
    if not mysql:
        out.update(run_without_mysql(step, say))
    if model:
        out.update(run_phase3(out["clean"], out["pairs"], step, say))
    else:
        say("[10-12] Recommendation examples, popularity model and Power BI export skipped (--no-model)")
    say(f"Done in {time.time() - t0:.1f}s.")
    return out


def run_without_mysql(step: Steps, say=print) -> dict:
    """Fallback when MySQL is not set up (or --no-mysql): skip loading and the SQL queries; the EDA charts and
    statistics are computed from the cleaned CSVs (the same data MySQL is loaded from)."""
    from src.eda import run_eda
    step("Loading MySQL ... skipped (no MySQL)")
    step("Running analytical SQL queries ... skipped (no MySQL; previous results in outputs/sql_results/ kept)")
    step("EDA from the cleaned CSV files (figures, statistics, findings) ...")
    eda = run_eda(None)
    say(f"      {len(eda['figures'])} figures, {len(eda['statistics'])} statistical tests -> docs/eda_findings.md")
    return {"eda": eda}


def run_phase2(cleaned, pairs, step: Steps, say=print) -> dict:
    from src.db import check_connection, get_engine, load_clean_data
    from src.eda import run_eda
    from src.sql_runner import run_all

    step("Loading MySQL ...")
    engine = get_engine()
    say(f"      MySQL {check_connection(engine)}")
    counts = load_clean_data(engine, cleaned, pairs)
    say("      " + ", ".join(f"{t}: {n:,}" for t, n in counts.items()))

    step("Running analytical SQL queries ...")
    results = run_all(engine)
    say(f"      {len(results)} queries -> outputs/sql_results/, docs/sql_results.md")

    step("EDA from MySQL (figures, statistics, findings) ...")
    eda = run_eda(engine)
    say(f"      {len(eda['figures'])} figures, {len(eda['statistics'])} statistical tests -> docs/eda_findings.md")
    return {"table_counts": counts, "sql_results": results, "eda": eda}


def run_phase3(cleaned, pairs, step: Steps, say=print) -> dict:
    from src.model import run_model
    from src.powerbi_export import export_powerbi
    from src.recommender import SCENARIOS, run_examples

    step("Recommendation engine examples ...")
    ex = run_examples(cleaned)
    say(f"      {len(SCENARIOS)} scenarios, {len(ex)} recommendations -> docs/recommendation_examples.md")

    step("Popularity model (4 algorithms + baseline, 5-fold CV, 80/20 test) ...")
    res = run_model(cleaned, pairs, verbose=True)
    say(f"      best: {res['best_name']} -> models/, outputs/predictions/, docs/model_results.md")
    from src.unrated import run_unrated
    un = run_unrated(cleaned, pairs)
    say(f"      unrated: {len(un['predictions']):,} restaurants profiled and scored -> docs/unrated_restaurants.md")
    from src.india import run_india
    ind = run_india(cleaned, pairs)
    say(f"      India deep dive: {len(ind['cities'])} cities, {len(ind['localities']):,} localities "
        "-> docs/india_deep_dive.md")
    from src.insights import run_insights
    ins = run_insights(cleaned)
    say(f"      insights: {len(ins['findings'])} findings, {len(ins['recommendations'])} recommendations "
        "-> docs/insights.md")

    step("Power BI data export ...")
    counts = export_powerbi(cleaned, pairs)
    say(f"      {len(counts)} tables -> dashboards/powerbi/powerbi_data.xlsx (+ expected_values.md)")
    return {"recommendations": ex, "model": res, "powerbi_tables": counts}


# ------------------------------------------------------------------------------------------------
# New-file run (--input)
# ------------------------------------------------------------------------------------------------

def city_recommendations(cleaned, top_n: int = 5):
    """Top restaurants per city with the default request (no cuisine/budget/rating/delivery filter)."""
    import pandas as pd

    from src.recommender import Request, recommend
    frames = []
    for (country, city), _ in cleaned.groupby(["country", "city"]):
        res = recommend(cleaned, Request(city=city, country=country, top_n=top_n))
        frames.append(res.assign(country=country))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _show(path: Path) -> str:
    try:
        return str(path.relative_to(config.ROOT))
    except ValueError:
        return str(path)


def run_new_file(input_path: Path, excel: bool = True, out_dir: Path | None = None, verbose: bool = True) -> dict:
    say = print if verbose else (lambda *a, **k: None)
    from src.scoring import predict_raw

    t0 = time.time()
    input_path = Path(input_path)
    out_dir = Path(out_dir) if out_dir else RUNS_DIR / input_path.stem
    paths = config.RunPaths(out_dir / "processed", out_dir / "docs", out_dir / "excel")
    say(f"New-file run: {input_path}")
    say(f"Results folder: {out_dir}")
    step = Steps(8, say)
    out = run_phase1(input_path, paths, excel, step, say)

    step("Recommendations: top 5 per city (rating + popularity; no other filters) ...")
    recs = city_recommendations(out["clean"])
    recs.to_csv(out_dir / "recommendations.csv", index=False, encoding="utf-8")
    for city, g in recs.groupby("city", sort=True):
        best = g.iloc[0]
        say(f"      {city:<20} #1 {best.restaurant_name} (rating {best.aggregate_rating:.1f}, "
            f"{best.votes:,} votes, score {best.total_score:.3f})")
    say(f"      {len(recs)} rows -> {_show(out_dir / 'recommendations.csv')}")

    step("Popularity predictions with the saved model (no re-training) ...")
    preds = predict_raw(out["raw"])
    preds.to_csv(out_dir / "predictions.csv", index=False, encoding="utf-8")
    split = preds["predicted_class"].value_counts().reindex(["High", "Medium", "Low"], fill_value=0)
    say("      predicted: " + ", ".join(f"{k} {v:,}" for k, v in split.items())
        + f"  (of {len(preds):,} restaurants)")
    say(f"      -> {_show(out_dir / 'predictions.csv')}")
    say("Not changed by a new-file run: MySQL database, SQL results, EDA figures, trained model, dashboards.")
    say(f"Done in {time.time() - t0:.1f}s.")
    out.update({"recommendations": recs, "predictions": preds, "out_dir": out_dir})
    return out


def main(argv=None) -> int:
    from src.db import DatabaseError

    p = argparse.ArgumentParser(description="Run the Restaurant Intelligence analysis.")
    p.add_argument("--input", type=Path, default=None,
                   help="Another CSV with the same columns as the Kaggle zomato.csv (results go to outputs/runs/)")
    p.add_argument("--no-excel", action="store_true", help="Skip the Excel workbook")
    p.add_argument("--no-mysql", action="store_true", help="Skip MySQL, SQL queries and EDA (Kaggle run)")
    p.add_argument("--no-model", action="store_true", help="Skip recommendation examples and the model (Kaggle run)")
    args = p.parse_args(argv)
    try:
        if args.input:
            run_new_file(args.input, excel=not args.no_excel)
        else:
            run(excel=not args.no_excel, mysql=not args.no_mysql, model=not args.no_model)
    except (SchemaError, DatabaseError, FileNotFoundError) as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 1
    except PermissionError as e:
        print(f"\nERROR: cannot write {e.filename}. Close it in Excel and try again.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
