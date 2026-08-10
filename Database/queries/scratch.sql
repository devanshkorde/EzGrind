-- =====================================================================
-- scratch.sql
-- =====================================================================
-- Ad-hoc queries for poking at the database by hand. NOT part of the schema
-- and never applied by any process. These were previously mixed into
-- EzGrindDB.sql between the CREATE TABLE statements, which made it impossible
-- to tell the schema from someone's exploration.
--
-- Run individual statements; do not pipe this whole file anywhere.
-- =====================================================================

USE ezgrind_db;


-- ---------------------------------------------------------------------
-- Original exploratory queries, moved verbatim out of EzGrindDB.sql
-- ---------------------------------------------------------------------
SHOW TABLES;

DESCRIBE users;

SELECT * FROM users;
SELECT user_id, full_name, email FROM users;
SELECT * FROM exercises;
SELECT * FROM workout_sets;

-- One user's full training history
SELECT
    w.workout_date,
    e.exercise_name,
    ws.weight,
    ws.reps
FROM workouts w
JOIN workout_sets ws ON w.workout_id = ws.workout_id
JOIN exercises e     ON ws.exercise_id = e.exercise_id
WHERE w.user_id = 1
ORDER BY w.workout_date DESC, ws.set_order;


-- ---------------------------------------------------------------------
-- Rebuild personal_records from workout_sets
-- ---------------------------------------------------------------------
-- personal_records is a cache. This statement is the definition of what it
-- should contain, and the recovery path if it ever drifts. Safe to re-run at
-- any time; it corrects existing rows rather than duplicating them.
--
-- Estimated 1RM uses Epley: weight * (1 + reps / 30).
-- Ties break toward the EARLIEST date, so a PR keeps the day it was first set.
INSERT INTO personal_records
    (user_id, exercise_id, best_weight, best_reps, estimated_1rm, achieved_on)
SELECT ranked.user_id, ranked.exercise_id, ranked.weight,
       ranked.reps, ranked.e1rm, ranked.workout_date
FROM (
    SELECT w.user_id,
           ws.exercise_id,
           ws.weight,
           ws.reps,
           w.workout_date,
           ROUND(ws.weight * (1 + ws.reps / 30), 2) AS e1rm,
           ROW_NUMBER() OVER (
               PARTITION BY w.user_id, ws.exercise_id
               ORDER BY ws.weight * (1 + ws.reps / 30) DESC, w.workout_date ASC
           ) AS rn
    FROM workout_sets ws
    JOIN workouts w ON w.workout_id = ws.workout_id
    WHERE ws.weight IS NOT NULL
      AND ws.reps   IS NOT NULL
) AS ranked
WHERE ranked.rn = 1
ON DUPLICATE KEY UPDATE
    best_weight   = VALUES(best_weight),
    best_reps     = VALUES(best_reps),
    estimated_1rm = VALUES(estimated_1rm),
    achieved_on   = VALUES(achieved_on);

-- Total reset, if you would rather rebuild from empty:
-- DELETE FROM personal_records;   -- then run the INSERT above


-- ---------------------------------------------------------------------
-- Health / sanity checks
-- ---------------------------------------------------------------------
-- Should return zero rows once 002 is applied.
SELECT user_id, workout_date, COUNT(*) AS n
FROM workouts
GROUP BY user_id, workout_date
HAVING n > 1;

-- Sets that never got an order assigned.
SELECT COUNT(*) AS unordered_sets FROM workout_sets WHERE set_order IS NULL;

-- What the schema currently looks like.
SELECT TABLE_NAME, ENGINE, TABLE_COLLATION, TABLE_ROWS
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'ezgrind_db'
ORDER BY TABLE_NAME;
