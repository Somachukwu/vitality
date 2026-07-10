-- ============================================================
-- Vita DB — MySQL 8.4 Init Script
-- Run once to create the database and all tables from scratch
-- ============================================================

CREATE DATABASE IF NOT EXISTS vita_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE vita_db;

-- ────────────────────────────────────────────────
-- 1. USERS
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id                      INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name                    VARCHAR(100)  NOT NULL,
    email                   VARCHAR(255)  NOT NULL UNIQUE,
    password_hash           VARCHAR(255)  NOT NULL,
    age                     TINYINT UNSIGNED,
    sex                     ENUM('male','female','other'),
    height                  FLOAT COMMENT 'cm',
    weight                  FLOAT COMMENT 'kg',
    daily_calorie_target    INT UNSIGNED,
    goal_type               ENUM('weight_loss','weight_gain','maintenance'),
    dietary_restrictions    JSON,
    notification_preferences JSON,
    created_at              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                            ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_email (email)
) ENGINE=InnoDB;

-- ────────────────────────────────────────────────
-- 2. DEVICES  (ESP32 units linked to a user)
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS devices (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id     INT UNSIGNED NOT NULL,
    device_uid  VARCHAR(100) NOT NULL UNIQUE COMMENT 'ESP32 MAC / chip ID',
    device_name VARCHAR(100) NOT NULL DEFAULT 'ESP32 Device',
    api_key     VARCHAR(64)  NOT NULL UNIQUE,
    is_active   TINYINT(1)   NOT NULL DEFAULT 1,
    last_seen   DATETIME,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_device_user FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE,
    INDEX idx_device_api_key (api_key),
    INDEX idx_device_user    (user_id)
) ENGINE=InnoDB;

-- ────────────────────────────────────────────────
-- 3. VITALS  (sensor readings pushed by ESP32)
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vitals (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id     INT UNSIGNED NOT NULL,
    device_id   INT UNSIGNED,
    heart_rate  FLOAT  COMMENT 'bpm',
    spo2        FLOAT  COMMENT 'blood oxygen %',
    temperature FLOAT  COMMENT 'degrees Celsius',
    humidity    FLOAT  COMMENT 'ambient humidity %',
    weight      FLOAT  COMMENT 'kg',
    steps       INT UNSIGNED,
    recorded_at DATETIME NOT NULL COMMENT 'timestamp from ESP32 or server',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_vitals_user   FOREIGN KEY (user_id)
        REFERENCES users   (id) ON DELETE CASCADE,
    CONSTRAINT fk_vitals_device FOREIGN KEY (device_id)
        REFERENCES devices (id) ON DELETE SET NULL,
    INDEX idx_vitals_user_time (user_id, recorded_at)
) ENGINE=InnoDB;

-- ────────────────────────────────────────────────
-- 4. MEALS
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS meals (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id         INT UNSIGNED NOT NULL,
    meal_type       ENUM('breakfast','lunch','dinner','snack') NOT NULL,
    total_calories  FLOAT NOT NULL DEFAULT 0,
    total_carbs     FLOAT NOT NULL DEFAULT 0,
    total_protein   FLOAT NOT NULL DEFAULT 0,
    total_fat       FLOAT NOT NULL DEFAULT 0,
    image_url       VARCHAR(500),
    notes           TEXT,
    logged_at       DATETIME NOT NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_meals_user FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE,
    INDEX idx_meals_user_time (user_id, logged_at)
) ENGINE=InnoDB;

-- ────────────────────────────────────────────────
-- 5. MEAL ITEMS  (individual food entries in a meal)
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS meal_items (
    id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    meal_id      INT UNSIGNED NOT NULL,
    food_name    VARCHAR(200) NOT NULL,
    portion_size VARCHAR(100),
    calories     FLOAT NOT NULL DEFAULT 0,
    carbs        FLOAT NOT NULL DEFAULT 0,
    protein      FLOAT NOT NULL DEFAULT 0,
    fat          FLOAT NOT NULL DEFAULT 0,
    CONSTRAINT fk_items_meal FOREIGN KEY (meal_id)
        REFERENCES meals (id) ON DELETE CASCADE,
    INDEX idx_items_meal (meal_id)
) ENGINE=InnoDB;

-- ────────────────────────────────────────────────
-- 6. RECOMMENDATIONS
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS recommendations (
    id         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id    INT UNSIGNED NOT NULL,
    type       ENUM('nutrition','activity','health_alert','goal_progress') NOT NULL,
    severity   ENUM('info','warning','critical') NOT NULL DEFAULT 'info',
    title      VARCHAR(200) NOT NULL,
    message    TEXT         NOT NULL,
    is_read    TINYINT(1)   NOT NULL DEFAULT 0,
    created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_rec_user FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE,
    INDEX idx_rec_user_time (user_id, created_at)
) ENGINE=InnoDB;

-- ────────────────────────────────────────────────
-- Confirm
-- ────────────────────────────────────────────────
SELECT
    table_name         AS `Table`,
    table_rows         AS `Rows (approx)`,
    engine             AS `Engine`,
    table_collation    AS `Collation`
FROM information_schema.tables
WHERE table_schema = 'vita_db'
ORDER BY table_name;


use vita_db;
DELETE FROM meals WHERE image_url IS NULL;

SELECT * FROM users