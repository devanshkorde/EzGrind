-- =====================================================================
-- 007_password_reset.sql
-- =====================================================================
-- Password reset tokens, and the column that makes "log out my other
-- sessions" possible.
--
-- ADDITIVE ONLY. No existing row is touched and no password is
-- invalidated. Every current account keeps its hash and keeps working:
-- the new policy runs when a password is WRITTEN, never when one is
-- CHECKED, and login only checks.
--
-- Idempotent, same information_schema guard as 002-006.
--
-- Applied by: mysql -u root -p ezgrind_db < 007_password_reset.sql
-- =====================================================================

USE ezgrind_db;


-- ---------------------------------------------------------------------
-- 1. users.password_changed_at
--
--    Flask sessions are signed cookies held by the client. There is no
--    server-side session store to delete from, so "invalidate this
--    user's other sessions" needs a value the server can compare
--    against. login_user() stamps the login time into the session;
--    auth.current_user_id() rejects any session stamped before this
--    column. Setting it therefore kills every cookie issued earlier.
--
--    NULL by default and left NULL for existing rows, so nobody who is
--    currently signed in is thrown out by applying this migration.
-- ---------------------------------------------------------------------
SET @ddl := IF(
    (SELECT COUNT(*) FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users'
        AND COLUMN_NAME = 'password_changed_at') > 0,
    'DO 0',
    'ALTER TABLE users ADD COLUMN password_changed_at DATETIME NULL DEFAULT NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- ---------------------------------------------------------------------
-- 2. password_reset_tokens
--
--    token_hash is CHAR(64): the hex SHA-256 of the token that was
--    emailed. The raw token is never stored. A database dump, a backup
--    or an injection that reads this table yields nothing that can be
--    put in a URL.
--
--    No salt on the hash, deliberately. The input is
--    secrets.token_urlsafe(32) - 256 bits - so there is no dictionary to
--    precompute against, and a per-row salt would destroy the indexed
--    lookup that makes redemption a single seek.
--
--    used_at is written out as DATETIME NULL DEFAULT NULL rather than
--    left implicit. MySQL auto-initialises the FIRST timestamp-family
--    column in a table to DEFAULT CURRENT_TIMESTAMP unless told
--    otherwise; left implicit, every token would be born already spent.
--
--    requested_ip is VARCHAR(45): long enough for a full IPv6 address
--    including an IPv4-mapped form.
--
--    ON DELETE CASCADE: a deleted account's pending tokens are worthless
--    and must not outlive it. That is the one place cascading is right
--    here - unlike workouts, which stay RESTRICT so a training history
--    can only be destroyed deliberately.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token_id      INT AUTO_INCREMENT PRIMARY KEY,
    user_id       INT NOT NULL,
    token_hash    CHAR(64) NOT NULL,
    expires_at    DATETIME NOT NULL,
    used_at       DATETIME NULL DEFAULT NULL,
    requested_ip  VARCHAR(45) NULL DEFAULT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_reset_tokens_user
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- ---------------------------------------------------------------------
-- 3. Indexes
--
--    idx_reset_tokens_hash serves redemption and validation, the only
--    hot path: one seek from a link click.
--
--    idx_reset_tokens_user_used serves invalidation - "spend this user's
--    other unused tokens" - which runs on every request and every
--    successful reset.
--
--    Not UNIQUE on token_hash: a collision is impossible in practice,
--    and a UNIQUE constraint would turn that impossibility into a 500 on
--    a password reset rather than something the application can reason
--    about.
-- ---------------------------------------------------------------------
SET @ddl := IF(
    (SELECT COUNT(*) FROM information_schema.STATISTICS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'password_reset_tokens'
        AND INDEX_NAME = 'idx_reset_tokens_hash') > 0,
    'DO 0',
    'ALTER TABLE password_reset_tokens ADD INDEX idx_reset_tokens_hash (token_hash)');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl := IF(
    (SELECT COUNT(*) FROM information_schema.STATISTICS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'password_reset_tokens'
        AND INDEX_NAME = 'idx_reset_tokens_user_used') > 0,
    'DO 0',
    'ALTER TABLE password_reset_tokens ADD INDEX idx_reset_tokens_user_used (user_id, used_at)');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
