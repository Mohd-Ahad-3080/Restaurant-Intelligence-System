-- =====================================================================
-- Reusable analytical views (used by queries, Python EDA and dashboards)
-- =====================================================================

-- Restaurants with the country name joined in
CREATE OR REPLACE VIEW v_restaurants AS
SELECT r.*, c.country_name
FROM restaurants r
JOIN countries c ON c.country_code = r.country_code;

-- Chain indicator: how many rows share the restaurant name (branches)
CREATE OR REPLACE VIEW v_restaurant_branches AS
SELECT r.restaurant_id,
       COUNT(*) OVER (PARTITION BY r.restaurant_name) AS branch_count
FROM restaurants r;

-- One row per country
CREATE OR REPLACE VIEW v_country_summary AS
SELECT c.country_name,
       COUNT(*)                                  AS restaurants,
       SUM(r.is_rated)                           AS rated_restaurants,
       ROUND(AVG(r.aggregate_rating), 2)         AS avg_rating,
       SUM(r.votes)                              AS total_votes,
       ROUND(100 * AVG(r.has_online_delivery), 1) AS online_delivery_pct,
       ROUND(100 * AVG(r.has_table_booking), 1)  AS table_booking_pct,
       ROUND(AVG(r.price_range), 2)              AS avg_price_range
FROM restaurants r
JOIN countries c ON c.country_code = r.country_code
GROUP BY c.country_name;

-- One row per city
CREATE OR REPLACE VIEW v_city_summary AS
SELECT c.country_name, r.city,
       COUNT(*)                                  AS restaurants,
       SUM(r.is_rated)                           AS rated_restaurants,
       ROUND(AVG(r.aggregate_rating), 2)         AS avg_rating,
       SUM(r.votes)                              AS total_votes,
       ROUND(100 * AVG(r.has_online_delivery), 1) AS online_delivery_pct,
       ROUND(AVG(r.price_range), 2)              AS avg_price_range
FROM restaurants r
JOIN countries c ON c.country_code = r.country_code
GROUP BY c.country_name, r.city;

-- One row per locality (area competition = number of restaurants in the locality)
CREATE OR REPLACE VIEW v_locality_summary AS
SELECT r.city, r.locality,
       COUNT(*)                          AS restaurants,
       SUM(r.is_rated)                   AS rated_restaurants,
       ROUND(AVG(r.aggregate_rating), 2) AS avg_rating,
       ROUND(AVG(r.price_range), 2)      AS avg_price_range
FROM restaurants r
GROUP BY r.city, r.locality;

-- One row per individual cuisine
CREATE OR REPLACE VIEW v_cuisine_summary AS
SELECT rc.cuisine,
       COUNT(*)                                   AS restaurants,
       SUM(r.is_rated)                            AS rated_restaurants,
       ROUND(AVG(r.aggregate_rating), 2)          AS avg_rating,
       ROUND(AVG(r.price_range), 2)               AS avg_price_range,
       ROUND(100 * AVG(r.has_online_delivery), 1) AS online_delivery_pct,
       SUM(r.popularity_class = 'High')           AS high_popularity
FROM restaurant_cuisines rc
JOIN restaurants r ON r.restaurant_id = rc.restaurant_id
GROUP BY rc.cuisine;

-- One row per price range
CREATE OR REPLACE VIEW v_price_summary AS
SELECT r.price_range,
       COUNT(*)                                   AS restaurants,
       SUM(r.is_rated)                            AS rated_restaurants,
       ROUND(AVG(r.aggregate_rating), 2)          AS avg_rating,
       ROUND(AVG(r.votes), 1)                     AS avg_votes,
       ROUND(100 * AVG(r.has_online_delivery), 1) AS online_delivery_pct,
       ROUND(100 * AVG(r.has_table_booking), 1)   AS table_booking_pct
FROM restaurants r
GROUP BY r.price_range;
