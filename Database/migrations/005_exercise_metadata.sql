-- =====================================================================
-- 005_exercise_metadata.sql
-- =====================================================================
-- Prepares the exercises table for a ~2,900 row import.
--
-- ADDITIVE ONLY. Nothing is dropped, truncated or renumbered. exercise_id
-- values 1-24 keep their identities, so existing workout_sets rows keep
-- pointing at the exercises they were logged against.
--
-- ALREADY PRESENT, so deliberately not repeated here:
--   * UNIQUE (exercise_name, muscle_id) - added by 002 as
--     uq_exercises_name_muscle. It is what makes the import re-runnable.
--   * INDEX on muscle_id - InnoDB created it for the foreign key in 001.
--
-- ORDERING NOTE: run this BEFORE the import. Adding a FULLTEXT index to
-- InnoDB rebuilds the table to add a hidden FTS_DOC_ID column; doing that
-- against 24 rows is instant, against 2,900 it is not.
--
-- Idempotent: every statement checks information_schema first, because
-- MySQL has no IF NOT EXISTS for ADD COLUMN or CREATE INDEX.
--
-- Applied by: mysql -u root -p ezgrind_db < 005_exercise_metadata.sql
-- =====================================================================

USE ezgrind_db;


-- ---------------------------------------------------------------------
-- 1. New metadata columns
--    All nullable: the source has gaps in every one of them and a blank
--    is not the same claim as a zero.
--
--    rating is DECIMAL(3,2), so its ceiling is 9.99. The source tops out
--    at 9.6, so nothing is lost - but the importer clamps to 9.99 rather
--    than 10, which would overflow the column.
-- ---------------------------------------------------------------------
SET @ddl := IF(
    (SELECT COUNT(*) FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exercises'
        AND COLUMN_NAME = 'exercise_type') > 0,
    'DO 0',
    'ALTER TABLE exercises ADD COLUMN exercise_type VARCHAR(30) NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl := IF(
    (SELECT COUNT(*) FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exercises'
        AND COLUMN_NAME = 'difficulty_level') > 0,
    'DO 0',
    'ALTER TABLE exercises ADD COLUMN difficulty_level VARCHAR(20) NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl := IF(
    (SELECT COUNT(*) FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exercises'
        AND COLUMN_NAME = 'rating') > 0,
    'DO 0',
    'ALTER TABLE exercises ADD COLUMN rating DECIMAL(3,2) NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- ---------------------------------------------------------------------
-- 2. Equipment filter index
--    The catalogue endpoint filters on exact equipment. Without this it
--    is a full scan of ~2,900 rows on every filtered request.
-- ---------------------------------------------------------------------
SET @ddl := IF(
    (SELECT COUNT(*) FROM information_schema.STATISTICS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exercises'
        AND INDEX_NAME = 'idx_exercises_equipment') > 0,
    'DO 0',
    'ALTER TABLE exercises ADD INDEX idx_exercises_equipment (equipment)');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- ---------------------------------------------------------------------
-- 3. Full-text search on the exercise name
--
--    This is a WORD index, not a substring index. In boolean mode
--    "ben*" matches "Bench Press", but no full-text query will ever
--    match "ress" inside "Press", and terms shorter than
--    innodb_ft_min_token_size (default 3) are ignored entirely.
--    The API falls back to LIKE below that length so a combobox does
--    not go dead on the first two keystrokes.
-- ---------------------------------------------------------------------
SET @ddl := IF(
    (SELECT COUNT(*) FROM information_schema.STATISTICS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exercises'
        AND INDEX_NAME = 'ft_exercises_name') > 0,
    'DO 0',
    'ALTER TABLE exercises ADD FULLTEXT INDEX ft_exercises_name (exercise_name)');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- ---------------------------------------------------------------------
-- 4. Muscle groups for the body parts the source has and we did not
--
--    77 exercises land here. Dropping them to avoid a missing image
--    would be losing data to protect a picture.
--
--    All four share a generated placeholder until real artwork exists:
--      Forearms 31, Abductors 21, Adductors 17, Neck 8
--
--    Explicit ids so the importer's mapping is stable, and INSERT IGNORE
--    so re-running changes nothing. muscle_name is UNIQUE as of 002.
-- ---------------------------------------------------------------------
INSERT IGNORE INTO muscle_groups (muscle_id, muscle_name, image_path) VALUES
    (13, 'Forearms',  'assets/muscles/placeholder.png'),
    (14, 'Abductors', 'assets/muscles/placeholder.png'),
    (15, 'Adductors', 'assets/muscles/placeholder.png'),
    (16, 'Neck',      'assets/muscles/placeholder.png');
