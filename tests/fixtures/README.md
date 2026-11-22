# Test fixtures: SYNTHETIC DATA, NOT RESEARCH DATA

Files here are **made up by hand for automated tests only**. They are never used in the report,
dashboards or any analysis results.

## `SYNTHETIC_sample_zomato.csv`

16 rows in the Zomato column format. Every restaurant name starts with `TEST Synthetic`. The rows
contain deliberate problems so the tests can confirm each cleaning rule works:

| Row ID | Deliberate problem | Expected cleaning result |
|---|---|---|
| 900002 (2nd copy) | Exact duplicate row | Dropped |
| 900001 (2nd copy, "15 duplicate ID") | Duplicate Restaurant ID | Dropped (first kept) |
| 900004 | Coordinates (0, 0); rating 0 "Not rated"; lowercase `yes` | Coords → missing; rating → missing, `is_rated` = 0, no popularity class; `yes` → 1 |
| 900005 | Cost for two = 0 | Cost → missing |
| 900006 | Cuisines empty | `Unknown`; not in the cuisine pairs table |
| 900011, 900012 | Philippines (code 162) with "Botswana Pula(P)" | Currency → "Philippine Peso(P)"; country → "Philippines" |
| 900013 | Country code 999 not in the lookup | Country → "Unknown" |
| 900014 | Extra spaces in name and cuisines; "Not rated" | Spaces trimmed; rating → missing |

Expected clean row count: **14** (16 − 1 exact duplicate − 1 duplicate ID).

## `SYNTHETIC_same_city_two_currencies.csv`

4 rows in the *cleaned* column format. A made-up city "Springfield" exists in two countries with
two currencies (Pounds and Dollars). Used only to test that the recommendation engine refuses to
mix currencies in one budget comparison and asks for the country instead.

## `SYNTHETIC_votes_classes.csv`

6 made-up rows (country "Testland", votes 1-6, two per class). Used only to unit-test the class cut-off
and distance-to-cut-off calculations in `src/model_medium.py` (cut-offs must be 2.5 and 4.5 votes).
