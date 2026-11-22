#!/usr/bin/env bash
# Restaurant Intelligence - one-time setup on macOS (Apple Silicon or Intel).
# Run from the project folder:   bash scripts/setup_mac.sh
# What it does: finds Python 3.12/3.13, creates .venv, installs requirements.txt, copies .env.example to .env
# (only if .env does not exist yet) and runs quick checks plus the test suite. It changes nothing outside
# this folder and never touches MySQL.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== 1/5 Looking for Python 3.12 or 3.13"
PY=""
for c in python3.13 python3.12 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    v=$("$c" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
    if [ "$v" = "3.12" ] || [ "$v" = "3.13" ]; then PY="$c"; break; fi
  fi
done
if [ -z "$PY" ]; then
  echo "   Python 3.12 or 3.13 was not found."
  echo "   Install Python 3.13 from https://www.python.org/downloads/macos/ (docs/MAC_SETUP.md, step 1), then run this again."
  exit 1
fi
echo "   using $PY ($("$PY" --version))"

echo "== 2/5 Virtual environment (.venv)"
if [ ! -d .venv ]; then "$PY" -m venv .venv; echo "   created .venv"; else echo "   .venv already exists (kept)"; fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip

echo "== 3/5 Installing requirements.txt (a few minutes the first time)"
python -m pip install --prefer-binary -r requirements.txt   # ready-made wheels (no compiler needed on Intel Macs)

echo "== 4/5 Settings file (.env)"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "   created .env from .env.example. Edit MYSQL_PASSWORD only if you set up MySQL (docs/MAC_SETUP.md, step 5)."
else
  echo "   .env already exists (kept)"
fi

echo "== 5/5 Quick checks"
python - <<'PYCHECK'
import importlib, platform, sys
from pathlib import Path
print(f"   Python {platform.python_version()} on macOS {platform.mac_ver()[0]} ({platform.machine()})")
for m in ["pandas", "numpy", "sklearn", "scipy", "matplotlib", "openpyxl", "joblib", "sqlalchemy",
          "mysql.connector", "tableauhyperapi", "streamlit", "docx"]:
    importlib.import_module(m)
print("   all packages import")
missing = [f for f in ["data/raw/zomato.csv", "data/raw/Country-Code.xlsx", "models/popularity_model.joblib",
                       "data/processed/zomato_clean.csv"] if not Path(f).exists()]
print("   project files present" if not missing else f"   MISSING: {missing}")
sys.exit(1 if missing else 0)
PYCHECK
python -m pytest -q
echo
echo "Setup finished. Next steps: docs/MAC_SETUP.md, step 6 (run the pipeline, recommend.py, predict.py, the app)."
echo "Every new Terminal window: cd into this folder, then:  source .venv/bin/activate"
