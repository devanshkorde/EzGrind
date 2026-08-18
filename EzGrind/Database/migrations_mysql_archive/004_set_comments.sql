-- =====================================================================
-- 004_set_comments.sql
-- =====================================================================
-- Replaces the "time under tension" input with a free-text note per set.
--
-- time_under_tension IS DELIBERATELY LEFT IN PLACE. 21 of the 22 existing
-- rows hold a real value, and removing a feature from the form is not a
-- reason to destroy the history behind it. The application stops writing
-- to the column; the data stays readable. Drop it in a later migration
-- only after deciding that history is genuinely unwanted.
--
-- Idempotent, same information_schema guard as 002.
--
-- Applied by: mysql -u root -p ezgrind_db < 004_set_comments.sql
-- =====================================================================

USE ezgrind_db;

-- 500 characters: a note about a set, not a training diary. Bounded so the
-- backend has a length to validate against rather than accepting anything.
SET @ddl := IF(
    (SELECT COUNT(*) FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'workout_sets'
        AND COLUMN_NAME = 'comments') > 0,
    'DO 0',
    'ALTER TABLE workout_sets ADD COLUMN comments VARCHAR(500) NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
