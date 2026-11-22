# Running the Project on a Mac

This guide is for running the project on a Mac (Apple Silicon M1/M2/M3/M4, or Intel). You do not need to be
a programmer: copy each command, paste it into **Terminal**, press **Return**, and check the result.

> **Honest status:** the project was built and tested on Windows. It has **not** yet been run on a real Mac.
> What was checked for macOS: every Python package has a ready-made macOS version for Python 3.12 and 3.13
> (Apple Silicon and Intel); no code uses Windows-only paths or programs (apart from Power BI, which
> exists only for Windows, see step 8); the setup script uses Mac line endings and passes a syntax check; the
> "no MySQL" path was tested. If something on the Mac behaves differently, see **Troubleshooting** at the end.

**What works on a Mac**

| Part | On a Mac? |
|---|---|
| Python pipeline, recommendations, predictions, tests | Yes |
| What-if app (Streamlit, in the browser) | Yes |
| MySQL database and the 28 SQL queries | Yes, after installing MySQL (optional, step 5) |
| Excel workbook (`excel/zomato_phase1_analysis.xlsx`) | Yes, opens in Excel for Mac or Numbers |
| Tableau dashboards (`.twbx`) | Yes, in Tableau Desktop Public Edition (free) |
| Power BI dashboard (`.pbix` / `.pbip`) | **No**: Power BI Desktop exists only for Windows. Use the PDF and PNG exports (step 8). |

**Time needed:** about 30 minutes the first time (mostly downloads).

---

## 1. Install Python 3.13

The project needs **Python 3.12 or 3.13** (3.11 is too old for the pinned numpy version).

1. Open <https://www.python.org/downloads/macos/> and download the latest **Python 3.13** "macOS 64-bit universal2
   installer" (works on Apple Silicon and Intel).
2. Double-click the downloaded `.pkg` file and click **Continue / Agree / Install** until it finishes.
3. In the folder that opens (Applications > Python 3.13), double-click **Install Certificates.command**.
   A Terminal window runs for a few seconds; close it when it says it is done.
4. Check: open **Terminal** (press **Cmd + Space**, type `Terminal`, press Return) and type:

```bash
python3 --version
```

**Expected:** `Python 3.13.x` (any last number). If you see an older version, close Terminal, open it again
and try once more.

---

## 2. Unzip the project and open it in Terminal

1. Double-click the project zip file (for example in **Downloads**). macOS creates a folder next to it.
2. Drag that folder into your **Documents** folder and rename it `restaurant-intelligence` if needed.
3. In Terminal, go into the folder:

```bash
cd ~/Documents/restaurant-intelligence
```

Tip: you can also type `cd ` (with a space) and then drag the folder from Finder into the Terminal window.

Check that you are in the right place:

```bash
ls
```

**Expected:** you see names such as `run_pipeline.py`, `requirements.txt`, `scripts`, `src`, `data`, `docs`.

---

## 3. Run the setup script (once)

```bash
bash scripts/setup_mac.sh
```

It does five things and prints a header for each:
1. finds Python 3.12 or 3.13;
2. creates the project's own Python environment in the folder `.venv`;
3. installs all packages from `requirements.txt` (a few minutes; lots of text is normal);
4. creates the settings file `.env` from `.env.example` (only if `.env` does not exist yet);
5. checks that every package loads and that the data and the saved model are present, then runs the tests.

**Expected at the end:** a line like `... passed, ... skipped` (MySQL tests are **skipped**, not failed,
until MySQL is set up; the Tableau schema test is skipped unless Tableau is installed) and then
`Setup finished.`

---

## 4. Every time you open a new Terminal window

```bash
cd ~/Documents/restaurant-intelligence
source .venv/bin/activate
```

**Expected:** the line now starts with `(.venv)`. All commands below assume this.

---

## 5. MySQL (optional)

Without MySQL everything still runs: the pipeline says that MySQL is not available, skips loading the
database and the 28 SQL queries (their saved results stay in `outputs/sql_results/`), and builds the charts
and statistics from the cleaned CSV files instead (the same data). Do this step only if you want to run the
SQL part yourself.

1. Find your chip: Apple menu > **About This Mac**. "Apple M…" = Apple Silicon (ARM); "Intel" = Intel (x86).
2. Download **MySQL Community Server 8.4 LTS** from <https://dev.mysql.com/downloads/mysql/>: choose
   **macOS**, then the **DMG Archive** for your chip (ARM 64-bit or x86 64-bit). You can click
   "No thanks, just start my download".
3. Open the `.dmg`, double-click the `.pkg` and install. When asked, choose **Use Strong Password Encryption**
   and set a **root password**. Write it down.
4. Start the server: **System Settings > MySQL** (at the bottom of the list) > **Start MySQL Server**.
   Tick "Start MySQL when your computer starts up" if you like.
5. Make the `mysql` command available in Terminal (once):

```bash
echo 'export PATH="/usr/local/mysql/bin:$PATH"' >> ~/.zprofile
source ~/.zprofile
mysql --version
```

6. Choose a password for the project account. Open `sql/00_create_database_and_user.sql` in TextEdit and replace
   **every** `change_me` with that password. Save. Then run it as root (it asks for the root password):

```bash
mysql -u root -p < sql/00_create_database_and_user.sql
```

**Expected:** `Database restaurant_intelligence and user ri_app are ready.`

7. Open `.env` in TextEdit (`open -e .env`) and set `MYSQL_PASSWORD=` to the same project password. Save.

---

## 6. Run the project

**Full pipeline** (a few minutes; close the Excel workbook first, because it is rewritten):

```bash
python run_pipeline.py
```

Without MySQL, add `--no-mysql` to skip the database check:

```bash
python run_pipeline.py --no-mysql
```

**Expected:** numbered steps `[1/12] ... [12/12]`, the same headline numbers as on Windows
(9,551 restaurants, 141 cities, average rating 3.44), the four model results (best: Gradient Boosting,
test accuracy 0.613) and `Done in ...s.` The steps and numbers are listed in `docs/HOW_TO_RUN.md`, section 2.

**Recommendations:**

```bash
python scripts/recommend.py --city "New Delhi" --cuisine "North Indian" --budget 800 --min-rating 3.5 --delivery required --top 5
```

**Expected:** a ranked list starting with QD's Restaurant (SCORE 0.882).

**Prediction for a new restaurant:**

```bash
python scripts/predict.py --city "New Delhi" --locality "Connaught Place" --cuisines "North Indian, Chinese" --price-range 2 --cost 600 --delivery yes --booking no
```

**Expected:** `PREDICTED POPULARITY:` followed by High / Medium / Low and the three probabilities.

**What-if app (in your browser):**

```bash
streamlit run scripts/app.py
```

Your browser opens the app (or open the `Local URL` it prints, usually <http://localhost:8501>). Tabs
**Predict** and **Recommend**. Stop it with **Ctrl + C** in Terminal. If Streamlit asks for an email address
the first time, just press Return.

**Tests:**

```bash
python -m pytest -q
```

---

## 7. Tableau dashboards

1. Install **Tableau Desktop Public Edition** (free) from <https://www.tableau.com/products/public/download>
   (sign up with an email address; choose the Mac version).
2. In Finder, open `dashboards/tableau/` and double-click **`RestaurantIntelligence.twbx`**.
   Open the **`.twbx`** (packaged: it contains its own data), **not** the `.twb` (that one points to data
   files on the Windows computer where it was made).
3. The dashboards are tabs at the bottom: Location intelligence, Cuisine and pricing, India deep dive,
   Success prediction, Insights and recommendations.

---

## 8. Power BI (Windows only)

Power BI Desktop does not exist for macOS, so the `.pbix` / `.pbip` files cannot be opened on a Mac. Use:
- the PDF export `dashboards/powerbi/exports/RestaurantIntelligence.pdf` (open in Preview), and
- the page images (PNG) in `dashboards/powerbi/exports/`;
- or, if you received a Power BI Service link, open it in Safari or Chrome.

---

## 9. Troubleshooting

| What you see | What to do |
|---|---|
| `Python 3.12 or 3.13 was not found` | Install Python 3.13 (step 1), close and reopen Terminal, run `bash scripts/setup_mac.sh` again. |
| `command not found: python` | You forgot `source .venv/bin/activate` (step 4). Outside the environment, macOS only knows `python3`. |
| `No such file or directory: scripts/setup_mac.sh` | You are not in the project folder. Run `cd ~/Documents/restaurant-intelligence` (step 2). |
| `xcrun: error: invalid active developer path` or a compiler error during setup | Run `xcode-select --install`, click Install, then run the setup script again. |
| Pip says it cannot find a version of a package | Check `python3 --version` is 3.12 or 3.13. Then run `python -m pip install --upgrade pip` and the setup again. |
| `MySQL is not available, so the pipeline continues WITHOUT MySQL` | Fine if you skipped step 5. Otherwise start MySQL (System Settings > MySQL) and check the password in `.env`. |
| `Access denied for user 'ri_app'` | The password in `.env` differs from the one in `sql/00_create_database_and_user.sql`. Make them equal and run the SQL file again. |
| `command not found: mysql` | Do step 5.5 (PATH), then open a new Terminal window. |
| `zsh: permission denied: scripts/setup_mac.sh` | Start it with `bash` in front: `bash scripts/setup_mac.sh`. |
| "... cannot be opened because the developer cannot be verified" (an installer) | Right-click the file > **Open** > **Open**. |
| `Address already in use` when starting the app | The app is already running in another window. Close it, or run `streamlit run scripts/app.py --server.port 8502`. |
| Tableau says it cannot find a data file | You opened the `.twb`. Open the `.twbx` instead (step 7). |
| The Excel workbook shows formulas as text or `#NAME?` | Open it in Microsoft Excel for Mac (Numbers supports most but not all formulas). |
