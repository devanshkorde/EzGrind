-- =====================================================================
-- 008_password_changed_precision.sql
-- =====================================================================
-- Widens users.password_changed_at from DATETIME to DATETIME(6).
--
-- WHY THIS EXISTS
--   007 created the column as plain DATETIME, which stores whole seconds
--   and silently truncates the fraction. Sessions carry their start time
--   as a float, so the comparison in auth._session_is_current became:
--
--       session started 17:30:45.700  >=  password changed 17:30:45.000
--
--   which is TRUE - and the session that should have been ended survived.
--   Any session opened in the same second as a password reset stayed
--   signed in. Caught by the "sessions elsewhere are ended" case, which
--   does exactly that inside one second.
--
--   DATETIME(6) keeps microseconds, so the two values order correctly and
--   the check does what it says.
--
-- ADDITIVE AND NON-DESTRUCTIVE. Widening precision cannot lose data: every
-- existing value keeps its seconds and gains .000000. No row is rewritten
-- in a way that changes its meaning, and nobody is signed out by applying
-- this - a NULL stays NULL.
--
-- Idempotent: the guard checks DATETIME_PRECISION, so re-running is a
-- no-op rather than a second ALTER.
--
-- Applied by: mysql -u root -p ezgrind_db < 008_password_changed_precision.sql
-- =====================================================================

USE ezgrind_db;

SET @ddl := IF(
    (SELECT COALESCE(DATETIME_PRECISION, 0) FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users'
        AND COLUMN_NAME = 'password_changed_at') = 6,
    'DO 0',
    'ALTER TABLE users MODIFY COLUMN password_changed_at DATETIME(6) NULL DEFAULT NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
