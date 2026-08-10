-- =====================================================================
-- 002_constraints_and_indexes.sql
-- =====================================================================
-- Constraints, ordering and type corrections on the existing tables.
-- Adds no tables and drops no data.
--
-- IDEMPOTENCY NOTE
-- MySQL supports IF NOT EXISTS for CREATE TABLE, but NOT for ADD COLUMN,
-- CREATE INDEX or ADD CONSTRAINT (that is MariaDB). So every statement below
-- inspects information_schema and executes 'DO 0' when the change is already
-- present. Re-running this file is therefore harmless.
--
-- INDEXES DELIBERATELY NOT ADDED
--   workout_sets(workout_id) - InnoDB already created this for the foreign
--     key, and it is exactly the join predicate. A second copy would be dead
--     weight.
--   workouts(user_id, workout_date DESC) - the UNIQUE constraint added below
--     builds a B-tree on those two columns, and MySQL 8 performs backward
--     index scans, so ORDER BY workout_date DESC uses it as-is. A descending
--     duplicate would cost write throughput and return nothing.
--
-- MUST BE APPLIED BEFORE the matching Backend change ships: workout_repo.log_set
-- relies on the UNIQUE constraint below for its upsert, and writes set_order.
--
-- Applied by: mysql -u root -p ezgrind_db < 002_constraints_and_indexes.sql
-- =====================================================================

USE ezgrind_db;


-- ---------------------------------------------------------------------
-- 1. One workout per user per day
--    The log-a-set path has always assumed this. Nothing enforced it, so a
--    double-submit could produce two workout rows for the same date and split
--    a day's training in two.
-- ---------------------------------------------------------------------
SET @ddl := IF(
    (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
      WHERE CONSTRAINT_SCHEMA = DATABASE()
        AND TABLE_NAME = 'workouts'
        AND CONSTRAINT_NAME = 'uq_workouts_user_date') > 0,
    'DO 0',
    'ALTER TABLE workouts ADD CONSTRAINT uq_workouts_user_date UNIQUE (user_id, workout_date)');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- ---------------------------------------------------------------------
-- 2. Reference data must be unique by name
--    Without these, INSERT IGNORE in the seed file cannot detect a collision
--    and would happily insert a second copy of every muscle and exercise.
--    Also stops two same-named exercises collapsing in the dashboard's
--    GROUP BY exercise_name.
-- ---------------------------------------------------------------------
SET @ddl := IF(
    (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
      WHERE CONSTRAINT_SCHEMA = DATABASE()
        AND TABLE_NAME = 'muscle_groups'
        AND CONSTRAINT_NAME = 'uq_muscle_groups_name') > 0,
    'DO 0',
    'ALTER TABLE muscle_groups ADD CONSTRAINT uq_muscle_groups_name UNIQUE (muscle_name)');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl := IF(
    (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
      WHERE CONSTRAINT_SCHEMA = DATABASE()
        AND TABLE_NAME = 'exercises'
        AND CONSTRAINT_NAME = 'uq_exercises_name_muscle') > 0,
    'DO 0',
    'ALTER TABLE exercises ADD CONSTRAINT uq_exercises_name_muscle UNIQUE (exercise_name, muscle_id)');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- ---------------------------------------------------------------------
-- 3. Deleting a workout must delete its sets
--    A set with no parent workout has no date and no owner - it is garbage,
--    not data. exercises -> muscle_groups is deliberately left RESTRICT:
--    deleting a muscle group should fail loudly, not silently erase the
--    exercise catalogue.
--
--    NOTE: workouts -> users is also still RESTRICT, so a user row cannot be
--    deleted while it has training history. That is intentional for now.
--
--    A foreign key's delete rule cannot be altered in place, so the
--    auto-named original is dropped and a named replacement added.
-- ---------------------------------------------------------------------
SET @ddl := IF(
    (SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS
      WHERE CONSTRAINT_SCHEMA = DATABASE()
        AND TABLE_NAME = 'workout_sets'
        AND CONSTRAINT_NAME = 'workout_sets_ibfk_1') > 0,
    'ALTER TABLE workout_sets DROP FOREIGN KEY workout_sets_ibfk_1',
    'DO 0');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl := IF(
    (SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS
      WHERE CONSTRAINT_SCHEMA = DATABASE()
        AND TABLE_NAME = 'workout_sets'
        AND CONSTRAINT_NAME = 'fk_workout_sets_workout') > 0,
    'DO 0',
    'ALTER TABLE workout_sets ADD CONSTRAINT fk_workout_sets_workout FOREIGN KEY (workout_id) REFERENCES workouts(workout_id) ON DELETE CASCADE');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- ---------------------------------------------------------------------
-- 4. workout_sets.created_at
--    Added without a default first, so existing rows land as NULL and can be
--    backfilled from their parent workout. Adding it with DEFAULT
--    CURRENT_TIMESTAMP would stamp every historical set with the moment this
--    migration ran, which is worse than useless - it looks like real data.
-- ---------------------------------------------------------------------
SET @ddl := IF(
    (SELECT COUNT(*) FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'workout_sets'
        AND COLUMN_NAME = 'created_at') > 0,
    'DO 0',
    'ALTER TABLE workout_sets ADD COLUMN created_at TIMESTAMP NULL DEFAULT NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

UPDATE workout_sets ws
  JOIN workouts w ON w.workout_id = ws.workout_id
   SET ws.created_at = w.created_at
 WHERE ws.created_at IS NULL;

-- Only now attach the default, so future inserts stamp themselves.
SET @ddl := IF(
    (SELECT COUNT(*) FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'workout_sets'
        AND COLUMN_NAME = 'created_at'
        AND COLUMN_DEFAULT = 'CURRENT_TIMESTAMP') > 0,
    'DO 0',
    'ALTER TABLE workout_sets MODIFY COLUMN created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- ---------------------------------------------------------------------
-- 5. workout_sets.set_order
--    Sets within a day had no defined order - "set 1 vs set 4" could not be
--    reconstructed, because set_id ordering is an implementation detail, not
--    a promise. Backfilled from set_id, which is the best approximation
--    available for rows already in the table.
-- ---------------------------------------------------------------------
SET @ddl := IF(
    (SELECT COUNT(*) FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'workout_sets'
        AND COLUMN_NAME = 'set_order') > 0,
    'DO 0',
    'ALTER TABLE workout_sets ADD COLUMN set_order SMALLINT UNSIGNED NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

UPDATE workout_sets ws
  JOIN (
      SELECT set_id,
             ROW_NUMBER() OVER (PARTITION BY workout_id ORDER BY set_id) AS rn
        FROM workout_sets
  ) AS ranked ON ranked.set_id = ws.set_id
   SET ws.set_order = ranked.rn
 WHERE ws.set_order IS NULL;


-- ---------------------------------------------------------------------
-- 6. Column types
--    weight DECIMAL(5,2) topped out at 999.99 kg. DECIMAL(6,2) is a lossless
--    widening.
--    reps was INT: four bytes and a two-billion ceiling for a number whose
--    real limit is about 100, and it permitted negatives. SMALLINT UNSIGNED
--    plus a CHECK bounds it properly. MySQL 8.0.16+ enforces CHECK.
-- ---------------------------------------------------------------------
SET @ddl := IF(
    (SELECT COLUMN_TYPE FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'workout_sets'
        AND COLUMN_NAME = 'weight') = 'decimal(6,2)',
    'DO 0',
    'ALTER TABLE workout_sets MODIFY COLUMN weight DECIMAL(6,2) NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl := IF(
    (SELECT COLUMN_TYPE FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'workout_sets'
        AND COLUMN_NAME = 'reps') = 'smallint unsigned',
    'DO 0',
    'ALTER TABLE workout_sets MODIFY COLUMN reps SMALLINT UNSIGNED NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl := IF(
    (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
      WHERE CONSTRAINT_SCHEMA = DATABASE()
        AND TABLE_NAME = 'workout_sets'
        AND CONSTRAINT_NAME = 'chk_workout_sets_reps') > 0,
    'DO 0',
    'ALTER TABLE workout_sets ADD CONSTRAINT chk_workout_sets_reps CHECK (reps > 0)');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
