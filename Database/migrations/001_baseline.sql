-- =====================================================================
-- 001_baseline.sql
-- =====================================================================
-- The schema as it actually exists today, after every ALTER that was
-- appended to the old EzGrindDB.sql had been applied by hand.
--
-- This file documents an existing state. It is:
--   * safe to run against a fresh database  -> creates everything
--   * safe to run against a live database   -> every statement no-ops
--
-- FORWARD ONLY. Once this file has been applied anywhere, never edit it.
-- Corrections go in a new numbered migration.
--
-- Applied by: mysql -u root -p < 001_baseline.sql
-- =====================================================================

CREATE DATABASE IF NOT EXISTS ezgrind_db
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_0900_ai_ci;

USE ezgrind_db;


-- Accounts. contact_number through fitness_goal were added by a later ALTER
-- than the original CREATE, and height_cm/weight_kg were widened INT -> FLOAT;
-- both are folded in here so a fresh database matches a migrated one exactly.
CREATE TABLE IF NOT EXISTS users (
    user_id        INT AUTO_INCREMENT PRIMARY KEY,
    full_name      VARCHAR(100) NOT NULL,
    email          VARCHAR(100) NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    contact_number VARCHAR(15),
    date_of_birth  DATE,
    height_cm      FLOAT,
    weight_kg      FLOAT,
    fitness_goal   VARCHAR(20)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- Reference data. image_path is relative to Frontend/, e.g. assets/muscles/chest.png
CREATE TABLE IF NOT EXISTS muscle_groups (
    muscle_id   INT AUTO_INCREMENT PRIMARY KEY,
    muscle_name VARCHAR(50)  NOT NULL,
    image_path  VARCHAR(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- Reference data. Seeded from seeds/muscle_groups_and_exercises.sql
CREATE TABLE IF NOT EXISTS exercises (
    exercise_id   INT AUTO_INCREMENT PRIMARY KEY,
    exercise_name VARCHAR(100) NOT NULL,
    muscle_id     INT NOT NULL,
    equipment     VARCHAR(50),
    description   TEXT,
    FOREIGN KEY (muscle_id) REFERENCES muscle_groups(muscle_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- One row per user per training day. The uniqueness that implies is NOT
-- enforced here - migration 002 adds it.
CREATE TABLE IF NOT EXISTS workouts (
    workout_id   INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT NOT NULL,
    workout_date DATE NOT NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- One row per set performed. weight/reps types are widened and ordering is
-- added in migration 002.
CREATE TABLE IF NOT EXISTS workout_sets (
    set_id             INT AUTO_INCREMENT PRIMARY KEY,
    workout_id         INT NOT NULL,
    exercise_id        INT NOT NULL,
    weight             DECIMAL(5,2),
    reps               INT,
    time_under_tension INT,
    FOREIGN KEY (workout_id)  REFERENCES workouts(workout_id),
    FOREIGN KEY (exercise_id) REFERENCES exercises(exercise_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
