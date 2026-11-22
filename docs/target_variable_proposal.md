# Target Variable Proposal: Popularity Class (High / Medium / Low)

**Status: APPROVED: Option B (Anser, 2026-11-09).** See decision record in section 6.

*Figures in sections 1–4 were computed from the Kaggle file by `src/target_options.py`. The approved rule
is implemented in `src/target.py`.*

All figures below were produced by `src/target_options.py` on the real dataset (9,551 rows).

## 1. Facts from the data that shape the choice

| Fact | Value |
|---|---|
| Rated restaurants | 7,403 |
| "Not rated" restaurants (rating stored as 0) | 2,148 |
| Votes of "Not rated" restaurants | 0 to 3 |
| Minimum votes of rated restaurants | 4 |
| Votes among rated: median / mean / max | 60 / 202.2 / 10,934 (heavily skewed) |
| Correlation of log(1+votes) with rating (rated only) | 0.649 |
| Share of rated restaurants that are in India | 6,513 of 7,403 (88.0%) |

**Implication:** Zomato publishes a rating only after 4+ votes. Whether a restaurant is "rated"
is therefore a function of votes, so `is_rated` / `rating_text = "Not rated"` would leak any
votes-based target.

"Success" in this project means **popularity on Zomato**, not revenue or profit (the dataset has no
financial data).

## 2. Options

### Option A: Global tertiles of log(1 + votes), rated restaurants only
- Low ≤ 27 votes, Medium 28–124, High > 124 (cut-offs on the rated set).
- Classes: Low 2,474 · Medium 2,471 · High 2,458 (balanced).
- **Problem:** popularity is mostly decided by country. % High by country: Indonesia 95.2%,
  UAE 91.7%, Philippines 86.4%, US 76.1%, India 28.7%, Brazil 0.0%, Singapore 0.0%.
  The non-India rows look like a hand-picked sample of well-known places, so the model would mostly
  learn "which country" rather than "what makes a restaurant popular".

### Option B (RECOMMENDED): Within-country tertiles of votes, rated restaurants only
- Each restaurant's votes are ranked against restaurants **in the same country** (percentile rank),
  then split into thirds.
- Classes: Low 2,482 · Medium 2,446 · High 2,475 (balanced).
- % High is about one third in every country (30.0%–36.4%; Canada 50% with only 4 rows).
- Meaning: "popular *relative to its own market*". This removes the country sampling bias and is
  easy to explain in the viva.
- Ranking on raw votes vs log(votes) gives identical classes (rank is unchanged by log).

### Option C: Tertiles of a Bayesian weighted rating (rating and votes combined)
- Score = v/(v+m)·R + m/(v+m)·C, with m = 60 (median votes), C = 3.440 (mean rating).
- Classes: Low 2,479 · Medium 2,456 · High 2,468.
- Measures "well-liked *and* well-known", which is closer to the everyday idea of success, but it
  forbids **both** rating and votes as features and is harder to explain.

## 3. Leakage impact (same for all three options)

Because every option is built from `votes` and/or `aggregate_rating`, the following are **forbidden
as features**:

| Forbidden feature | Reason |
|---|---|
| `votes` | Target is built from it (A, B, C) |
| `aggregate_rating` | Part of target in C; in A/B it is outcome feedback from the same users and correlates 0.649 with log votes |
| `rating_text`, `rating_color` | Derived directly from `aggregate_rating` |
| `is_rated` / "Not rated" flag | Determined by votes (rated ⇔ votes ≥ 4) |
| Any locality/city/cuisine average of votes or rating | Encodes the target of neighbouring rows (target leakage) |

**Features that remain allowed:**

| Feature | Notes |
|---|---|
| `country`, `city` | City has 141 values; group rare cities into "Other" |
| `price_range` (1–4) | Comparable across countries |
| Cost for two as a **within-country percentile** | Raw cost is in local currency |
| `has_table_booking`, `has_online_delivery` | 1/0 |
| `is_delivering_now` | Snapshot flag; weak but legitimate |
| Cuisines as multi-hot columns (top ~20 + "Other") and number of cuisines | From exploded cuisine table |
| Branch count (rows with the same restaurant name) | Chain indicator; not built from votes |
| Locality competition (number of restaurants in the same locality) | Count of rows, not of votes |
| Latitude/longitude (valid rows only) | 499 rows have missing (0) coordinates |

**Expectation:** with these honest features the model will likely score well below the planned ~84%
accuracy. A random guess on three balanced classes is about 33%. Whatever the honest model achieves
will be reported.

## 4. Scope decision: unrated restaurants

The recommended approach **excludes the 2,148 unrated restaurants** from training, because they are
"Low" by definition (0–3 votes) and would make the task artificially easy. Alternative: keep them all
as "Low" (A on all rows gives cut-offs 10 / 82 votes, classes Low 3,223 · Medium 3,148 · High 3,180).

## 5. Recommendation

**Option B: within-country tertiles of votes, rated restaurants only (n = 7,403)**, with all features
in the "forbidden" table excluded.

## 6. Decision record

| Item | Decision |
|---|---|
| Target option | **Option B**: within-country percentile rank of votes, cut into thirds (Low / Medium / High) |
| Include unrated restaurants? | **Excluded from model training.** Their actual `popularity_class` is left blank. |
| Philippines currency | Relabel "Botswana Pula(P)" → "Philippine Peso(P)" for Philippines rows (approved) |
| Approved by / date | Anser, 2026-11-09 |
| Implemented in | `src/target.py` (column `popularity_class` in `zomato_clean.csv`) |
