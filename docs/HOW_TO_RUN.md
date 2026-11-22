# How to Run the Project (Windows, VS Code)

This guide is for running and showing the project yourself. You don't need to know programming: copy
each command, paste it into the VS Code terminal, press **Enter**, and compare what you see with the
**Expected output** box.

Every expected output below was produced on this PC on 2026-11-10. Small differences in timing
("Done in 98.9s") are normal. **The numbers must match.**

**Contents**
1. Open the project
2. Run the full pipeline
3. Look at the data at each stage (CSV → Excel → MySQL)
4. EDA notebook and charts
5. Recommendation engine
6. Popularity prediction
7. Run on a different data file
8. Run the tests
9. Open the dashboards (Power BI, Tableau)
10. 10-minute demo script
11. If something goes wrong
12. What-if app (Streamlit, Windows and Mac)

---

## 1. Open the project

1. Start **VS Code**.
2. **File → Open Folder…** → choose `D:\restaurant-intelligence` → **Select Folder**.
   If VS Code asks "Do you trust the authors?", click **Yes, I trust the authors**.
3. Open the terminal: **Terminal → New Terminal** (or press `` Ctrl + ` ``). A panel opens at the bottom
   showing `PS D:\restaurant-intelligence>`.
4. Switch on the project's Python environment (`.venv`). You do this **once every time** you open a new
   terminal:

```powershell
.venv\Scripts\Activate.ps1
```

**Expected output:** no message. The start of the line now shows **`(.venv)`**:
```
(.venv) PS D:\restaurant-intelligence>
```

5. Check it worked:

```powershell
python --version
```
**Expected output:**
```
Python 3.13.5
```

> If you see "running scripts is disabled on this system", run this once and try step 4 again:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (answer **Y** if asked).

**All commands below assume `(.venv)` is showing.**

---

## 2. Run the full pipeline (Kaggle data)

```powershell
python run_pipeline.py
```

**What it does, in order:**
- reads the Kaggle file `data/raw/zomato.csv`;
- checks its quality and cleans it, and adds an approximate cost in US dollars;
- builds the Excel workbook;
- loads everything into MySQL and runs the 28 SQL queries (without MySQL it says so and carries on);
- makes the EDA charts and runs the statistical tests;
- runs the recommendation examples;
- trains and compares the 4 popularity models, then the model variants, the Medium-class checks and the
  High-vs-Low model;
- profiles the unrated restaurants, runs the India deep dive and computes the insights;
- exports the data for Power BI.

**How long:** about **4 minutes** (250.3 seconds on the last run). Step 11 (the models) takes most of it.
**Before you start:** close the Excel workbook and Power BI if they are open, because the pipeline
rewrites their files. MySQL runs automatically in the background as a Windows service.

**Expected output:**
```
[1/12] Validating and loading zomato.csv ...
      9,551 rows, 22 columns, encoding latin-1
[2/12] Data quality checks ...
      41 checks run
[3/12] Cleaning ...
      9,551 clean rows, 19,705 restaurant-cuisine pairs
[4/12] Headline KPIs:
  Restaurants                 : 9,551
  Countries                   : 15
  Cities                      : 141
  Rated restaurants           : 7,403
  Average rating (rated only) : 3.44
  Total votes                 : 1,498,645
  Online delivery %           : 25.7
  Table booking %             : 12.1
  Unique cuisine combinations : 1,821
  Unique individual cuisines  : 145
[5/12] Writing data dictionary and quality report ...
[6/12] Building Excel workbook ...
      cost in US$ (approx., World Bank 2017 rates) -> docs/currency_and_costs.md
[7/12] Loading MySQL ...
      MySQL 8.4.9
      countries: 15, restaurants: 9,551, restaurant_cuisines: 19,705
[8/12] Running analytical SQL queries ...
      28 queries -> outputs/sql_results/, docs/sql_results.md
[9/12] EDA from MySQL (figures, statistics, findings) ...
      12 figures, 12 statistical tests -> docs/eda_findings.md
[10/12] Recommendation engine examples ...
      4 scenarios, 20 recommendations -> docs/recommendation_examples.md
[11/12] Popularity model (4 algorithms + baseline, 5-fold CV, 80/20 test) ...
      Baseline (majority class)  CV macro-F1 0.167 | test acc 0.336, macro-F1 0.168, AUC 0.500
      Logistic Regression        CV macro-F1 0.555 | test acc 0.550, macro-F1 0.543, AUC 0.732
      Decision Tree              CV macro-F1 0.551 | test acc 0.567, macro-F1 0.561, AUC 0.741
      Random Forest              CV macro-F1 0.578 | test acc 0.581, macro-F1 0.573, AUC 0.768
      Gradient Boosting          CV macro-F1 0.624 | test acc 0.613, macro-F1 0.611, AUC 0.795
      check: Main model (all rated, all features)     acc 0.613, macro-F1 0.611, AUC 0.795 (baseline 0.336)
      check: Delhi NCR only (consistent sampling)     acc 0.614, macro-F1 0.614, AUC 0.790 (baseline 0.374)
      check: All rated, location features removed     acc 0.519, macro-F1 0.514, AUC 0.715 (baseline 0.336)
      leakage demo (illustration only, + votes & rating): acc 0.988, macro-F1 0.988, AUC 1.000
      variant: Main (all countries, all features)     rows 7,403 | acc 0.613, macro-F1 0.611, AUC 0.795
      variant: No location (all countries)            rows 7,403 | acc 0.519, macro-F1 0.514, AUC 0.715
      variant: India, with city/locality              rows 6,513 | acc 0.625, macro-F1 0.622, AUC 0.802
      variant: India, without city/locality           rows 6,513 | acc 0.572, macro-F1 0.569, AUC 0.748
      variant: Baseline (majority class)              rows 7,403 | acc 0.336, macro-F1 0.168, AUC 0.500
      variant: Leaky: + votes and rating (INVALID)    rows 7,403 | acc 0.988, macro-F1 0.988, AUC 1.000
      medium: Before: main model (highest probability)  acc 0.613, macro-F1 0.611 | Medium P 0.503 R 0.472
      medium: Class weights (Medium up-weighted)        acc 0.613, macro-F1 0.611 | Medium P 0.503 R 0.472
      medium: Threshold tuning (Medium bias)            acc 0.604, macro-F1 0.604 | Medium P 0.486 R 0.495
      medium: Ordinal (Frank and Hall)                  acc 0.621, macro-F1 0.621 | Medium P 0.502 R 0.515
      separate question, High vs Low (Medium excluded): acc 0.832, macro-F1 0.832, AUC 0.925 (baseline 0.501)
      best: Gradient Boosting -> models/, outputs/predictions/, docs/model_results.md
      unrated: 2,148 restaurants profiled and scored -> docs/unrated_restaurants.md
      India deep dive: 43 cities, 841 localities -> docs/india_deep_dive.md
      insights: 8 findings, 6 recommendations -> docs/insights.md
[12/12] Power BI data export ...
      9 tables -> dashboards/powerbi/powerbi_data.xlsx (+ expected_values.md)
Done in 250.3s.
```

**The numbers to remember:** 9,551 restaurants · 141 cities · 3.44 average rating · 25.7% online
delivery · 28 SQL queries · best model Gradient Boosting with **61.3% accuracy** (test acc 0.613).

**Files it creates or updates** (running it again overwrites them with the same results):

| What | Where |
|---|---|
| Cleaned data | `data/processed/zomato_clean.csv`, `restaurant_cuisines.csv`, `cleaning_log.csv` |
| Data dictionary, quality report | `docs/data_dictionary.md`, `docs/data_quality_report.md` |
| Excel workbook | `excel/zomato_phase1_analysis.xlsx` |
| MySQL database | `restaurant_intelligence` (3 tables, 7 views) |
| SQL results | `outputs/sql_results/Q01…Q28.csv`, `docs/sql_results.md` |
| EDA charts and tests | `outputs/figures/fig01…fig12.png`, `outputs/eda_statistics.csv`, `docs/eda_findings.md` |
| Recommendation examples | `docs/recommendation_examples.md`, `outputs/recommendation_examples.csv` |
| Model and results | `models/popularity_model.joblib`, `outputs/predictions/*.csv`, `outputs/figures/fig13…fig19.png`, `docs/model_results.md` |
| Currency, unrated, India, insights | `docs/currency_and_costs.md`, `outputs/unrated/`, `docs/unrated_restaurants.md`, `outputs/india/`, `docs/india_deep_dive.md`, `outputs/insights/`, `docs/insights.md`, `outputs/figures/fig20…fig22.png` |
| Power BI data | `dashboards/powerbi/powerbi_data.xlsx` |

Optional switches: `--no-mysql` (skip MySQL; the charts are made from the cleaned CSV files instead), `--no-model` (skip the model), `--no-excel`.

---

## 3. Look at the data at each stage

### 3a. Raw CSV (as downloaded from Kaggle)

In VS Code's left panel (Explorer), click `data` → `raw` → `zomato.csv` to see the file. Or print the
first rows:

```powershell
python -c "import pandas as pd; d=pd.read_csv('data/raw/zomato.csv', encoding='latin-1'); print(d.shape); print(d[['Restaurant Name','City','Cuisines','Aggregate rating','Rating text','Votes']].head(3).to_string())"
```
**Expected output:**
```
(9551, 21)
          Restaurant Name              City                          Cuisines  Aggregate rating Rating text  Votes
0        Le Petit Souffle       Makati City        French, Japanese, Desserts               4.8   Excellent    314
1        Izakaya Kikufuji       Makati City                          Japanese               4.5   Excellent    591
2  Heat - Edsa Shangri-La  Mandaluyong City  Seafood, Asian, Filipino, Indian               4.4   Very Good    270
```
*Say:* "9,551 restaurants, 21 columns, exactly as published on Kaggle. We never change this file."

### 3b. Cleaned CSV

```powershell
python -c "import pandas as pd; d=pd.read_csv('data/processed/zomato_clean.csv'); print(d.shape); print(d[['restaurant_name','city','cuisines','aggregate_rating','votes','popularity_class']].head(3).to_string())"
```
**Expected output:**
```
(9551, 28)
          restaurant_name              city                          cuisines  aggregate_rating  votes popularity_class
0        Le Petit Souffle       Makati City        French, Japanese, Desserts               4.8    314           Medium
1        Izakaya Kikufuji       Makati City                          Japanese               4.5    591             High
2  Heat - Edsa Shangri-La  Mandaluyong City  Seafood, Asian, Filipino, Indian               4.4    270              Low
```
*Say:* "Same restaurants. The column names are tidy, and there are 7 extra columns: the country name
plus 6 helper columns, such as the popularity class (Low / Medium / High within each country)."

To see every cleaning step and how many rows it changed:
```powershell
python -c "import pandas as pd; print(pd.read_csv('data/processed/cleaning_log.csv')[['step_no','step','rows_affected']].to_string(index=False))"
```
**Expected output (24 steps; key lines):**
```
       6  Remove invisible control characters (U+0080-U+009F)            164
       8  Fix country spelling 'Phillipines' -> 'Philippines'             22
      16  Rating 0 / 'Not rated' -> missing                             2148
      22  Zero / out-of-range coordinates -> missing                     499
      23  Add popularity_class (Option B)                               7403
```

### 3c. Excel workbook

Open `excel\zomato_phase1_analysis.xlsx` (double-click it in File Explorer, or right-click it in VS Code
→ **Reveal in File Explorer**). It has 11 sheets:

| Sheet | Show this |
|---|---|
| `Raw_Sample` | The first rows exactly as in the Kaggle file |
| `Data_Dictionary` | What every column means |
| `Quality_Checks` | The 41 checks with counts (e.g. 2,148 "Not rated") |
| `Cleaning_Log` | The 24 cleaning steps |
| `Cleaned_Data` | The full clean table (9,551 rows) |
| `Cuisine_Pairs` | One row per restaurant–cuisine pair (19,705) |
| `Summary_By_Country` | Click a number: it is a live **COUNTIF/AVERAGEIF** formula, not typed in |
| `Summary_By_City`, `Summary_By_Cuisine`, `Summary_By_Price_Range` | More formula summaries |
| `Charts` | 6 Excel charts |

Close Excel before running the pipeline again.

### 3d. MySQL (command line)

1. Find the database password: open the file `.env` in VS Code and copy the value after `MYSQL_PASSWORD=`.
   This file is private; never share it or put it in the report.
2. In the terminal, start the MySQL client:

```powershell
& "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe" -u ri_app -p restaurant_intelligence
```
3. At `Enter password:` paste the password (nothing appears while you type; that is normal) and press
   **Enter**. The prompt changes to `mysql>`.
4. Paste each query below and press **Enter**.

**List the tables and views:**
```sql
SHOW TABLES;
```
**Expected output:** `countries`, `restaurant_cuisines`, `restaurants` and 7 views (`v_city_summary`,
`v_country_summary`, `v_cuisine_summary`, `v_locality_summary`, `v_price_summary`,
`v_restaurant_branches`, `v_restaurants`), so 10 rows in total.

**Q01: Headline figures**
```sql
SELECT COUNT(*) AS restaurants, COUNT(DISTINCT country_code) AS countries, COUNT(DISTINCT city) AS cities, SUM(is_rated) AS rated_restaurants, ROUND(AVG(aggregate_rating), 2) AS avg_rating_rated_only, SUM(votes) AS total_votes, ROUND(100 * AVG(has_online_delivery), 1) AS online_delivery_pct, ROUND(100 * AVG(has_table_booking), 1) AS table_booking_pct FROM restaurants;
```
**Expected output:**
```
+-------------+-----------+--------+-------------------+-----------------------+-------------+---------------------+-------------------+
| restaurants | countries | cities | rated_restaurants | avg_rating_rated_only | total_votes | online_delivery_pct | table_booking_pct |
+-------------+-----------+--------+-------------------+-----------------------+-------------+---------------------+-------------------+
|        9551 |        15 |    141 |              7403 |                  3.44 |     1498645 |                25.7 |              12.1 |
+-------------+-----------+--------+-------------------+-----------------------+-------------+---------------------+-------------------+
```

**Q06: How rating, votes, delivery and booking change with price range** (uses a view and a window function)
```sql
SELECT price_range, restaurants, ROUND(100 * restaurants / SUM(restaurants) OVER (), 2) AS share_pct, avg_rating, avg_votes, online_delivery_pct, table_booking_pct FROM v_price_summary ORDER BY price_range;
```
**Expected output:**
```
+-------------+-------------+-----------+------------+-----------+---------------------+-------------------+
| price_range | restaurants | share_pct | avg_rating | avg_votes | online_delivery_pct | table_booking_pct |
+-------------+-------------+-----------+------------+-----------+---------------------+-------------------+
|           1 |        4444 |     46.53 |       3.24 |      44.6 |                15.8 |               0.0 |
|           2 |        3113 |     32.59 |       3.38 |     147.6 |                41.3 |               7.7 |
|           3 |        1408 |     14.74 |       3.78 |     443.9 |                29.2 |              45.7 |
|           4 |         586 |      6.14 |       3.89 |     368.6 |                 9.0 |              46.8 |
+-------------+-------------+-----------+------------+-----------+---------------------+-------------------+
```

**Q21: Is popularity related to price range?**
```sql
SELECT price_range, SUM(is_rated) AS rated_restaurants, ROUND(100 * SUM(popularity_class = 'Low') / SUM(is_rated), 1) AS low_pct, ROUND(100 * SUM(popularity_class = 'Medium') / SUM(is_rated), 1) AS medium_pct, ROUND(100 * SUM(popularity_class = 'High') / SUM(is_rated), 1) AS high_pct FROM restaurants GROUP BY price_range ORDER BY price_range;
```
**Expected output:**
```
+-------------+-------------------+---------+------------+----------+
| price_range | rated_restaurants | low_pct | medium_pct | high_pct |
+-------------+-------------------+---------+------------+----------+
|           1 |              2744 |    53.6 |       33.0 |     13.3 |
|           2 |              2711 |    27.0 |       38.8 |     34.1 |
|           3 |              1373 |    13.1 |       23.7 |     63.2 |
|           4 |               575 |    16.9 |       28.2 |     55.0 |
+-------------+-------------------+---------+------------+----------+
```

5. Leave MySQL with:
```sql
exit
```

All 28 queries, each with its question, are in `sql/03_analysis_queries.sql`. You can copy any one of
them into the `mysql>` prompt. Their saved results are in `docs/sql_results.md`.

---

## 4. EDA notebook and charts

The notebook reads the data **from MySQL**, makes the charts and runs the statistical tests.

**Option A (nothing to install): Jupyter in the browser**
```powershell
jupyter notebook notebooks/02_eda.ipynb
```
**Expected:** after a few seconds your web browser opens the notebook. Choose **Run → Run All Cells**.
It finishes in about 10 seconds, with charts appearing under the cells. When done, close the browser tab,
go back to the terminal and press **Ctrl + C** (twice if asked) to stop Jupyter.

**Option B: inside VS Code.** Install two free extensions once: **Extensions** (left bar) → search
**Python** (by Microsoft) → Install, then **Jupyter** (by Microsoft) → Install. Open
`notebooks/02_eda.ipynb`, click **Select Kernel** (top right) → **Python Environments** → `.venv`, then
click **Run All**.

**Where the charts are:** `outputs/figures/`. Click any `.png` in VS Code to view it:
- `fig01_restaurants_by_country.png` to `fig12_rating_by_cuisine.png`: EDA charts;
- `fig13_model_comparison.png`, `fig14_confusion_matrix.png`, `fig15_feature_importance.png`: model charts.

The written findings, with all 12 statistical tests, are in `docs/eda_findings.md`.

---

## 5. Recommendation engine

**Easiest: answer the questions.** Press Enter to accept the suggested value in [brackets]:
```powershell
python scripts/recommend.py
```
```
City (e.g. New Delhi, Gurgaon, Mumbai, London) [New Delhi]:
Cuisine(s), comma-separated, or leave empty for any [North Indian]:
Budget for two in local currency, or leave empty for no limit [800]:
Minimum rating (0 to 5) [3.5]:
Online delivery required? (yes/no) [yes]:
Locality (optional, e.g. Connaught Place):
```

**Or type everything in one line:**
```powershell
python scripts/recommend.py --city "New Delhi" --cuisine "North Indian" --budget 800 --min-rating 3.5 --delivery required --top 5
```
**Expected output:**
```
Request: New Delhi | cuisine: North Indian | budget: 800 Indian Rupees(Rs.) | min rating: 3.5 | delivery: required
Filters: in city: 5,473 -> rating >= 3.5: 1,456 -> offers online delivery: 670

 #         Restaurant                 Locality Rating Votes Cost Rating pts Popular pts Budget pts Cuisine pts SCORE
 1    QD's Restaurant Delhi University-GTB Nag    3.9 2,724  800      0.312       0.220      0.200       0.150 0.882
 2      Indus Flavour Delhi University-GTB Nag    4.1 1,384  700      0.328       0.201      0.200       0.150 0.879
 3 The Vintage Avenue                GTB Nagar    3.9 1,439  800      0.312       0.202      0.200       0.150 0.864
 4   Bikkgane Biryani          Connaught Place    4.1   740  800      0.328       0.184      0.200       0.150 0.862
 5    QD's Restaurant              Laxmi Nagar    4.1   675  800      0.328       0.181      0.200       0.150 0.859

SCORE = 0.40 x rating + 0.25 x popularity + 0.20 x budget fit + 0.15 x cuisine match (the 'pts' columns add up to SCORE).
```

**How to read it:**
- **Filters** shows how many restaurants are left after each filter.
- The four **pts** columns explain each score. For example, QD's Restaurant scores
  0.312 + 0.220 + 0.200 + 0.150 = **0.882**.

This is the same result as Example S1 in the report.

**Other examples:**
- `--city Gurgaon --cuisine Italian --budget 2000 --min-rating 4`
- `--city London --cuisine British --budget 60 --min-rating 4`. London's budget is in pounds: **the
  budget is always in the city's own currency.**

**Options:**

| Option | Meaning |
|---|---|
| `--cuisine` | Several cuisines are allowed: `"Chinese, Thai"` |
| `--locality` | Restrict to one area, e.g. `"Sector 18"` |
| `--delivery` | `any` or `required` |
| `--top` | How many results (default 10) |

A wrong city gives a helpful message, e.g. `ERROR: City 'Atlantis' not found.`

Note: a few names show odd characters (e.g. `Cafí©`). That damage is already in the Kaggle file. It is
a recorded limitation and was deliberately not "guessed" back.

---

## 6. Popularity prediction (saved model)

This uses the saved model `models/popularity_model.joblib`; no training happens. You describe a
restaurant and the model returns **High / Medium / Low** with probabilities. It never needs votes or a
rating, so it works for a restaurant that has just opened.

**Easiest: answer the questions:**
```powershell
python scripts/predict.py
```

**Or one line:**
```powershell
python scripts/predict.py --city "New Delhi" --locality "Connaught Place" --cuisines "North Indian, Chinese" --price-range 2 --cost 600 --delivery yes --booking no
```
**Expected output** (takes about 3 seconds):
```
Restaurant : New restaurant | New Delhi, India | Connaught Place
Input      : North Indian, Chinese | price range 2 | cost for two 600 Indian Rupees(Rs.) | delivery yes | booking no
Context    : cost percentile in India = 66 (0 cheapest, 100 dearest); 123 restaurant(s) in this locality and 1 branch(es) with this name (both counts include this one)
Note       : Coordinates not given: using the middle of the locality.

PREDICTED POPULARITY: HIGH
  High    82.0%  #################################
  Medium  13.2%  #####
  Low      4.8%  ##

Model: Gradient Boosting (test accuracy 61.3%; random guessing about 33%). Popularity = Zomato votes relative to the same country, not sales.
```

**Two more examples that give different answers** (good for the demo):

```powershell
python scripts/predict.py --city "New Delhi" --locality "Laxmi Nagar" --cuisines "Street Food, North Indian" --price-range 1 --cost 250 --delivery no --booking no
```
Expected: **PREDICTED POPULARITY: LOW**. Probabilities: High 1.3%, Medium 18.3%, Low 80.4%.

```powershell
python scripts/predict.py --city Faridabad --locality "Sector 15" --cuisines "Fast Food" --price-range 1 --cost 200 --delivery no --booking no
```
Expected: **PREDICTED POPULARITY: MEDIUM**. Probabilities: High 7.5%, Medium 54.7%, Low 37.8%.

**Inputs:**

| Option | Meaning |
|---|---|
| `--city` | Must be one of the 141 cities in the data |
| `--locality` | Optional; it sets the "competition" (restaurants in the same locality) |
| `--cuisines` | Comma-separated, e.g. `"Cafe, Italian"` |
| `--price-range` | 1 (budget) to 4 (luxury) |
| `--cost` | Cost for two in local currency |
| `--delivery`, `--booking` | `yes` or `no` |
| `--name` | Optional. A known chain name (e.g. `"Domino's Pizza"`) counts its existing branches |

**Be honest about it in the demo:**
- The model is right about 61% of the time, against about 33% for guessing.
- For cities outside Delhi NCR it tends to say **High**. Zomato listed mostly famous restaurants there
  (72.1% of them are High), and the model learned that pattern. Use Delhi NCR cities (New Delhi, Gurgaon,
  Noida, Faridabad) to show differences.

---

## 7. Run on a different data file

**Before this update**, `run_pipeline.py` could only read the Kaggle file; there was no `--input`
option. **Now** `--input` runs on any CSV with the **same columns as the Kaggle `zomato.csv`**. It does
the following:
- the same checks and cleaning, the KPIs, the data dictionary, the quality report and an Excel workbook;
- recommendations for every city in the file;
- popularity predictions for every restaurant, using the saved model.

It does **not** retrain the model, load MySQL or change any report output. Those stay based on the
Kaggle data, so the report's numbers are protected.

**Sample file provided:** `data/samples/zomato_sample_india_3cities.csv` has 66 real restaurants from
the Kaggle file: every restaurant in Ghaziabad (25), Amritsar (21) and Agra (20).

```powershell
python run_pipeline.py --input data/samples/zomato_sample_india_3cities.csv
```
**Expected output** (about 3 seconds):
```
New-file run: data\samples\zomato_sample_india_3cities.csv
Results folder: D:\restaurant-intelligence\outputs\runs\zomato_sample_india_3cities
[1/8] Validating and loading zomato_sample_india_3cities.csv ...
      66 rows, 22 columns, encoding utf-8-sig
[2/8] Data quality checks ...
      36 checks run
[3/8] Cleaning ...
      66 clean rows, 131 restaurant-cuisine pairs
[4/8] Headline KPIs:
  Restaurants                 : 66
  Countries                   : 1
  Cities                      : 3
  Rated restaurants           : 64
  Average rating (rated only) : 3.56
  Total votes                 : 8,093
  Online delivery %           : 15.2
  Table booking %             : 4.5
  Unique cuisine combinations : 37
  Unique individual cuisines  : 20
[5/8] Writing data dictionary and quality report ...
[6/8] Building Excel workbook ...
[7/8] Recommendations: top 5 per city (rating + popularity; no other filters) ...
      Agra                 #1 Sheroes Hangout (rating 4.9, 77 votes, score 0.952)
      Amritsar             #1 Kesar Da Dhabha (rating 4.1, 878 votes, score 0.928)
      Ghaziabad            #1 Dunkin' Donuts (rating 3.6, 252 votes, score 0.877)
      15 rows -> outputs\runs\zomato_sample_india_3cities\recommendations.csv
[8/8] Popularity predictions with the saved model (no re-training) ...
      predicted: High 50, Medium 13, Low 3  (of 66 restaurants)
      -> outputs\runs\zomato_sample_india_3cities\predictions.csv
Not changed by a new-file run: MySQL database, SQL results, EDA figures, trained model, dashboards.
Done in 2.0s.
```
(The file has fewer columns, so fewer quality checks apply: 36 instead of 41.)

**Where the results are:** `outputs\runs\zomato_sample_india_3cities\`:

| File | Contents |
|---|---|
| `processed\zomato_clean.csv` | The cleaned file |
| `processed\cleaning_log.csv` | The cleaning steps for this file |
| `excel\zomato_phase1_analysis.xlsx` | The same 11-sheet workbook, for this file only |
| `recommendations.csv` | Top 5 per city with the score breakdown |
| `predictions.csv` | One row per restaurant: predicted class and the 3 probabilities |
| `docs\` | Data dictionary and quality report for this file |

**Check that the predictions are sensible:** for the 64 rated restaurants in the sample, the predicted
class agrees with their real class in the Kaggle data **60.9%** of the time. That is in line with the
model's 61.3%.

You can also run the recommender on the new file's results:
```powershell
python scripts/recommend.py --city Agra --data outputs/runs/zomato_sample_india_3cities/processed/zomato_clean.csv
```

**Your own file** must have the same column headers as `zomato.csv`. Five optional columns may be
missing (Address, Locality Verbose, Is delivering now, Switch to order menu, Rating color). A file with
wrong or missing required columns stops with a clear `ERROR:` message explaining what is wrong.

---

## 8. Run the tests

```powershell
python -m pytest -q
```
**Expected output** (about half a minute):
```
........................................................................ [ 42%]
........................................................................ [ 85%]
........................                                                 [100%]
168 passed in 25.79s
```
**What it means:**
- Each **dot** is one automated check that passed. There are 168, covering the data, the cleaning, the
  database, the SQL, the model (including the no-leakage rule), the model variants, the recommender, the
  commands, the app, the Mac setup files, and the Power BI and Tableau files.
- An **F** would mean a check failed, with details printed underneath. An **s** means "skipped" (for
  example, when MySQL or Tableau is not installed).
- The last line must say **"168 passed"**, with nothing failed.

Run the tests after `python run_pipeline.py`, and close Tableau first. One test reads Tableau's data
files, which Tableau locks while it is open.

---

## 9. Open the dashboards

### Power BI (6 pages, Windows only)
1. In File Explorer, double-click `dashboards\powerbi\RestaurantIntelligence.pbix`.
   Power BI Desktop opens the report (allow about 30 seconds).
2. **Check:** with nothing selected, page 1 shows **9,551 · 141 · 3.44 · 1,498,645 · 25.7%**.
3. **What to click:**

| Control | How to use it |
|---|---|
| **Page tabs** (Overview, Customers and market, Location intelligence, India deep dive, Success prediction, Insights) | **Ctrl + click** them. Power BI Desktop needs Ctrl to "press" a button; the page names at the bottom also work |
| **Slicers** (Country, City, Price range, Cuisine; Locality on the India page) | Click a value, e.g. Country = India; all cards and charts update. Ctrl + click picks several |
| **Reset** | **Ctrl + click** clears every slicer |
| **Bars** | Click a bar (e.g. a cuisine) to filter the other charts on the page; click it again to undo |

A chart that a selection leaves empty says **"No data for this selection"**. The India deep dive page is
always limited to India. The Insights page has no slicers (its findings describe the whole data set).
On a Mac, use `dashboards/powerbi/exports/RestaurantIntelligence.pdf` instead.

### Tableau (5 dashboards, Windows and Mac)
1. Double-click `dashboards\tableau\RestaurantIntelligence.twbx`. Tableau Public opens it; it contains
   its own data.
2. **Tabs at the bottom:** Location intelligence, Cuisine and pricing, India deep dive, Success prediction,
   Insights and recommendations.
3. **What to click:**
   - hover over any bar or bubble to see its exact numbers;
   - on **India deep dive**, choose a **City** and a **Locality** in the drop-downs at the top (scroll down to
     see all charts); a red line "No data for this selection" appears above a chart that has nothing to show;
   - click a colour in a legend to highlight it; click it again to undo;
   - press **F7** (Window → Presentation Mode) for full screen, and **Esc** to leave.
4. Close Tableau **without saving**.

The dashboards show the Kaggle data. A new-file run (section 7) does not change them.

---

## 10. Ten-minute demo script

Before the demo, open VS Code with the terminal activated (`(.venv)` showing), the Excel workbook,
Power BI and Tableau. Run `python run_pipeline.py` once beforehand so everything is fresh, and close
Excel while it runs.

| Min | Do this | Say this |
|---|---|---|
| 0:00 | Show `README.md` or the report title page | "Restaurant Recommendation and Success Prediction: public Zomato data, five tools, two outputs: recommendations for diners and a popularity prediction for owners." |
| 0:30 | Run the raw-CSV command (3a) | "9,551 restaurants in 15 countries, straight from Kaggle. This is secondary data only; nothing invented." |
| 1:30 | Run `python run_pipeline.py --no-model --no-excel` (about 11 seconds; Excel can stay open), then show the cleaning log (3b) | "One command checks and cleans the data. Every change is logged: for example, 2,148 zero ratings really mean 'not rated', so they are treated as missing." |
| 3:00 | Excel: `Quality_Checks`, then `Summary_By_Country`; click a formula | "The Excel summaries are live formulas, so anyone can verify them." |
| 4:00 | MySQL: run Q21 (3d) | "The data sits in a MySQL database with 28 analytical queries. Here, popularity rises with price range: 13% High in budget restaurants against 63% in range 3." |
| 5:00 | Open `outputs/figures/fig10_high_popularity_by_services.png` | "Restaurants offering both table booking and delivery are High popularity 78% of the time, against 25% with neither." |
| 5:45 | Run the recommender one-liner (section 5) | "The recommender ranks by rating, popularity, budget and cuisine, and shows the points behind every score." |
| 6:45 | Run the Connaught Place prediction, then Laxmi Nagar (section 6) | "The model predicts High, Medium or Low without using votes or ratings; that would be cheating, known as data leakage. It is right about 61% of the time, nearly double guessing." |
| 8:00 | Power BI: Overview → select India → Ctrl+click Success prediction | "The dashboard shows the same verified numbers. Slicers filter everything. This page holds the model results." |
| 9:00 | Tableau: Location intelligence → Cuisine and pricing | "The same data in Tableau: the city map and cuisine pricing." |
| 9:30 | Run `python -m pytest -q` (or show the app: `streamlit run scripts/app.py`) | "168 automated checks confirm that the data, the database, the model rules and the dashboards are consistent." |

To show the "new data" feature instead of MySQL, replace 4:00 with section 7: "the same pipeline runs
on another file with the same columns and gives recommendations and predictions for it."

---

## 11. If something goes wrong

| Message | What to do |
|---|---|
| `python` is not recognized / no `(.venv)` | Run `.venv\Scripts\Activate.ps1` again (section 1) |
| `MySQL is not available, so the pipeline continues WITHOUT MySQL` | The MySQL service is stopped. Open the **Services** app, find **MySQL84** and click **Start**, then run again. Or use `--no-mysql` |
| `ERROR: cannot write ... Close it in Excel` | Close the Excel workbook (or Power BI) and run again |
| `ERROR: City '...' not found. Did you mean: ...?` | Use one of the suggested spellings |
| `Unknown cuisine(s)` | Check the spelling. Cuisines are listed in Excel, sheet `Summary_By_Cuisine` |
| Tests fail with "Permission denied" on a `.hyper` file | Close Tableau and run the tests again |

---

## 12. What-if app (Streamlit, Windows and Mac)

A small app in your web browser with two tabs. It runs only on your computer; nothing is sent anywhere.

```powershell
streamlit run scripts/app.py
```

**What happens:** the terminal prints `Local URL: http://localhost:8501` and your browser opens that page
(if it does not, copy the address into the browser). To stop the app, click in the terminal and press
**Ctrl + C**.

- **Predict** tab: choose city, locality (optional), cuisines, price range, cost for two, online delivery and
  table booking, then click **Predict**. You get High / Medium / Low with the probability of each. It is the
  same saved model and the same code as `python scripts/predict.py`, so both always give the same answer.
- **Recommend** tab: choose city, cuisines, budget for two (0 = no limit), minimum rating and whether online
  delivery is required, then click **Recommend**. You get the top 10 with the four score parts
  (rating, popularity, budget, cuisine) that add up to SCORE. It is the same engine as
  `python scripts/recommend.py`. With the default inputs (New Delhi, North Indian, 800, 3.5, delivery required)
  the list starts with the same restaurant as Example S1 in the report.

If filters leave nothing, the app says "No restaurants match these filters." instead of an empty table.
