-- =====================================================================
-- scratch.sql                                      PostgreSQL 16 (Neon)
-- =====================================================================
-- Ad-hoc queries for poking at the database by hand. NOT part of the schema
-- and never applied by any process.
--
-- Run individual statements; do not pipe this whole file anywhere.
-- =====================================================================


-- ---------------------------------------------------------------------
-- Looking around
--   \dt and \d are psql meta-commands, which is where SHOW TABLES and
--   DESCRIBE went. They only work in psql, not through a driver.
-- ---------------------------------------------------------------------
-- \dt
-- \d users

SELECT * FROM users;
SELECT user_id, full_name, email FROM users;
SELECT * FROM exercises LIMIT 50;
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
--
-- THE DIVISOR IS 30.0, NOT 30. reps is SMALLINT: integer division would floor
-- to 0 for every set under 30 reps and rebuild the whole table with
-- estimated_1rm equal to best_weight. It raises no error - it just quietly
-- writes wrong numbers over the right ones, which is the worst possible
-- behaviour for a statement whose job is repair.
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
           ROUND(ws.weight * (1 + ws.reps / 30.0), 2) AS e1rm,
           ROW_NUMBER() OVER (
               PARTITION BY w.user_id, ws.exercise_id
               ORDER BY ws.weight * (1 + ws.reps / 30.0) DESC, w.workout_date ASC
           ) AS rn
    FROM workout_sets ws
    JOIN workouts w ON w.workout_id = ws.workout_id
    WHERE ws.weight IS NOT NULL
      AND ws.reps   IS NOT NULL
) AS ranked
WHERE ranked.rn = 1
ON CONFLICT (user_id, exercise_id) DO UPDATE SET
    best_weight   = EXCLUDED.best_weight,
    best_reps     = EXCLUDED.best_reps,
    estimated_1rm = EXCLUDED.estimated_1rm,
    achieved_on   = EXCLUDED.achieved_on,
    updated_at    = now();

-- Total reset, if you would rather rebuild from empty:
-- DELETE FROM personal_records;   -- then run the INSERT above


-- ---------------------------------------------------------------------
-- Health / sanity checks
-- ---------------------------------------------------------------------
-- Should return zero rows - uq_workouts_user_date makes it impossible.
SELECT user_id, workout_date, COUNT(*) AS n
FROM workouts
GROUP BY user_id, workout_date
HAVING COUNT(*) > 1;

-- Sets that never got an order assigned.
SELECT COUNT(*) AS unordered_sets FROM workout_sets WHERE set_order IS NULL;

-- Records whose stored 1RM disagrees with their own weight and reps. Any row
-- here means an Epley was evaluated with integer division somewhere.
SELECT pr_id, user_id, exercise_id, best_weight, best_reps, estimated_1rm
FROM personal_records
WHERE ABS(estimated_1rm - ROUND(best_weight * (1 + best_reps / 30.0), 2)) > 0.05;

-- Identity sequences vs the largest id actually present. next_value must be
-- greater than max_id, or the next insert collides. If it is not, the fix is
-- setval - see the bottom of seeds/muscle_groups_and_exercises.sql.
SELECT c.relname AS table_name,
       s.last_value,
       pg_sequence_last_value(seq.oid) AS current_value
FROM pg_class seq
JOIN pg_depend d  ON d.objid = seq.oid AND d.deptype = 'i'
JOIN pg_class c   ON c.oid = d.refobjid
JOIN pg_sequences s ON s.sequencename = seq.relname
WHERE seq.relkind = 'S'
ORDER BY c.relname;

-- What the schema currently looks like.
SELECT table_name,
       pg_size_pretty(pg_total_relation_size(quote_ident(table_name))) AS total_size
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
ORDER BY table_name;

-- Every index, and whether anything has ever used it.
SELECT relname AS table_name, indexrelname AS index_name,
       idx_scan AS times_used, pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes
ORDER BY idx_scan, relname;
