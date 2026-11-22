"""Run the analytical queries in sql/03_analysis_queries.sql and save their results.

Each result -> outputs/sql_results/Qnn_name.csv; all results -> docs/sql_results.md (for the report).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from sqlalchemy.engine import Engine

from src import config
from src.db import QUERIES_SQL, read_sql

SQL_RESULTS_DIR = config.OUTPUTS_DIR / "sql_results"
SQL_RESULTS_MD = config.DOCS_DIR / "sql_results.md"
HEADER = re.compile(r"^--\s*(Q\d+)\s*\|\s*([a-z0-9_]+)\s*\|\s*(.+)$", re.MULTILINE)


@dataclass
class Query:
    qid: str
    name: str
    question: str
    sql: str


def parse_queries(path: Path = QUERIES_SQL) -> list[Query]:
    text = Path(path).read_text(encoding="utf-8")
    heads = list(HEADER.finditer(text))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[m.end():end].strip()
        body = body[: body.rfind(";")].strip() if ";" in body else body
        out.append(Query(m.group(1), m.group(2), m.group(3).strip(), body))
    return out


TECHNIQUES = ["JOIN", "GROUP BY", "HAVING", "Subquery", "CTE", "Window function", "Aggregate functions",
              "View", "Index used"]


def _strip_comments(sql: str) -> str:
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


def detect_techniques(sql: str) -> dict[str, bool]:
    """Detect SQL techniques from the query text (index use is added separately via EXPLAIN)."""
    s = re.sub(r"\s+", " ", _strip_comments(sql)).upper()
    no_cte_bodies = re.sub(r"\bAS \(\s*SELECT", "AS (CTE", s)  # so CTE bodies don't count as subqueries
    return {
        "JOIN": bool(re.search(r"\bJOIN\b", s)),
        "GROUP BY": "GROUP BY" in s,
        "HAVING": bool(re.search(r"\bHAVING\b", s)),
        "Subquery": bool(re.search(r"\(\s*SELECT\b", no_cte_bodies)),
        "CTE": s.lstrip().startswith("WITH "),
        "Window function": bool(re.search(r"\bOVER\s*\(", s)),
        "Aggregate functions": bool(re.search(r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\(", s)),
        "View": bool(re.search(r"\bV_[A-Z_]+\b", s)),
    }


def indexes_used(engine: Engine, sql: str) -> list[str]:
    """Index names MySQL's optimiser chooses for the query (EXPLAIN 'key' column)."""
    plan = read_sql(engine, "EXPLAIN " + sql)
    keys = plan["key"].dropna().astype(str) if "key" in plan else pd.Series(dtype=str)
    return sorted({k for k in keys if k and k.lower() != "none"})


def technique_matrix(engine: Engine, queries: list[Query] | None = None) -> pd.DataFrame:
    rows = []
    for q in queries or parse_queries():
        t = detect_techniques(q.sql)
        idx = indexes_used(engine, q.sql)
        t["Index used"] = bool(idx)
        rows.append({"Query": q.qid, **t, "Indexes (EXPLAIN)": ", ".join(idx)})
    return pd.DataFrame(rows)


def _technique_md(m: pd.DataFrame) -> list[str]:
    cols = ["Query"] + TECHNIQUES + ["Indexes (EXPLAIN)"]
    lines = ["## SQL techniques used by each query", "",
             "*Detected automatically from the query text; 'Index used' comes from MySQL `EXPLAIN` "
             "(the optimiser's actual index choice).*", "",
             "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in m.to_dict("records"):
        cells = [r["Query"]] + ["✓" if r[c] else "" for c in TECHNIQUES] + [r["Indexes (EXPLAIN)"]]
        lines.append("| " + " | ".join(cells) + " |")
    counts = [int(m[c].sum()) for c in TECHNIQUES]
    lines.append("| **Queries using it** | " + " | ".join(f"**{c}**" for c in counts) + " | |")
    lines += ["",
              "Every technique is used by at least one query." if all(counts)
              else "WARNING: some techniques are not used by any query.",
              "",
              "Notes: ticks show techniques written **directly** in the query. Queries that read a view also use "
              "the JOINs, GROUP BYs and aggregates defined inside that view (`sql/02_views.sql`). "
              "`<auto_key0>` is an index MySQL builds automatically on a CTE/derived table; the other names are "
              "the primary keys and indexes defined in `sql/01_schema.sql`.", ""]
    return lines


def _md_table(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        cells = []
        for v in row:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                cells.append("")
            elif isinstance(v, float):
                cells.append(f"{v:,.2f}".rstrip("0").rstrip("."))
            elif isinstance(v, int):
                cells.append(f"{v:,}")
            else:
                cells.append(str(v).replace("|", "/"))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def run_all(engine: Engine, out_dir: Path = SQL_RESULTS_DIR, md_path: Path = SQL_RESULTS_MD) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    md = ["# SQL Analysis Results",
          "",
          "*Generated by `src/sql_runner.py` from `sql/03_analysis_queries.sql` against the MySQL database "
          "`restaurant_intelligence`. Do not edit numbers by hand.*",
          ""]
    matrix = technique_matrix(engine)
    matrix.to_csv(out_dir / "sql_techniques.csv", index=False)
    md += _technique_md(matrix)
    for q in parse_queries():
        df = read_sql(engine, q.sql)
        df = df.convert_dtypes()
        df = df.astype(object).where(df.notna(), None)
        csv = out_dir / f"{q.qid}_{q.name}.csv"
        df.to_csv(csv, index=False, encoding="utf-8")
        results.append({"qid": q.qid, "name": q.name, "question": q.question, "rows": len(df), "csv": csv})
        md += [f"## {q.qid}. {q.question}", "", _md_table(df), ""]
    md_path.write_text("\n".join(md), encoding="utf-8")
    return results
