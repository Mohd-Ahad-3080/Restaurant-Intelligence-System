-- =====================================================================
-- Analytical queries for the report
-- Format: each query starts with a header line
--     -- Qnn | short_name | Question the query answers
-- and ends with a semicolon. src/sql_runner.py runs them in order and
-- saves each result to outputs/sql_results/Qnn_short_name.csv.
-- Ratings: aggregate_rating is NULL for unrated restaurants, so AVG()
-- automatically uses rated restaurants only.
-- =====================================================================

-- Q01 | headline_kpis | What are the headline figures of the dataset?
SELECT COUNT(*)                                   AS restaurants,
       COUNT(DISTINCT country_code)               AS countries,
       COUNT(DISTINCT city)                       AS cities,
       SUM(is_rated)                              AS rated_restaurants,
       ROUND(AVG(aggregate_rating), 2)            AS avg_rating_rated_only,
       SUM(votes)                                 AS total_votes,
       ROUND(100 * AVG(has_online_delivery), 1)   AS online_delivery_pct,
       ROUND(100 * AVG(has_table_booking), 1)     AS table_booking_pct
FROM restaurants;

-- Q02 | restaurants_by_country | How are restaurants distributed across countries?
SELECT country_name, restaurants,
       ROUND(100 * restaurants / SUM(restaurants) OVER (), 2) AS share_pct,
       rated_restaurants, avg_rating
FROM v_country_summary
ORDER BY restaurants DESC;

-- Q03 | top_cities | Which 10 cities have the most restaurants?
SELECT country_name, city, restaurants, avg_rating, online_delivery_pct
FROM v_city_summary
ORDER BY restaurants DESC
LIMIT 10;

-- Q04 | avg_rating_by_country | Which countries have the highest average rating (rated restaurants only)?
SELECT country_name, rated_restaurants, avg_rating
FROM v_country_summary
ORDER BY avg_rating DESC;

-- Q05 | rating_band_distribution | How many restaurants fall in each rating band?
SELECT rating_text,
       COUNT(*) AS restaurants,
       ROUND(100 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS share_pct,
       MIN(aggregate_rating) AS min_rating,
       MAX(aggregate_rating) AS max_rating
FROM restaurants
GROUP BY rating_text
ORDER BY MIN(COALESCE(aggregate_rating, 0));

-- Q06 | price_range_profile | How do rating, votes, delivery and booking change with price range?
SELECT price_range, restaurants,
       ROUND(100 * restaurants / SUM(restaurants) OVER (), 2) AS share_pct,
       avg_rating, avg_votes, online_delivery_pct, table_booking_pct
FROM v_price_summary
ORDER BY price_range;

-- Q07 | online_delivery_by_country | Which countries offer online delivery on Zomato?
SELECT country_name, restaurants, online_delivery_pct
FROM v_country_summary
ORDER BY online_delivery_pct DESC, restaurants DESC;

-- Q08 | delivery_vs_rating_india | In India, do restaurants with online delivery have different ratings?
SELECT CASE has_online_delivery WHEN 1 THEN 'Online delivery' ELSE 'No online delivery' END AS delivery,
       COUNT(*)                         AS restaurants,
       SUM(is_rated)                    AS rated_restaurants,
       ROUND(AVG(aggregate_rating), 2)  AS avg_rating,
       ROUND(AVG(votes), 1)             AS avg_votes
FROM v_restaurants
WHERE country_name = 'India'
GROUP BY has_online_delivery;

-- Q09 | booking_vs_rating_india | In India, do restaurants with table booking have different ratings and costs?
SELECT CASE has_table_booking WHEN 1 THEN 'Table booking' ELSE 'No table booking' END AS booking,
       COUNT(*)                          AS restaurants,
       ROUND(AVG(aggregate_rating), 2)   AS avg_rating,
       ROUND(AVG(avg_cost_for_two), 0)   AS avg_cost_for_two_inr,
       ROUND(AVG(votes), 1)              AS avg_votes
FROM v_restaurants
WHERE country_name = 'India'
GROUP BY has_table_booking;

-- Q10 | top_cuisines | Which 15 cuisines are offered by the most restaurants?
SELECT cuisine, restaurants,
       ROUND(100 * restaurants / (SELECT COUNT(*) FROM restaurants), 2) AS share_of_restaurants_pct,
       avg_rating
FROM v_cuisine_summary
ORDER BY restaurants DESC
LIMIT 15;

-- Q11 | best_rated_cuisines | Which cuisines have the highest average rating (at least 50 rated restaurants)?
SELECT cuisine, rated_restaurants, avg_rating, avg_price_range
FROM v_cuisine_summary
WHERE rated_restaurants >= 50
ORDER BY avg_rating DESC
LIMIT 15;

-- Q12 | cuisines_high_popularity | Which cuisines have the largest share of High-popularity restaurants (at least 50 rated)?
SELECT cuisine, rated_restaurants, high_popularity,
       ROUND(100 * high_popularity / rated_restaurants, 1) AS high_popularity_pct
FROM v_cuisine_summary
WHERE rated_restaurants >= 50
ORDER BY high_popularity_pct DESC
LIMIT 15;

-- Q13 | cuisine_count_vs_rating | Do restaurants offering more cuisines get better ratings or more votes?
SELECT CASE WHEN n_cuisines = 0 THEN 'Unknown'
            WHEN n_cuisines >= 5 THEN '5+'
            ELSE CAST(n_cuisines AS CHAR) END AS cuisines_offered,
       COUNT(*)                         AS restaurants,
       ROUND(AVG(aggregate_rating), 2)  AS avg_rating,
       ROUND(AVG(votes), 1)             AS avg_votes
FROM restaurants
GROUP BY cuisines_offered
ORDER BY cuisines_offered;

-- Q14 | most_competitive_localities | Which localities have the most restaurants (area competition)?
SELECT city, locality, restaurants, avg_rating, avg_price_range
FROM v_locality_summary
ORDER BY restaurants DESC
LIMIT 15;

-- Q15 | best_rated_localities | Which localities have the highest average rating (at least 20 rated restaurants)?
SELECT city, locality, rated_restaurants, avg_rating, avg_price_range
FROM v_locality_summary
WHERE rated_restaurants >= 20
ORDER BY avg_rating DESC
LIMIT 15;

-- Q16 | india_cost_by_price_range | In India, what does a meal for two cost (INR) in each price range?
SELECT price_range,
       COUNT(avg_cost_for_two)          AS restaurants_with_cost,
       ROUND(MIN(avg_cost_for_two), 0)  AS min_cost_inr,
       ROUND(AVG(avg_cost_for_two), 0)  AS avg_cost_inr,
       ROUND(MAX(avg_cost_for_two), 0)  AS max_cost_inr
FROM v_restaurants
WHERE country_name = 'India'
GROUP BY price_range
ORDER BY price_range;

-- Q17 | cost_by_country_local | What is the average cost for two in each country (local currency, and approximate US$ at World Bank 2017 rates for comparison across countries)?
SELECT c.country_name, r.currency,
       COUNT(r.avg_cost_for_two)              AS restaurants_with_cost,
       ROUND(AVG(r.avg_cost_for_two), 0)      AS avg_cost_local,
       ROUND(AVG(r.avg_cost_for_two_usd), 2)  AS avg_cost_usd_approx
FROM restaurants r
JOIN countries c ON c.country_code = r.country_code
GROUP BY c.country_name, r.currency
ORDER BY restaurants_with_cost DESC;

-- Q18 | largest_chains | Which restaurant names have the most branches, and how are they rated?
SELECT restaurant_name,
       COUNT(*)                          AS branches,
       COUNT(DISTINCT city)              AS cities,
       ROUND(AVG(aggregate_rating), 2)   AS avg_rating,
       SUM(votes)                        AS total_votes
FROM restaurants
GROUP BY restaurant_name
HAVING COUNT(*) >= 10
ORDER BY branches DESC
LIMIT 15;

-- Q19 | chain_vs_independent | Do chain branches differ from single-outlet restaurants?
WITH tagged AS (
    SELECT r.*, CASE WHEN b.branch_count > 1 THEN 'Chain (2+ branches)' ELSE 'Single outlet' END AS outlet_type
    FROM restaurants r
    JOIN v_restaurant_branches b ON b.restaurant_id = r.restaurant_id
)
SELECT outlet_type,
       COUNT(*)                                 AS restaurants,
       ROUND(AVG(aggregate_rating), 2)          AS avg_rating,
       ROUND(AVG(votes), 1)                     AS avg_votes,
       ROUND(100 * AVG(has_online_delivery), 1) AS online_delivery_pct
FROM tagged
GROUP BY outlet_type;

-- Q20 | popularity_by_country | How is the popularity class distributed in each country?
SELECT country_name,
       SUM(popularity_class = 'Low')    AS low,
       SUM(popularity_class = 'Medium') AS medium,
       SUM(popularity_class = 'High')   AS high,
       SUM(is_rated)                    AS rated_restaurants
FROM v_restaurants
GROUP BY country_name
ORDER BY rated_restaurants DESC;

-- Q21 | popularity_by_price_range | Is popularity related to price range?
SELECT price_range,
       SUM(is_rated) AS rated_restaurants,
       ROUND(100 * SUM(popularity_class = 'Low')    / SUM(is_rated), 1) AS low_pct,
       ROUND(100 * SUM(popularity_class = 'Medium') / SUM(is_rated), 1) AS medium_pct,
       ROUND(100 * SUM(popularity_class = 'High')   / SUM(is_rated), 1) AS high_pct
FROM restaurants
GROUP BY price_range
ORDER BY price_range;

-- Q22 | popularity_by_services | Is popularity related to online delivery and table booking?
SELECT CASE has_online_delivery WHEN 1 THEN 'Yes' ELSE 'No' END AS online_delivery,
       CASE has_table_booking   WHEN 1 THEN 'Yes' ELSE 'No' END AS table_booking,
       SUM(is_rated) AS rated_restaurants,
       ROUND(100 * SUM(popularity_class = 'High') / SUM(is_rated), 1) AS high_pct,
       ROUND(100 * SUM(popularity_class = 'Low')  / SUM(is_rated), 1) AS low_pct
FROM restaurants
GROUP BY has_online_delivery, has_table_booking
ORDER BY has_online_delivery, has_table_booking;

-- Q23 | most_voted | Which 10 restaurants received the most votes?
SELECT restaurant_name, city, country_name, votes, aggregate_rating, price_range
FROM v_restaurants
ORDER BY votes DESC
LIMIT 10;

-- Q24 | unrated_share_by_city | In the 10 largest cities, what share of restaurants is still unrated?
SELECT city, restaurants,
       restaurants - rated_restaurants AS unrated,
       ROUND(100 * (restaurants - rated_restaurants) / restaurants, 1) AS unrated_pct
FROM v_city_summary
ORDER BY restaurants DESC
LIMIT 10;

-- Q25 | votes_rating_by_band | How do votes grow across rating bands?
SELECT rating_text,
       COUNT(*)                         AS restaurants,
       ROUND(AVG(votes), 1)             AS avg_votes,
       MIN(votes)                       AS min_votes,
       MAX(votes)                       AS max_votes
FROM restaurants
GROUP BY rating_text
ORDER BY AVG(votes);

-- Q26 | map_coverage | How many restaurants per country have usable map coordinates?
SELECT c.country_name,
       COUNT(*)                                AS restaurants,
       SUM(r.has_valid_coords)                 AS with_coordinates,
       ROUND(100 * AVG(r.has_valid_coords), 1) AS coverage_pct
FROM restaurants r
JOIN countries c ON c.country_code = r.country_code
GROUP BY c.country_name
ORDER BY restaurants DESC;

-- Q27 | top_cuisine_per_city | What is the most common cuisine in each of the 10 largest cities?
WITH big_cities AS (
    SELECT city FROM restaurants GROUP BY city ORDER BY COUNT(*) DESC LIMIT 10
),
ranked AS (
    SELECT r.city, rc.cuisine, COUNT(*) AS restaurants,
           ROW_NUMBER() OVER (PARTITION BY r.city ORDER BY COUNT(*) DESC, rc.cuisine) AS rn
    FROM restaurants r
    JOIN restaurant_cuisines rc ON rc.restaurant_id = r.restaurant_id
    WHERE r.city IN (SELECT city FROM big_cities)
    GROUP BY r.city, rc.cuisine
)
SELECT city, cuisine AS top_cuisine, restaurants
FROM ranked
WHERE rn = 1
ORDER BY restaurants DESC;

-- Q28 | locality_rank_largest_city | In the largest city, how do localities with 20+ rated restaurants rank by average rating?
WITH largest AS (
    SELECT city FROM restaurants GROUP BY city ORDER BY COUNT(*) DESC LIMIT 1
)
SELECT l.city, l.locality, l.rated_restaurants, l.avg_rating,
       RANK() OVER (ORDER BY l.avg_rating DESC) AS rating_rank
FROM v_locality_summary l
WHERE l.city = (SELECT city FROM largest) AND l.rated_restaurants >= 20
ORDER BY rating_rank
LIMIT 15;
