# DAX Measures

How to add a measure (done once per measure):
1. In the **Data** pane on the right, click the table named in the heading (e.g. `restaurants`).
2. Ribbon: **Home → New measure**. A formula bar appears above the canvas.
3. Delete what is there, paste the whole line below (name = formula), press **Enter**.
4. With the measure still selected, set its format in the **Measure tools** ribbon as listed.

All measures read the real data; no number is typed in.

## Table `restaurants` (Pages 1–3)

| # | Paste this | Format (Measure tools) |
|---|---|---|
| 1 | `Restaurants = COUNTROWS ( restaurants )` | Whole number, thousands separator on |
| 2 | `Cities = DISTINCTCOUNT ( restaurants[city] )` | Whole number |
| 3 | `Avg Rating = AVERAGE ( restaurants[aggregate_rating] )` | Decimal number, 2 decimals |
| 4 | `Total Votes = SUM ( restaurants[votes] )` | Whole number, thousands separator on |
| 5 | `Online Delivery % = DIVIDE ( CALCULATE ( [Restaurants], restaurants[has_online_delivery] = 1 ), [Restaurants] )` | Percentage, 1 decimal |
| 6 | `Table Booking % = DIVIDE ( CALCULATE ( [Restaurants], restaurants[has_table_booking] = 1 ), [Restaurants] )` | Percentage, 1 decimal |
| 7 | `Rated Restaurants = CALCULATE ( [Restaurants], restaurants[is_rated] = 1 )` | Whole number, thousands separator on |
| 8 | `Unrated % = DIVIDE ( [Restaurants] - [Rated Restaurants], [Restaurants] )` | Percentage, 1 decimal |
| 9 | `Avg Votes = AVERAGE ( restaurants[votes] )` | Decimal number, 1 decimal |
| 10 | `Avg Cost for Two (local) = AVERAGE ( restaurants[avg_cost_for_two] )` | Whole number. **Only meaningful when ONE country is selected** (costs are in local currency). |
| 11 | `Cuisine Restaurants = DISTINCTCOUNT ( restaurant_cuisines[restaurant_id] )` | Whole number, thousands separator on |
| 12 | `Avg Price Range = AVERAGE ( restaurants[price_range] )` | Decimal number, 2 decimals |

Helper measures added for the generated PBIP report (already in the model; nothing to paste):

| # | Measure | Purpose |
|---|---|---|
| 22 | `Top 10 Cuisine Restaurants = IF ( RANKX ( ALLSELECTED ( restaurant_cuisines[cuisine] ), [Cuisine Restaurants], , DESC, Skip ) <= 10, [Cuisine Restaurants] )` | Shows only the 10 largest cuisines (others are blank, so the chart hides them) and reacts to slicers |
| 23 | `Price Bar Color = SELECTEDVALUE ( restaurants[price_color], "#5C5C66" )` | Theme B price-range colour per bar |
| 24 | `Rating Bar Color = SELECTEDVALUE ( restaurants[rating_bar_color], "#5C5C66" )` | Red for rating bands, grey for "Not rated" |
| 25 | `Top 10 Country Restaurants = IF ( RANKX ( ALLSELECTED ( restaurants[country] ), [Restaurants], , DESC, Skip ) <= 10, [Restaurants] )` | "Restaurants by country (top 10)" bar chart (replaces the map). `Skip` ranking: Brazil, UAE and South Africa tie at 60, and `Dense` ranking would have shown 14 countries |
| 26 | `Service % = SWITCH ( SELECTEDVALUE ( services[service_order] ), 1, [Table Booking %], 2, [Online Delivery %] )` | Booking/delivery bar chart: one bar per row of the small `services` table ("Table booking", "Online delivery") |

Added for Pages 2–4 (also generated):

| # | Measure | Purpose |
|---|---|---|
| 27 | `Rated Avg Votes = CALCULATE ( AVERAGE ( restaurants[votes] ), restaurants[is_rated] = 1 )` | Y axis of the votes-vs-rating scatter (rated restaurants only) |
| 28 | `Localities = COUNTROWS ( SUMMARIZE ( restaurants, restaurants[city], restaurants[locality] ) )` | Distinct city + locality pairs (same locality name in two cities counts twice) |
| 29 | `Top 10 Locality Restaurants = IF ( RANKX ( ALLSELECTED ( restaurants[locality_city] ), [Restaurants], , DESC, Skip ) <= 10, [Restaurants] )` | "Area competition" chart |
| 30 | `Predicted Class Color = SELECTEDVALUE ( predictions[predicted_color], "#5C5C66" )` | Colour per predicted class |
| 31 | `Importance = SUM ( feature_importance[importance_mean] )` | Permutation importance |
| 32 | `Top 10 Importance = IF ( RANKX ( ALLSELECTED ( feature_importance[feature_label] ), [Importance], , DESC, Skip ) <= 10, [Importance] )` | Feature-importance chart |

| 33 | `Avg Rating (India) = CALCULATE ( [Avg Rating], KEEPFILTERS ( restaurants[country] = "India" ) )` | Page 2 delivery chart. **Official delivery-vs-rating figure: India only, rated restaurants, mean: 3.37 with vs 3.34 without delivery** (delivery exists only in India and UAE; all countries would give a misleading 3.38 vs 3.47) |
| 34 | `Log10 Votes = AVERAGE ( restaurants[log10_votes] )` | Page 2 scatter Y axis (a log axis did not render, so log10 is plotted and labelled) |
| 35–37 | `T10 Locality Avg Rating / Avg Votes / Avg Price Range = IF ( NOT ISBLANK ( [Top 10 Locality Restaurants] ), [Avg Rating] / [Avg Votes] / [Avg Price Range] )` | Page 3 table shows exactly the 10 most crowded localities |
| 38 | `Confusion Cell Color = IF ( HASONEVALUE ( confusion_matrix[actual] ) && HASONEVALUE ( confusion_matrix[predicted] ) && MAX ( confusion_matrix[is_correct] ) = 1, "#F5C6CA", "#FFFFFF" )` | Page 4 matrix: light red on the diagonal (correct predictions) |

Calculated column `restaurants[log10_votes] = IF ( restaurants[is_rated] = 1 && restaurants[votes] > 0, LOG10 ( restaurants[votes] ) )`
(rated restaurants have 4 to 10,934 votes, so log10 runs from 0.60 to 4.04).

Calculated column `restaurants[locality_city] = restaurants[locality] & " (" & restaurants[city] & ")"`:
Malviya Nagar and Krishna Nagar each exist in two cities, so a locality name alone would merge them.

The `services` table is a 2-row calculated table (labels only, written by `src/powerbi_pbip.py`); the
percentages themselves come from the real data through measures 5 and 6.

With the PBIP approach all measures are written into the model by `src/powerbi_pbip.py`
(single source of truth: the `MEASURES` list in that file).

Notes
- `Avg Rating` automatically uses rated restaurants only: unrated restaurants have a blank rating, and
  AVERAGE ignores blanks.
- `Cuisine Restaurants` counts restaurants offering a cuisine (one restaurant can offer several).

## Table `model_comparison` (Page 4)

| # | Paste this | Format |
|---|---|---|
| 13 | `Best Model = CALCULATE ( SELECTEDVALUE ( model_comparison[model] ), model_comparison[is_best] = 1 )` | Text |
| 14 | `Best Accuracy = CALCULATE ( MAX ( model_comparison[test_accuracy] ), model_comparison[is_best] = 1 )` | Percentage, 1 decimal |
| 15 | `Best Macro F1 = CALCULATE ( MAX ( model_comparison[test_f1_macro] ), model_comparison[is_best] = 1 )` | Decimal number, 3 decimals |
| 16 | `Best ROC AUC = CALCULATE ( MAX ( model_comparison[test_roc_auc_ovr_macro] ), model_comparison[is_best] = 1 )` | Decimal number, 3 decimals |
| 17 | `Baseline Accuracy = CALCULATE ( MAX ( model_comparison[test_accuracy] ), model_comparison[model] = "Baseline (majority class)" )` | Percentage, 1 decimal |

## Table `predictions` (Page 4)

| # | Paste this | Format |
|---|---|---|
| 18 | `Predicted Restaurants = COUNTROWS ( predictions )` | Whole number, thousands separator on |
| 19 | `Prediction Agreement % = AVERAGE ( predictions[correct] )` | Percentage, 1 decimal |

## Table `confusion_matrix` (Page 4)

| # | Paste this | Format |
|---|---|---|
| 20 | `Confusion Count = SUM ( confusion_matrix[count] )` | Whole number |
| 21 | `Confusion % of Actual = SUM ( confusion_matrix[pct_of_actual] )` | Percentage, 0 decimals |
