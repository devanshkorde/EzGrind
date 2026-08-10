-- =====================================================================
-- 003_new_tables.sql
-- =====================================================================
-- Tables for features that are not built yet. Created empty; no application
-- code reads or writes them at this point.
--
-- Both use CREATE TABLE IF NOT EXISTS, so re-running is harmless.
--
-- Applied by: mysql -u root -p ezgrind_db < 003_new_tables.sql
-- =====================================================================

USE ezgrind_db;


-- ---------------------------------------------------------------------
-- weight_logs
--   Bodyweight over time. users.weight_kg holds only the current value and is
--   overwritten, so it cannot answer "am I trending up or down" - which is
--   the entire point of a weight goal.
--
--   UNIQUE (user_id, logged_on) means one reading per person per day: a second
--   entry corrects the first rather than stacking, so a nervous morning of
--   re-weighing cannot skew a trend line.
--
--   Cascades on user delete: a weight reading with no owner is garbage.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS weight_logs (
    log_id     INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NOT NULL,
    logged_on  DATE NOT NULL,
    weight_kg  DECIMAL(5,2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_weight_logs_user_day UNIQUE (user_id, logged_on),
    CONSTRAINT fk_weight_logs_user FOREIGN KEY (user_id)
        REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- ---------------------------------------------------------------------
-- personal_records
--   Best effort per user per exercise.
--
--   This is a derived cache, not a source of truth. It must always be
--   rebuildable from workout_sets - see the rebuild query in
--   Database/queries/scratch.sql. If it ever disagrees with the sets, the
--   sets win: truncate and rebuild.
--
--   estimated_1rm is stored rather than computed on read because the formula
--   may change; a stored value records what was claimed at the time.
--
--   exercise_id does NOT cascade: deleting an exercise that somebody has a PR
--   on should fail loudly and make a human decide.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS personal_records (
    pr_id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id       INT NOT NULL,
    exercise_id   INT NOT NULL,
    best_weight   DECIMAL(6,2) NOT NULL,
    best_reps     SMALLINT UNSIGNED NOT NULL,
    estimated_1rm DECIMAL(6,2) NOT NULL,
    achieved_on   DATE NOT NULL,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                            ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT uq_personal_records_user_exercise UNIQUE (user_id, exercise_id),
    CONSTRAINT fk_personal_records_user FOREIGN KEY (user_id)
        REFERENCES users(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_personal_records_exercise FOREIGN KEY (exercise_id)
        REFERENCES exercises(exercise_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
