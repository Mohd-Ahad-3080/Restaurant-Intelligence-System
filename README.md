# Restaurant Intelligence System

**Restaurant Recommendation and Success Prediction Using Data Analytics**

This project analyses public Zomato restaurant data from Kaggle (9,551 restaurants in 15 countries and
141 cities; CC0 licence; secondary data only). It uses five tools (Python, MySQL, Excel, Power BI and
Tableau) and a small Streamlit app, and it delivers:

- a **recommendation engine** that ranks restaurants and shows how each score is made;
- a **popularity model** that predicts High, Medium or Low popularity on Zomato without data leakage;
- **dashboards** (6 Power BI pages, 5 Tableau dashboards) and a **what-if app** for predictions and
  recommendations;
- a project **report** (short and full versions) with all results.

**Start here: `Project_Guide.pdf`** (delivered next to this package). It explains every part in simple
steps, including the Mac setup. Short technical notes: `docs/HOW_TO_RUN.md` and `docs/MAC_SETUP.md`.

## Folder map

| Folder / file | Contents |
|---|---|
| `run_pipeline.py` | Runs the whole analysis (`--no-mysql` without a database, `--input <file>` for another file) |
| `src/` | Python code: loading, checks, cleaning, database link, analysis, model, recommender, dashboard files |
| `scripts/` | `app.py` (what-if app), `recommend.py`, `predict.py`, `setup_mac.sh`, two dashboard helpers |
| `sql/` | Database setup, tables, views and the analytical queries |
| `data/` | `raw/` (original files, never changed), `processed/` (cleaned data), `samples/` (small real sample) |
| `models/` | The saved popularity model and its settings |
| `outputs/` | Figures, model results, SQL results, India, unrated and insight tables |
| `excel/` | Excel workbook with live formulas and charts |
| `dashboards/` | Power BI (`.pbix`, `.pbip` project, PDF and page images) and Tableau (`.twbx`, images) |
| `notebooks/` | Exploratory analysis notebook |
| `report/` | Project report (short and full, `.docx` and `.pdf`) and the Extended Abstract |
| `docs/` | How to run, Mac setup, viva preparation, and the documents the code generates |
| `tests/` | Automated tests (`python -m pytest -q`) |
| `requirements.txt`, `.env.example` | Python libraries, and a template for the MySQL settings (no password included) |

## Quick start

macOS: `bash scripts/setup_mac.sh` (see `docs/MAC_SETUP.md`). Windows:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run_pipeline.py --no-mysql
streamlit run scripts/app.py
```

On Windows, unzip to a short folder such as `C:\RestaurantIntelligence` (the Power BI project has long file
paths). Power BI Desktop runs only on Windows; on a Mac, use `dashboards/powerbi/exports/RestaurantIntelligence.pdf`.
The Tableau file `dashboards/tableau/RestaurantIntelligence.twbx` opens on both.
