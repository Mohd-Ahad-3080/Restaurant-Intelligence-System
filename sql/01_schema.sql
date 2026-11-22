-- =====================================================================
-- Restaurant Intelligence System - MySQL 8 schema
-- Database: restaurant_intelligence (utf8mb4)
-- Source: data/processed/zomato_clean.csv + restaurant_cuisines.csv
-- Re-runnable: drops and recreates the tables.
-- =====================================================================

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS restaurant_cuisines;
DROP TABLE IF EXISTS restaurants;
DROP TABLE IF EXISTS countries;
SET FOREIGN_KEY_CHECKS = 1;

-- Lookup: one row per country (from Country-Code.xlsx, names cleaned)
CREATE TABLE countries (
    country_code   SMALLINT     NOT NULL,
    country_name   VARCHAR(60)  NOT NULL,
    PRIMARY KEY (country_code),
    UNIQUE KEY uq_country_name (country_name)
) ENGINE = InnoDB;

-- Fact table: one row per restaurant (cleaned)
CREATE TABLE restaurants (
    restaurant_id         INT            NOT NULL,
    restaurant_name       VARCHAR(150)   NOT NULL,
    country_code          SMALLINT       NOT NULL,
    city                  VARCHAR(80)    NOT NULL,
    address               VARCHAR(300)   NULL,
    locality              VARCHAR(150)   NULL,
    locality_verbose      VARCHAR(200)   NULL,
    longitude             DECIMAL(11, 7) NULL,        -- NULL = no valid coordinates
    latitude              DECIMAL(10, 7) NULL,
    has_valid_coords      TINYINT(1)     NOT NULL,
    cuisines              VARCHAR(255)   NOT NULL,    -- original comma-separated list ('Unknown' if missing)
    n_cuisines            TINYINT        NOT NULL,
    avg_cost_for_two      DECIMAL(12, 2) NULL,        -- LOCAL currency; NULL where source had 0
    avg_cost_for_two_usd  DECIMAL(10, 2) NULL,        -- APPROXIMATE US$, World Bank 2017 official rate by country
    currency              VARCHAR(40)    NOT NULL,
    is_cost_outlier       TINYINT(1)     NOT NULL,
    has_table_booking     TINYINT(1)     NULL,
    has_online_delivery   TINYINT(1)     NULL,
    is_delivering_now     TINYINT(1)     NULL,
    switch_to_order_menu  TINYINT(1)     NULL,
    price_range           TINYINT        NULL,
    aggregate_rating      DECIMAL(2, 1)  NULL,        -- NULL = not rated
    rating_color          VARCHAR(20)    NULL,
    rating_text           VARCHAR(20)    NULL,
    votes                 INT            NULL,
    is_rated              TINYINT(1)     NOT NULL,
    votes_pct_in_country  DECIMAL(7, 6)  NULL,
    popularity_class      ENUM('Low', 'Medium', 'High') NULL,   -- popularity target (Option B)
    PRIMARY KEY (restaurant_id),
    CONSTRAINT fk_rest_country FOREIGN KEY (country_code) REFERENCES countries (country_code),
    CONSTRAINT chk_rating      CHECK (aggregate_rating IS NULL OR aggregate_rating BETWEEN 0 AND 5),
    CONSTRAINT chk_price       CHECK (price_range IS NULL OR price_range BETWEEN 1 AND 4),
    CONSTRAINT chk_votes       CHECK (votes IS NULL OR votes >= 0),
    CONSTRAINT chk_cost        CHECK (avg_cost_for_two IS NULL OR avg_cost_for_two > 0),
    CONSTRAINT chk_rated_class CHECK ((is_rated = 1) = (popularity_class IS NOT NULL)),
    INDEX idx_country_city   (country_code, city),
    INDEX idx_city_locality  (city, locality),
    INDEX idx_price_range    (price_range),
    INDEX idx_popularity     (popularity_class),
    INDEX idx_name           (restaurant_name)
) ENGINE = InnoDB;

-- Bridge table: one row per restaurant-cuisine pair (many-to-many)
CREATE TABLE restaurant_cuisines (
    restaurant_id  INT          NOT NULL,
    cuisine        VARCHAR(60)  NOT NULL,
    PRIMARY KEY (restaurant_id, cuisine),
    INDEX idx_cuisine (cuisine),
    CONSTRAINT fk_rc_restaurant FOREIGN KEY (restaurant_id) REFERENCES restaurants (restaurant_id)
        ON DELETE CASCADE
) ENGINE = InnoDB;
