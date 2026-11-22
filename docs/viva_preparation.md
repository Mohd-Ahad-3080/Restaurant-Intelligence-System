# Viva Preparation: 15 Likely Questions with Model Answers

The viva has **5 descriptive questions × 6 marks = 30 marks**. Below are the 15 questions most likely to be
asked about this project, each with an answer of 150–200 words. Every number comes from the project
outputs (`docs/model_results.md`, `docs/eda_findings.md`, `docs/sql_results.md`). Learn the ideas and
key numbers; don't memorise the wording.

**Key numbers to remember:** 9,551 restaurants · 15 countries · 141 cities · 7,403 rated · 2,148 unrated ·
mean rating 3.44 · 28 SQL queries · 34 features · Gradient Boosting 61.3% accuracy, macro-F1 0.611,
ROC-AUC 0.795 · baseline 33.6% · leaky model (invalid) 98.8% · no location features 51.9% · India only
62.5% (57.2% without location) · High vs Low only 83.2% (a separate question) · 6 Power BI pages ·
5 Tableau dashboards · 169 automated tests.

**Target definition (say it exactly):** popularity class = within-country tertiles (thirds) of votes among
rated restaurants (Low / Medium / High). Votes, aggregate rating, rating text, rating colour and the rated
flag are excluded as features because the target is built from votes.

---

### Q1. What is the aim of your project, and what does "success" mean in it?

The aim is to show how public restaurant listings can support two groups. Diners get ranked recommendations
whose scores are explained. Owners and analysts get evidence on which attributes go with popularity, plus a
model that predicts a restaurant's popularity class. The data come from the Zomato Restaurants Data set on
Kaggle: 9,551 restaurants in 15 countries and 141 cities, published under a CC0 public-domain licence. This
is secondary data only; no surveys or interviews were used. The data set has no revenue, profit or footfall
columns, so I could not measure financial success honestly. Instead, success is defined as **popularity on
Zomato**, measured by votes. Specifically, each rated restaurant is placed in the Low, Medium or High third
of votes within its own country. This matters because it keeps the claims honest. The report never says a
restaurant earns more; it only says that certain attributes are associated with more votes and better
ratings. The objectives were to:
- clean and document the data;
- build a MySQL database with analytical queries;
- test associations statistically;
- build a recommender and a leakage-free prediction model, and test how much it depends on location;
- look closely at India, where 90.6% of the restaurants are;
- present the results in Power BI and Tableau dashboards and a small what-if app.

### Q2. Why did you choose this dataset, and what are its main characteristics?

The data set is public, free and legally reusable (CC0). It is large enough for machine learning and rich in
business attributes: city, locality, coordinates, cuisines, cost for two, price range (1–4), table booking,
online delivery, rating and votes.

Profile, verified in Python:
- 9,551 rows and 21 columns;
- 8,652 restaurants (90.6%) are in India;
- New Delhi, Gurgaon, Noida and Faridabad alone hold 82.9% of all records;
- 7,403 restaurants are rated and 2,148 are "Not rated";
- the mean rating of rated restaurants is 3.44;
- there are 145 individual cuisines in 1,821 distinct combinations.

Several traits needed care:
- the file is not UTF-8, so a Latin-1 fallback is used;
- costs are in local currencies, so they cannot be compared across countries (I use price range 1–4, the
  cost percentile within the country, or an approximate US-dollar cost from the World Bank's 2017 official
  exchange rates, matched by country);
- a rating of 0 actually means "not rated";
- there is no date column, so no trend analysis is possible.

These traits shaped the methods. Price range replaces cost for cross-country comparisons, and unrated
restaurants are treated as missing rather than as zero.

### Q3. Explain how you defined the target variable for the popularity model.

I compared three options, all documented in `target_variable_proposal.md`:
- **Option A (global thirds of votes):** this mostly learned which country a restaurant was in. For
  example, 95.2% of Indonesian rows would be "High" but 0% of Brazilian rows, because the non-Indian rows are
  a small, hand-picked sample.
- **Option C (a Bayesian weighted rating):** this mixed rating and votes and was harder to explain.
- **Option B (chosen):** each rated restaurant's votes are ranked against restaurants in the same country,
  and the ranks are cut into thirds. This gives balanced classes: Low 2,482, Medium 2,446 and High 2,475. It
  means "popular relative to its own market", which removes the country sampling bias.

The 2,148 unrated restaurants are excluded from training. They have 0–3 votes, so they would be "Low" by
definition and would make the task artificially easy. A three-class balanced target also gives a clear
reference point: a random guess is right about one time in three.

### Q4. What is data leakage, and how did you prevent it?

Data leakage means using information about the target that would not be available when a real prediction is
made. Kaufman, Rosset, Perlich and Stitelman (2012) show that it produces high but meaningless accuracy. Here
the target is built from votes, and the rating is produced by the same diners at the same time. The
correlation is strong: Spearman ρ = 0.682 between rating and votes. Using rating to predict popularity would
therefore be predicting votes from votes.

I forbade these features:
- votes and aggregate rating;
- rating text and rating colour (both derived from the rating);
- the "is rated" flag (a restaurant is rated only after 4+ votes);
- any average of votes or rating per city or locality.

A function in the code, `assert_no_leakage`, stops the run if any of them appears, and a test checks it. The
remaining 34 features describe things known before diners vote: location, price, cost percentile in the
country, services, cuisines, chain size and locality size. A deliberate test shows the danger: adding votes
and rating to the same model lifts accuracy from 61.3% to 98.8%, which measures the leak, not skill.

### Q5. Your model has 61.3% accuracy. Why is that acceptable?

A much higher score was easy to get, but only by cheating. I tested it: the same Gradient Boosting model,
given votes and rating as extra inputs, reaches 98.8% accuracy, because the target is built from votes.
Without those inputs, the honest result is:
- Gradient Boosting: 61.3% test accuracy, macro-F1 of 0.611 and one-vs-rest ROC-AUC of 0.795;
- majority-class baseline: 33.6%.

So the model is nearly twice as accurate as guessing. The ROC-AUC of 0.795 also means it ranks restaurants by
likelihood of being popular quite well.

Model variants with the same algorithm and settings support the result:
- **Delhi NCR only**, where sampling is consistent: macro-F1 is 0.614, about the same as the main model.
- **No location features at all**: 51.9% accuracy (macro-F1 0.514), still well above the baseline.
- **India only**: 62.5% with city and locality features, 57.2% without them.
- **High vs Low only** (Medium removed): 83.2% accuracy, ROC-AUC 0.925. This is a different, easier
  question, not the three-class result.

The task is also hard by nature. Popularity depends on food quality, service, marketing and timing, none of
which appear in the data. An honest 61% that holds up for new restaurants, which have no votes yet, is more
useful than an inflated 98.8% that would collapse in real use. Reporting it openly is part of the project's
integrity.

### Q6. Which models did you compare, and why was Gradient Boosting chosen?

I compared four classifiers and a majority-class baseline, all from scikit-learn:
- **Logistic Regression:** a linear benchmark;
- **Decision Tree:** easy to interpret;
- **Random Forest:** many randomised trees averaged together (Breiman, 2001);
- **Gradient Boosting:** shallow trees added one after another, each correcting the remaining error
  (Friedman, 2001).

The data were split 80/20 with stratification (5,922 training and 1,481 test rows, random state 42). Each
model's hyper-parameters were tuned by five-fold cross-validation on the training set only.

The best model was selected by **cross-validated macro-F1**, not by test score. This avoids choosing a model
because it happened to suit the test set. Gradient Boosting had the highest CV macro-F1 (0.624) and was then
also best on the test set:

| Model | Accuracy | Macro-F1 |
|---|---|---|
| Logistic Regression | 0.550 | 0.543 |
| Decision Tree | 0.567 | 0.561 |
| Random Forest | 0.581 | 0.573 |
| **Gradient Boosting** | **0.613** | **0.611** |

Boosting suits this data because it captures non-linear effects and interactions, for example between
location and price, without heavy feature engineering.

### Q7. Explain the evaluation metrics you used and what the confusion matrix shows.

- **Accuracy:** the share of correct predictions.
- **Precision:** how many restaurants predicted in a class truly belong to it.
- **Recall:** how many of a class's restaurants were found.
- **F1:** combines precision and recall. **Macro-F1** averages the three classes equally; weighted-F1
  weights them by size. The classes are balanced, so the two are almost identical (0.611).
- **ROC-AUC (one-vs-rest):** measures how well the predicted probabilities rank each class above the
  others. 0.5 is random and 1.0 is perfect; the model scores 0.795.

The confusion matrix shows these recalls:
- Low: 66.2%;
- Medium: 47.2%;
- High: 70.3%.

Medium is hardest because it sits between the other two classes, so its errors spill both ways. The extremes
are rarely confused: only 46 Low restaurants were predicted High, and 41 High restaurants were predicted Low.
The model therefore separates clearly unpopular from clearly popular restaurants well. Most mistakes are
"one step" errors, which are less harmful in practice.

Why Medium is weak, with evidence: in India the Medium band covers only 25–99 votes, and accuracy is 44.8%
for restaurants within five percentile points of a class cut-off against 79.3% far from one. I tried three
honest fixes, tuned on the training set only: class weights (cross-validation chose weight 1, so no change),
threshold tuning (Medium recall 0.495 instead of 0.472, but accuracy fell to 60.4%) and an ordinal model
(62.1% on the test set, but lower in cross-validation, 0.619 against 0.624, so I did not adopt it; choosing by
the test score would overfit the test set).

### Q8. Which features mattered most, and is location importance a problem?

Permutation importance measures how much macro-F1 drops when one feature is shuffled. The top features were:
1. latitude;
2. city group;
3. cost percentile within the country;
4. longitude;
5. locality size;
6. online delivery;
7. price range;
8. branch count.

Location dominates, which raised a concern. Outside Delhi NCR, Zomato appears to list mainly well-known
restaurants: 72.1% of rated restaurants in other Indian cities are High, against 28.7% inside NCR. The model
could partly learn where a restaurant was sampled rather than what makes it popular.

I tested this directly:
- **Within Delhi NCR alone**, where sampling is consistent, macro-F1 was 0.614, about the same as the main
  model. So the result is not a sampling artefact.
- **With all location features removed**, accuracy fell to 51.9% (macro-F1 0.514) but stayed far above the
  baseline. Cost percentile, online delivery and price range then lead, so price, services, cuisines and
  chain status carry real signal.
- **India only**: 62.5% with location features and 57.2% without them.

Location is a legitimate input, not leakage. It matches the long-standing view that location is central to
restaurant success.

### Q9. How does your recommendation engine work?

It is a weighted, content-based hybrid, the design Burke (2002) calls a "weighted hybrid":

**Score = 0.40 × rating + 0.25 × popularity + 0.20 × budget suitability + 0.15 × cuisine match**

Each component is scaled from 0 to 1:
- **Rating:** the rating divided by 5.
- **Popularity:** log(1 + votes) divided by the log of the city's highest vote count, so one famous
  restaurant does not swamp the scale.
- **Budget:** 1 within budget, falling to 0 at twice the budget. The budget is always in the city's own
  currency.
- **Cuisine:** the share of requested cuisines the restaurant offers.

City, optional locality, minimum rating and delivery are hard filters. Budget and cuisine are scored, so
near-matches can still appear lower down.

Example (New Delhi): North Indian food, Rs 800 for two, rating at least 3.5, delivery required.
- The filters narrowed 5,473 restaurants to 1,456 and then to 670.
- The top result scored 0.882 = 0.312 (rating) + 0.220 (popularity) + 0.200 (budget) + 0.150 (cuisine).

Showing each component makes every ranking explainable. Collaborative filtering was not possible because the
data contain no user histories.

### Q10. Describe the role of MySQL and SQL in your project.

MySQL 8 is the project's structured store and the source for the statistical analysis.

The schema has three tables:
- countries;
- restaurants;
- restaurant–cuisine pairs: 19,705 rows, one per restaurant and cuisine, which turns the comma-separated
  cuisine text into proper relational data.

Integrity is enforced in the database:
- primary and foreign keys;
- five CHECK constraints (rating 0–5, price range 1–4, votes ≥ 0, cost > 0, and a popularity class only for
  rated restaurants);
- six secondary indexes for speed.

Seven views provide reusable summaries by country, city, locality, cuisine and price.

I wrote 28 analytical queries, each answering one business question, for example how popularity varies by
price range or which localities are most competitive. They use joins, GROUP BY with HAVING, common table
expressions and window functions such as RANK, ROW_NUMBER and running SUM.

Python connects through SQLAlchemy, and the exploratory analysis reads its data back from MySQL. Automated
tests confirm that database totals equal the cleaned files and that the constraints reject bad data.

### Q11. What were the roles of Python, Excel, Power BI and Tableau?

Each tool had a distinct job:
- **Python** (pandas, scikit-learn, matplotlib): loading with the encoding fix, 41 data-quality checks,
  cleaning with a 25-step log, statistical tests, the recommender, the four models and their variants, the
  India and unrated analyses, and the report figures. Pytest runs 169 automated tests.
- **Excel:** an eleven-sheet workbook generated with openpyxl. It holds a raw sample, the data dictionary,
  the quality checks, the cleaning log and summaries by country, city, cuisine and price range. The
  summaries use live COUNTIF, AVERAGEIF and SUMIF formulas, so the workbook is a genuine Excel artefact.
- **Power BI:** a six-page interactive dashboard (overview, customers and market, location, India deep dive,
  success prediction, and insights). It has slicers for country, city, price range and cuisine (locality on
  the India page), and a chart left empty by the slicers says "No data for this selection".
- **Tableau Public:** five dashboards: location intelligence, cuisine and pricing, India deep dive (City and
  Locality drop-downs), success prediction, and insights and recommendations.
- **Streamlit what-if app:** a browser app with a Predict tab (High/Medium/Low with probabilities from the
  saved model) and a Recommend tab (ranked list with the score breakdown). It uses the same code as the
  command-line tools.

Using two BI tools shows the same verified numbers presented consistently on different platforms.

### Q12. What were the main findings of your data analysis?

- **Concentration:** 90.6% of restaurants are in India, and 82.9% are in four Delhi NCR cities.
- **Price and rating:** average rating rises from 3.24 in price range 1 to 3.89 in range 4 (Spearman
  ρ = 0.402, a moderate effect).
- **Price and popularity:** only 13.3% of budget restaurants are High popularity, against 63.2% in range 3.
- **Services:** 77.6% of restaurants offering both table booking and delivery are High popularity, against
  24.5% with neither. In India (rated restaurants), 63.0% of restaurants with table booking are High against
  27.6% without, and booking goes with higher ratings (median 3.6 against 3.3).
- **India deep dive:** New Delhi alone has 5,473 restaurants (mean rating 3.30, 29.2% High). Most other
  Indian cities list only about 20 well-known restaurants, so their high ratings partly reflect sampling.
- **Delivery and rating:** online delivery shows almost no link with rating in India (mean 3.37 against
  3.34; effect size 0.074), although delivery outlets get more votes.
- **Cuisines:** North Indian (41.5%) and Chinese (28.6%) dominate supply but are rated below average.
  Italian, Continental and American rate higher (3.71–3.76), but they are also pricier (average price
  range 2.55–2.78), so price may explain part of it.
- **Chains:** chain outlets are rated slightly lower than single outlets.
- **Competition:** the number of competitors in a locality had no significant link with rating
  (p = 0.126).

All of these are associations, not causes.

### Q13. Why did you use non-parametric statistical tests?

Votes are extremely skewed. Among rated restaurants the median is 60, the mean is 202.2 and the maximum is
10,934, with a skewness of 7.95. Ratings lie on a bounded 0–5 scale and are not normally distributed.
Parametric tests such as the t-test, ANOVA and Pearson correlation assume roughly normal data and are
sensitive to extreme values, so they could give misleading results here.

I therefore used rank-based tests:
- **Spearman correlation** for relationships between two ordered variables;
- **Kruskal–Wallis** to compare ratings across the four price ranges;
- **Mann–Whitney U** for two-group comparisons such as delivery against no delivery;
- **Chi-square tests of independence** for popularity class against price range or services.

Each test is reported with an effect size: ρ, ε², rank-biserial r or Cramér's V. This matters because with
thousands of rows almost everything is "significant". For example, delivery against rating has p < 0.001
but an effect size of only 0.074, which is negligible in practice. Twelve tests were run at α = 0.05.

### Q14. What are the limitations of your study?

- **No financial outcome:** popularity is measured by Zomato votes, not revenue, profit or footfall, so no
  financial success claims are made.
- **Single snapshot:** the data were published on Kaggle in 2018 and have no dates, so trends and causal
  effects cannot be studied.
- **Uneven sampling:** Delhi NCR dominates, and other cities and countries look like curated samples, so
  results generalise best to Delhi NCR.
- **Unrated restaurants:** 22.5% of restaurants are unrated and have no popularity class, so they are not
  used for training. The model can still score them (it uses no votes or rating) and puts 89.6% in Low, but
  those predictions cannot be checked.
- **Source data issues:**
  - 499 restaurants lack usable coordinates;
  - some text has corrupted accented characters that cannot be reliably repaired;
  - costs are in local currencies. I used price range for comparisons; the US-dollar costs (World Bank
    2017 rates) are approximate because the listing dates are unknown.
- **Missing popularity drivers:** food quality, service and marketing are not in the data, which limits
  any model.
- **Modest tuning:** the hyper-parameter grids were kept small, so slightly better scores may be possible.

I handled each limitation openly: by defining the target within each country, by testing robustness, and by
stating that all findings are associations.

### Q15. What recommendations do you make, and what future work would improve the project?

The six recommendations on the Insights page of both dashboards (each based on numbered findings):
- **Choose the location first** (F1, F7): location and locality carry the most signal. Caveat: outside
  Delhi NCR the data lists mostly well-known restaurants (72.1% High there, 28.7% within NCR), so part of
  this reflects sampling.
- **Offer table booking where the format allows it** (F3): in India 63.0% of restaurants with booking are
  High, against 27.6% without (association, not proof of cause).
- **Use delivery for reach, not for rating** (F4): in India, delivery goes with a higher High share (44.6%
  against 27.2%) but ratings barely differ (3.37 against 3.34).
- **Mind the price band** (F2): ranges 3 and 4 are more often High; budget outlets compete in a crowded,
  lower-voted segment.
- **Help unrated restaurants get their first ratings** (F6): a fifth of listings have no rating.
- **Use the model as a screen, not a verdict** (F7, F8): it separates High from Low well; Medium predictions
  near a cut-off are uncertain.

**For platforms:** show recommendation scores with their components, as this engine does, to build trust.

**Future work:**
- Add review text for sentiment analysis.
- Collect data at several dates to study trends.
- Obtain sales or footfall figures to test financial success directly.
- Expand coverage beyond Delhi NCR.
- Evaluate the recommender with real user feedback.
- Tune the models more widely and check whether the 61.3% accuracy holds on a newer Zomato snapshot.
