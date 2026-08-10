"""Password reset tokens: issue, inspect, redeem, invalidate.

The raw token exists in exactly two places - the link in the email, and the
return value of issue(). The database stores only its SHA-256. Someone who
reads every row of this table walks away with nothing they can put in a URL,
which is the entire point: a leaked backup must not be a set of working reset
links.
"""

import hashlib
import hmac
import secrets
from datetime import datetime

from db import get_cursor

# 32 bytes -> a 43-character URL-safe string. An attacker submitting a million
# guesses a second is still astronomically far from a hit inside a 20-minute
# window, so no lockout on redemption is load-bearing.
TOKEN_BYTES = 32


def _hash(raw_token):
    """SHA-256 hex of the raw token. Unsalted, deliberately.

    A password hash needs a salt and a work factor because passwords are
    low-entropy and guessable. This input is 256 bits from secrets - there is
    no dictionary to precompute against, nothing worth slowing down, and a
    per-row salt would force a table scan on every redemption instead of one
    indexed seek.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _lock_user(cursor, user_id):
    """Take the account row before touching any of its tokens.

    Every mutating function here calls this first, which is what makes them
    deadlock-free. Without it, "UPDATE ... WHERE user_id = X" followed by an
    INSERT takes row and gap locks on idx_reset_tokens_user_used in an order
    that depends on what is already in the table - so two requests for the same
    account, arriving together, can each hold what the other needs.

    That is not hypothetical: it fired as MySQL error 1213 the first time two
    resets were requested for one user within the same instant. The rate limit
    (3/hour/email) makes it rare, not impossible - two clicks on the same button
    are one HTTP round trip apart.

    One row, always the same row, always taken first. There is nothing left to
    deadlock against.
    """
    cursor.execute("SELECT user_id FROM users WHERE user_id = %s FOR UPDATE",
                   (user_id,))
    cursor.fetchall()


def issue(user_id, ttl, requested_ip=None):
    """Mint a token, kill the user's earlier unused ones, return the raw value.

    All three statements share one transaction, so there is never a moment where
    the old tokens are dead and the new one does not exist yet.

    Old tokens are marked used rather than deleted. A row saying "issued 09:00,
    superseded 09:02" is an audit trail; a row that has vanished is not. It also
    means someone clicking the link from an older email gets the honest "this
    link is no longer valid" rather than a bare "unknown token".
    """
    raw_token = secrets.token_urlsafe(TOKEN_BYTES)
    expires_at = datetime.now() + ttl

    with get_cursor(dictionary=False) as cursor:
        _lock_user(cursor, user_id)

        cursor.execute("""
            UPDATE password_reset_tokens SET used_at = NOW()
            WHERE user_id = %s AND used_at IS NULL
        """, (user_id,))

        cursor.execute("""
            INSERT INTO password_reset_tokens
                (user_id, token_hash, expires_at, requested_ip)
            VALUES (%s, %s, %s, %s)
        """, (user_id, _hash(raw_token), expires_at, requested_ip))

    return raw_token


def classify(raw_token):
    """(status, row) where status is valid | invalid | used | expired.

    Distinguishing these is safe to report to whoever holds the link: knowing
    that a token you already possess is expired rather than fabricated tells you
    nothing about anyone else's account, and it is the difference between
    "request a new link" and "something is broken".

    Called by the validate endpoint on page LOAD, so an expired link is reported
    before anyone types a password twice.
    """
    row = _lookup(raw_token)
    if row is None:
        return "invalid", None
    if row["used_at"] is not None:
        return "used", row
    if row["expires_at"] < datetime.now():
        return "expired", row
    return "valid", row


def _lookup(raw_token):
    """Find by hash, then confirm with a constant-time compare.

    The WHERE clause has already matched on the hash, so compare_digest is belt
    and braces here - but it is the line that stays correct if this ever changes
    to scanning candidate rows, and it costs nothing.
    """
    if not raw_token:
        return None

    token_hash = _hash(raw_token)
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT token_id, user_id, token_hash, expires_at, used_at, created_at
            FROM password_reset_tokens
            WHERE token_hash = %s
            LIMIT 1
        """, (token_hash,))
        row = cursor.fetchone()

    if row is None:
        return None
    if not hmac.compare_digest(row["token_hash"], token_hash):
        return None
    return row


def redeem(token_id, user_id):
    """Spend this token and every other outstanding one for the same user.

    Returns False if something already spent it.

    `used_at IS NULL` is in the WHERE clause, so two clicks arriving together
    cannot both succeed - the second updates zero rows. Checking in Python and
    then writing would leave a window between the two.

    The second statement is what makes a reset final: any other link sitting in
    the user's inbox dies with it.
    """
    with get_cursor(dictionary=False) as cursor:
        # Same lock, same order as issue(). A reset landing at the same instant
        # as a new request must queue behind it, not race it.
        _lock_user(cursor, user_id)

        cursor.execute("""
            UPDATE password_reset_tokens SET used_at = NOW()
            WHERE token_id = %s AND used_at IS NULL
        """, (token_id,))
        if cursor.rowcount != 1:
            return False

        cursor.execute("""
            UPDATE password_reset_tokens SET used_at = NOW()
            WHERE user_id = %s AND used_at IS NULL
        """, (user_id,))
        return True


def invalidate_all(user_id):
    """Spend every outstanding token for a user without redeeming one."""
    with get_cursor(dictionary=False) as cursor:
        _lock_user(cursor, user_id)
        cursor.execute("""
            UPDATE password_reset_tokens SET used_at = NOW()
            WHERE user_id = %s AND used_at IS NULL
        """, (user_id,))
        return cursor.rowcount


def purge_expired(before=None):
    """Delete spent and expired rows. Housekeeping, wired to nothing yet.

    Here because the table only grows otherwise. Not scheduled: this project has
    no job runner, and inventing one for a table that gains a row per forgotten
    password would be building infrastructure ahead of the need.
    """
    cutoff = before or datetime.now()
    with get_cursor(dictionary=False) as cursor:
        cursor.execute("""
            DELETE FROM password_reset_tokens
            WHERE expires_at < %s OR used_at IS NOT NULL
        """, (cutoff,))
        return cursor.rowcount
