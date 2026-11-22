"""macOS support: setup script, requirements, no Windows-only code paths, and the no-MySQL fallback."""
import re
import shutil
import subprocess

import pytest

from src import config

ROOT = config.ROOT


def test_setup_mac_script_is_valid_bash_with_lf_endings():
    p = ROOT / "scripts" / "setup_mac.sh"
    raw = p.read_bytes()
    assert raw.startswith(b"#!/usr/bin/env bash\n") and b"\r" not in raw
    text = raw.decode("utf-8")
    for must in ("python3.13", "python3.12", "-m venv .venv", "pip install --prefer-binary -r requirements.txt",
                 "cp .env.example .env", "if [ ! -f .env ]", "pytest", "--prefer-binary"):
        assert must in text, must
    bash = shutil.which("bash")
    if bash:
        assert subprocess.run([bash, "-n", str(p)], capture_output=True).returncode == 0


def test_requirements_have_mac_builds_and_no_windows_only_packages():
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    pins = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s#]+)", req, re.M))
    # 0.0.26963 ships Windows/Linux wheels only; 0.0.26479 also has macOS arm64 + x86_64 (checked on PyPI)
    assert pins["tableauhyperapi"] == "0.0.26479"
    assert "streamlit" in pins
    assert not {"pywin32", "pypiwin32", "comtypes", "docx2pdf", "wmi"} & {k.lower() for k in pins}


def test_no_hard_coded_windows_paths_in_code():
    allowed = {"src/tableau_twb.py": "directory='D:/restaurant-intelligence/data/processed'",   # replaced at run time
               "scripts/validate_twb.py": 'Path("C:/Program Files/Tableau")'}   # Windows location, Mac one next to it
    files = list((ROOT / "src").glob("*.py")) + list((ROOT / "scripts").glob("*.py")) + [ROOT / "run_pipeline.py"]
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        for line in f.read_text(encoding="utf-8").splitlines():
            if re.search(r"\b[A-Z]:[\\/]", line) and allowed.get(rel, "\0") not in line:
                pytest.fail(f"{rel}: hard-coded Windows path: {line.strip()}")


def test_mysql_setup_sql_matches_env_example():
    sql = (ROOT / "sql" / "00_create_database_and_user.sql").read_text(encoding="utf-8")
    env = dict(re.findall(r"^(\w+)=(.*)$", (ROOT / ".env.example").read_text(encoding="utf-8"), re.M))
    assert f"CREATE DATABASE IF NOT EXISTS {env['MYSQL_DB']}" in sql
    code = " ".join(l for l in sql.splitlines() if not l.lstrip().startswith("--")).upper()
    assert f"'{env['MYSQL_USER']}'@'localhost'".upper() in code and "DROP " not in code   # never deletes anything


def test_pipeline_falls_back_when_mysql_is_missing(monkeypatch, capsys):
    """run() must not crash when MySQL cannot be reached: clear message, then the no-MySQL path."""
    import run_pipeline as rp
    from src.db import DatabaseError
    calls = []
    monkeypatch.setattr(rp, "run_phase1", lambda *a, **k: {"clean": None, "pairs": None})
    monkeypatch.setattr("src.currency.write_doc", lambda clean: None)

    def no_db(*a, **k):
        raise DatabaseError("Cannot connect to MySQL (test).")
    monkeypatch.setattr(rp, "run_phase2", no_db)
    monkeypatch.setattr(rp, "run_without_mysql", lambda step, say: calls.append("fallback") or {})
    rp.run(excel=False, mysql=True, model=False, verbose=True)
    out = capsys.readouterr().out
    assert calls == ["fallback"]
    assert "continues WITHOUT MySQL" in out and "--no-mysql" in out and "MAC_SETUP.md" in out


def test_csv_eda_equals_mysql_eda():
    """The fallback EDA reads the cleaned CSVs; its statistics must equal the MySQL ones (needs MySQL to compare)."""
    import pandas as pd
    from src.db import DatabaseError, check_connection, get_engine
    from src.eda import load_from_csv, load_from_mysql, run_statistics
    try:
        engine = get_engine()
        check_connection(engine)
    except DatabaseError as e:
        pytest.skip(f"MySQL not available: {e}")
    a = run_statistics(load_from_mysql(engine)[0]).reset_index(drop=True)
    b = run_statistics(load_from_csv()[0]).reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b, check_dtype=False)
