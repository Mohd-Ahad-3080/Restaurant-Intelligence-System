# Power BI Guide: Restaurant Intelligence Dashboard

> **Current approach (2026-11-09): the dashboard is GENERATED as a Power BI Project (PBIP).**
> Claude's script `src/powerbi_pbip.py` writes the measures, theme, pages and visuals into
> `RestaurantIntelligence.pbip`. You do **not** need Parts A and B below: they are kept only as a
> reference for what each visual should look like. Your manual work is limited to the section
> **"PBIP: what to do"** directly below.

## PBIP: what to do

**Rule:** keep Power BI Desktop **closed** whenever Claude regenerates the project, and do not edit the
generated visuals' JSON files by hand.

### 1. Open the project
1. Double-click `dashboards/powerbi/RestaurantIntelligence.pbip`.
2. If a yellow bar says the data needs refreshing or relationships changed, click **Refresh** (ribbon
   **Home → Refresh**). This reloads `powerbi_data.xlsx`.
3. Every page has the same slate header with 4 tabs (Ctrl + click a tab to switch pages while editing),
   4 slicers and the Reset button, then a row of 5 KPI cards, a tall row and a short row:

| Page | KPI cards | Tall row | Short row |
|---|---|---|---|
| 1 Overview | Restaurants, Cities, Avg rating, Total votes, Online delivery | Top 10 cuisines · Restaurants by country (top 10) | Rating distribution · Price range mix · Table booking and online delivery |
| 2 Customers and market | Rated restaurants, Not rated, Avg votes, Table booking, Avg price range | Votes vs rating scatter (log votes) · Avg rating by price range | Avg rating with/without online delivery · Table booking vs price range |
| 3 Location intelligence | Restaurants, Cities, Localities, Avg rating, Avg price range | Area competition (10 most crowded localities) · Top localities table | Price level vs rating by city (bubbles) · Avg rating by zone |
| 4 Success prediction | Best model, Test accuracy, Macro F1, ROC-AUC, Baseline accuracy | Feature importance (top 10) · Predicted vs actual matrix | Model comparison table · Predicted class split |

Page 4 note: the model metrics, the confusion matrix and the feature importance are fixed test-set results
from Phase 3, so the slicers do not change them. Only "Predicted class split" follows the slicers.

### 2. No manual steps
Everything is generated. The map was dropped because it did not work in your Power BI, and the
"Restaurants by country (top 10)" bar chart replaces it.

### 3. Check the numbers
With no slicer selected the Page 1 cards must show **9,551 · 141 · 3.44 · 1,498,645 · 25.7%**.
With Country = India: **8,652 · 43 · 3.35 · 1,187,163 · 28.0%**. Page 4: Gradient Boosting, accuracy
**61.3%**, macro F1 **0.611**, ROC-AUC **0.795**, baseline **33.6%**; the confusion matrix totals **1,481**
(more in `expected_values.md`). Test the Reset button with **Ctrl + click**.

### 4. Export for the report (PDF, then PNGs)
1. Open `RestaurantIntelligence.pbip`. If asked, click **Refresh**.
2. Go to the **Overview** page and **Ctrl + click Reset**, so no slicer is selected. Click an empty spot of the
   canvas, so no bar is selected either. Check that the cards show 9,551 · 141 · 3.44 · 1,498,645 · 25.7%.
   Slicers are shared across pages, but check Pages 2–4 too: no slicer selected, no bar highlighted.
3. **File → Export → Export to PDF**. Power BI exports every page of the report, in tab order, as it
   currently looks.
4. Wait for the PDF to open in your PDF viewer. Check that it has 4 pages, then save it as
   `dashboards/powerbi/exports/RestaurantIntelligence.pdf`. Create the `exports` folder if needed. If Power BI
   saved it automatically to Documents or Downloads, move it there.
5. Close Power BI without saving changes (nothing needs saving), then tell Claude. Claude runs
   `python scripts/export_dashboard_pngs.py`, which writes `page1_overview.png`, `page2_customers_market.png`,
   `page3_location.png`, `page4_india.png`, `page5_prediction.png` and `page6_insights.png` (6 pages, tab order) into the same folder.

### 5. Tell Claude
Which pages look right and anything that looks wrong (a screenshot via **Win + Shift + S** helps). Close
Power BI before Claude regenerates anything.

---

# Reference: manual build steps (not needed with PBIP)

Written for a first-time Power BI user. Do the steps in order. Each step says **where to click**.
If anything looks different on your screen, stop and tell Claude what you see.

Files in this folder:

| File | What it is |
|---|---|
| `powerbi_data.xlsx` | All data for the dashboard (9 sheets = 9 tables) |
| `theme_b_slate_red.json` | Colour theme (Theme B): one-click import |
| `dax_measures.md` | The formulas (measures) to paste |
| `expected_values.md` | Numbers your dashboard should show; use them to check your work |

Save your work as **`dashboards/powerbi/restaurant_intelligence.pbix`** (this folder) and press
**Ctrl + S** often.

---

## PART A: One-time setup (about 20 minutes)

### A1. Open Power BI and set the page
1. Open **Power BI Desktop**. Close the start-up window (X at top-right).
2. Click an empty spot on the white canvas. In the **Visualizations** pane (right side), click the
   **paint-brush icon** ("Format your report page").
3. Open **Canvas settings** → **Type**: choose **16:9**. Width should read **1280**, height **720**.
4. Ribbon **View** → tick **Gridlines** and **Snap to grid**.
5. At the bottom, right-click the tab **Page 1** → **Rename page** → type **Overview** → Enter.

### A2. Import the colour theme
1. Ribbon **View** → in the **Themes** group click the small **down-arrow** → **Browse for themes**.
2. Select `theme_b_slate_red.json` → **Open**. A message says the theme was imported. Click **Got it**.
3. The canvas background turns light grey (#F4F4F5). That means it worked.
   *If you get an error, copy its text and send it to Claude.*

### A3. Load the data (one step for all tables)
1. Ribbon **Home** → **Excel workbook** → select `powerbi_data.xlsx` → **Open**.
2. The **Navigator** window lists 9 sheets. **Tick all 9 boxes**:
   restaurants, restaurant_cuisines, model_comparison, model_metrics_long, confusion_matrix,
   feature_importance, predictions, robustness_checks, popularity_classes.
3. Click **Load** (not "Transform Data"). Wait until loading finishes.
4. The **Data** pane (far right) now shows the 9 tables.

### A4. Check the relationships (how tables connect)
1. Click the **Model view** icon on the far-left bar (third icon, looks like three connected boxes).
2. You should see a line between **restaurants** and **restaurant_cuisines**, and one between
   **restaurants** and **predictions** (both on `restaurant_id`).
   - If a line is missing: drag `restaurant_id` from **restaurants** onto `restaurant_id` in the other table.
3. **Delete any other lines** (e.g. lines between the model tables, or to `popularity_classes`):
   click the line → press **Delete** → **Yes**.
4. Double-click the line **restaurants – restaurant_cuisines**. Set:
   - Cardinality: **One to many (1:\*)** (restaurants is the "one" side)
   - Cross filter direction: **Both** → **OK**.
   *(This lets the Cuisine slicer filter the restaurant counts.)*
5. Double-click the line **restaurants – predictions**. Cardinality: **One to one (1:1)**,
   cross filter direction: **Both** → **OK**.

### A5. Prepare three columns (sorting and map)
Click the **Table view** icon on the far-left bar (second icon, looks like a grid).
1. In the **Data** pane click table **restaurants**, then click the column header **price_label**.
   Ribbon **Column tools** → **Sort by column** → choose **price_range**.
2. Click column **rating_text** → **Sort by column** → **rating_band_order**.
3. Click column **popularity_class** → **Sort by column** → **popularity_order**.
4. Click column **country** → **Column tools** → **Data category** → **Country/Region**.
5. Click column **aggregate_rating**: check **Data type** says **Decimal number**. Empty cells are
   unrated restaurants; that is correct.

### A6. Add the measures (formulas)
Open `dax_measures.md`. For **measures 1 to 12** (table `restaurants`) follow the "How to add a measure"
steps at the top of that file. Measures 13 to 21 are for Page 4; add them now too, so they are ready.

Check: in the **Data** pane, under **restaurants**, you now see entries with a **calculator icon**
(Restaurants, Cities, Avg Rating, ...).

Back to the canvas: click the **Report view** icon (first icon on the far-left bar).

---

## PART B: Page 1 "Overview"

### The layout (1280 × 720 pixels)

```
y=0    ┌──────────────────────── HEADER (slate #1F2329) ─────────────── page tabs ┐ h=56
y=64   │ [Country ▾]   [City ▾]   [Price range ▾]   [Cuisine ▾]          [Reset]  │ h=52  slicer bar
y=124  │ [Restaurants] [Cities] [Avg Rating] [Total Votes] [Online Delivery %]    │ h=84  5 KPI cards
y=216  │ Top 10 cuisines  │ Restaurants by country (map) │ Rating distribution   │ h=244 3 × 4 columns
y=468  │ Price range mix                │ Table booking & online delivery          │ h=236 2 × 6 columns
y=704  └───────────────────────────────────────────────────────────────────────────┘
```
12-column grid: margins 16 px, gaps 12 px, column width 93 px.
4 columns = 408 px wide; 6 columns = 618 px wide.

**How to place anything exactly:** select the item → **Format** pane (paint brush) → **General** →
**Properties** → **Size**: Height, Width and **Position**: Horizontal (X), Vertical (Y). Type the numbers.

### B1. Header bar
1. Ribbon **Insert** → **Shapes** → **Rectangle**.
2. Format → **Shape** → **Style**: **Fill** color **#1F2329** (click the colour box → **More colors** →
   type the hex). **Border**: Off. **Rounded corners**: 0. In **General → Effects** turn **Background** off
   and **Visual border** off.
3. Size and position: X **0**, Y **0**, Width **1280**, Height **56**.
4. Ribbon **Insert** → **Text box**. Type **Restaurant Intelligence**. Select the text: font
   **Segoe UI Semibold**, size **16**, colour **#FFFFFF**.
   Press Enter and type a second line: **Zomato restaurants data (Kaggle, CC0) · Overview**; select
   it, size **9**, colour **#FFFFFF**.
   Format → **Effects**: Background **Off**, Visual border **Off**. Position X **24**, Y **4**, Width **520**, Height **50**.

### B2. Page tabs (in the header)
1. Ribbon **Insert** → **Buttons** → **Navigator** → **Page navigator**.
2. Position X **820**, Y **12**, Width **440**, Height **32**.
3. Format → **Button** → **Style** → at the top choose **Apply settings to: State = Default**:
   - **Fill**: **#1F2329**, **Text**: font colour **#FFFFFF**, **Border**: Off.
4. Change **State** to **Selected**: Fill **#E23744**, Text colour **#FFFFFF**.
5. Change **State** to **On hover**: Fill **#8E1520**, Text colour **#FFFFFF**.
6. For now it shows one tab ("Overview"). New pages appear here automatically later.
   *(In Power BI Desktop, hold **Ctrl** while clicking a button to use it.)*

### B3. Slicer bar (filters)
1. Click an empty spot on the canvas. In **Visualizations** click the **Slicer** icon.
2. From the Data pane drag **restaurants → country** into the slicer's **Field** box.
3. Format → **Slicer settings** → **Options** → **Style**: **Dropdown**.
   **Slicer header**: On, text **Country**.
4. Position X **24**, Y **68**, Width **270**, Height **44**.
5. Copy and paste the slicer (Ctrl+C, Ctrl+V) three times and change each one:

| Slicer | Field (replace the field) | Header text | X | Y | Width | Height |
|---|---|---|---|---|---|---|
| City | restaurants → city | City | 306 | 68 | 270 | 44 |
| Price range | restaurants → price_label | Price range | 588 | 68 | 270 | 44 |
| Cuisine | **restaurant_cuisines** → cuisine | Cuisine | 870 | 68 | 270 | 44 |

6. Reset button: **Insert** → **Buttons** → **Clear all slicers**. Format → **Button** → **Text**:
   On, text **Reset**, font colour **#FFFFFF**. **Fill**: **#CB202D**. Position X **1152**, Y **72**, Width **104**, Height **36**.

### B4. Five KPI cards
1. Click an empty spot. **Visualizations** → **Card**.
2. Drag the measure **Restaurants** into the card's field box.
3. Format → **Callout value** → **Display units**: **None**. (Otherwise 1,498,645 shows as "1.5M".)
   Keep the **Category label** On (it shows the measure name under the number).
4. Position X **16**, Y **124**, Width **240**, Height **84**.
5. Copy and paste the card four times; in each copy remove the measure and drag in the new one:

| Card | Measure | X |
|---|---|---|
| 1 | Restaurants | 16 |
| 2 | Cities | 268 |
| 3 | Avg Rating | 520 |
| 4 | Total Votes | 772 |
| 5 | Online Delivery % | 1024 |

All cards: Y **124**, Width **240**, Height **84**.

6. Red accent strip on each card (optional, matches the mockup): **Insert** → **Shapes** →
   **Rectangle**, Fill **#CB202D**, Border Off, Rounded corners 0, Background Off; Width **240**, Height **4**, Y **124**,
   X = the card's X. Copy it for the other four cards.

### B5. Top 10 cuisines (row 1, left)
1. Click an empty spot. **Visualizations** → **Clustered bar chart** (horizontal bars).
2. **Y-axis**: restaurant_cuisines → **cuisine**. **X-axis**: measure **Cuisine Restaurants**.
3. Show only the top 10: open the **Filters** pane (between canvas and Visualizations). Under
   **Filters on this visual**, expand **cuisine** → **Filter type**: **Top N** → **Show items**: Top **10** →
   drag **Cuisine Restaurants** into **By value** → **Apply filter**.
4. Format → **Bars** → Color **#CB202D**. **Data labels**: On. **X-axis**: Off. **Y-axis title**: Off.
5. **Title** text: **Top 10 cuisines (restaurants offering each)**.
6. Position X **16**, Y **216**, Width **408**, Height **244**.

### B6. Restaurants by country map (row 1, middle)
1. **Visualizations** → **Azure Map** (globe icon).
   *If Power BI says map visuals are disabled: **File → Options and settings → Options → Security** →
   tick **Use Azure Map visual** (or "Use Map and Filled Map visuals") → OK, then try again.*
2. **Location**: restaurants → **country**. **Bubble size**: measure **Restaurants**.
3. Format → **Bubble layer** → **Fill color** **#CB202D**.
4. **Title**: **Restaurants by country (bubble size = number of restaurants)**.
5. Position X **436**, Y **216**, Width **408**, Height **244**.
   *India's bubble dominates because 90.6% of restaurants are in India; this is real, not an error.*
   *If no map visual works at all, tell Claude. A bar chart of restaurants by country is the fallback.*

### B7. Rating distribution (row 1, right)
1. **Visualizations** → **Clustered column chart**.
2. **X-axis**: restaurants → **rating_text**. **Y-axis**: measure **Restaurants**.
3. Sort: click **… (More options)** at the top-right of the chart → **Sort axis** → **rating_text**, then
   **… → Sort axis → Sort ascending**. Order: Not rated, Poor, Average, Good, Very Good, Excellent.
4. Colours: Format → **Columns** → **Color** → click **fx** → **Format style**: **Field value** →
   **What field should we base this on?**: **rating_bar_color**, summarisation **First** → **OK**.
   (Rated bands turn red, "Not rated" turns grey.)
5. **Data labels**: On. **Y-axis**: Off. Title: **Rating distribution (Not rated in grey)**.
6. Position X **856**, Y **216**, Width **408**, Height **244**.

### B8. Price range mix (row 2, left)
1. **Visualizations** → **Clustered column chart**.
2. **X-axis**: restaurants → **price_label**. **Y-axis**: measure **Restaurants**.
3. **… → Sort axis → price_label**, then **Sort ascending** (1 Budget → 4 Luxury).
4. Colours: Format → **Columns** → **Color** → **fx** → **Field value** → **price_color**, **First** → OK.
   This gives the approved sequence #8E1520, #CB202D, #E8838B, #F5C6CA.
5. **Data labels**: On (important: price ranges 1 and 2 have similar reds, so the labels on the axis
   and bars do the identifying). **Y-axis**: Off.
6. Title: **Price range mix (1 = Budget, 4 = Luxury)**.
7. Position X **16**, Y **468**, Width **618**, Height **236**.

### B9. Table booking and online delivery (row 2, right)
1. **Visualizations** → **Clustered bar chart**.
2. Drag **both** measures **Table Booking %** and **Online Delivery %** into **X-axis**. Leave Y-axis empty.
3. Format → **Bars** → **Colors**: Table Booking % **#8E1520**, Online Delivery % **#CB202D**.
4. **X-axis** → **Range** → **Maximum**: **1** (= 100%). **Data labels**: On. **Legend**: On, position **Bottom**.
5. Title: **Share of restaurants offering table booking and online delivery**.
6. Position X **646**, Y **468**, Width **618**, Height **236**.

### B10. Check your numbers
With **no slicer selected**, the cards must show:

| Restaurants | Cities | Avg Rating | Total Votes | Online Delivery % |
|---|---|---|---|---|
| 9,551 | 141 | 3.44 | 1,498,645 | 25.7% |

Then pick **Country = India** in the slicer: 8,652 · 43 · 3.35 · 1,187,163 · 28.0%.
Click **Reset** (Ctrl + click) to clear. More check values: `expected_values.md`.

### B11. Save
**File → Save as** → this folder → `restaurant_intelligence.pbix`.

**Stop here.** Tell Claude: (1) whether the numbers matched, (2) anything that looked different
from these steps, and if possible (3) a screenshot of the page (Windows: **Win + Shift + S**).
Pages 2–4 follow after that.
