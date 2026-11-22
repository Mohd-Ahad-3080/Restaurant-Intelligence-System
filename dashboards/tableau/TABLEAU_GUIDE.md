# Tableau Guide: Restaurant Intelligence (Tableau Public 2026.3)

The workbook is **generated** by `src/tableau_twb.py` as `RestaurantIntelligence.twb`. The format is copied
from `starter_extract.twb` (with an extract and a dashboard), the file Tableau Public itself wrote. Keep Tableau **closed** whenever Claude
regenerates the workbook.

## Data the workbook reads (local CSVs)
- `data/processed/zomato_clean.csv`: one row per restaurant.
- `data/processed/restaurant_cuisines_city.csv`: one row per restaurant–cuisine pair, with country, city,
  price range and rating.
  It is written by the generator and contains no aggregation.

## Open and check the dashboards
1. Double-click `dashboards/tableau/RestaurantIntelligence.twb` (or open it with **File → Open**).
2. If Tableau asks where a CSV is, point it to the file in `data/processed/`. If it offers to create or
   refresh an extract, accept: Tableau Public works from extracts.
3. Open the **Location intelligence** and **Cuisine and pricing** tabs at the bottom and compare them with
   `expected_values.md`.
4. Report anything that looks wrong (a screenshot helps), then close Tableau **without saving**, so Claude
   can regenerate the file.

## Saving the deliverable (after all dashboards are approved)
**File → Save As → Tableau Packaged Workbook (*.twbx)**. The packaged file includes the data, so it also
opens on the client's Mac. Publishing to the Tableau Public website is optional; it makes the workbook and
data public (the dataset is CC0).
