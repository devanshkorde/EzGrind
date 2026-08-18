"""The bodyweight log, and keeping users.weight_kg in step with it.

Every function takes user_id as its first positional argument and puts it in the
WHERE clause. Nothing here reads a session or accepts an identity from anywhere
else.
"""

from datetime import date, timedelta

from db import get_cursor

CHANGE_WINDOW_DAYS = 30


def _resync_profile_weight(cursor, user_id):
    """Point users.weight_kg at this user's most recent log.

    Deliberately NOT "the value just written". Two cases break that reading:
    a backdated entry must not overwrite the current weight, and deleting the
    newest log has to roll the profile back to the one before it. Both are
    wrong if this copies whatever was last touched.

    Does nothing when no logs remain, so deleting every entry leaves the figure
    the user typed at signup rather than nulling their profile and their BMI.

    Runs on the caller's cursor, inside the caller's transaction.

    The SET target is bare weight_kg, not u.weight_kg. Postgres accepts the
    table alias everywhere else in the statement but rejects it on the left of
    an assignment - the column being set is never ambiguous, so qualifying it
    is a syntax error rather than a clarification.
    """
    cursor.execute("""
        UPDATE users u
           SET weight_kg = (
                   SELECT wl.weight_kg
                   FROM weight_logs wl
                   WHERE wl.user_id = u.user_id
                   ORDER BY wl.logged_on DESC
                   LIMIT 1
               )
         WHERE u.user_id = %s
           AND EXISTS (SELECT 1 FROM weight_logs w2 WHERE w2.user_id = u.user_id)
    """, (user_id,))


def log_weight(user_id, weight_kg, logged_on=None):
    """Record one day's weight. Logging twice in a day corrects, not duplicates.

    The unique key on (user_id, logged_on) is what makes that true - the upsert
    leans on the constraint rather than on a check-then-insert that could race.

    RETURNING replaces the follow-up SELECT this needed under MySQL, where
    lastrowid was meaningless on the duplicate-key branch and the row had to be
    read back by hand. One statement now answers both "write it" and "what does
    it say", so there is no window between them and one less round trip.

    The default date is resolved in Python rather than with CURRENT_DATE, so
    "today" here is the same day stats_repo counts streaks against.
    """
    logged_on = logged_on or date.today()

    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO weight_logs (user_id, logged_on, weight_kg)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, logged_on) DO UPDATE
                SET weight_kg = EXCLUDED.weight_kg
            RETURNING log_id, logged_on, weight_kg
        """, (user_id, logged_on, weight_kg))
        row = cursor.fetchone()

        _resync_profile_weight(cursor, user_id)

    return {
        "log_id": row["log_id"],
        "logged_on": row["logged_on"],
        "weight_kg": float(row["weight_kg"]),
    }


def list_logs(user_id, date_from=None, date_to=None, limit=None):
    """Entries oldest first - the chart is the primary consumer.

    A limit takes the NEWEST n and returns them oldest-first. Applying LIMIT to
    an ascending sort would hand back the oldest n instead, which is never what
    a caller asking for "the last 200" wants.
    """
    where = ["user_id = %s"]
    params = [user_id]

    if date_from:
        where.append("logged_on >= %s")
        params.append(date_from)
    if date_to:
        where.append("logged_on <= %s")
        params.append(date_to)

    clause = " AND ".join(where)

    if limit:
        sql = f"""
            SELECT log_id, logged_on, weight_kg FROM (
                SELECT log_id, logged_on, weight_kg
                FROM weight_logs
                WHERE {clause}
                ORDER BY logged_on DESC
                LIMIT %s
            ) AS recent
            ORDER BY logged_on ASC
        """
        params.append(limit)
    else:
        sql = f"""
            SELECT log_id, logged_on, weight_kg
            FROM weight_logs
            WHERE {clause}
            ORDER BY logged_on ASC
        """

    with get_cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    return [{
        "log_id": row["log_id"],
        "logged_on": row["logged_on"],
        "weight_kg": float(row["weight_kg"]),
    } for row in rows]


def delete_log(user_id, log_id):
    """Delete one entry, but only this user's. Returns success.

    Ownership is in the WHERE clause, so there is no window between checking
    and deleting and no path where a caller forgets the check.
    """
    with get_cursor(dictionary=False) as cursor:
        cursor.execute(
            "DELETE FROM weight_logs WHERE log_id = %s AND user_id = %s",
            (log_id, user_id)
        )
        if cursor.rowcount == 0:
            return False

        # The deleted row may have been the newest, so the profile figure it
        # was backing is now stale.
        _resync_profile_weight(cursor, user_id)
        return True


def summary_stats(user_id):
    """current_weight, starting_weight and the change over the window.

    None rather than 0 when there is nothing to compare: "you have not changed"
    and "there is not enough data to say" are different answers, and a card
    showing 0.0 kg for the second one is a lie.
    """
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT logged_on, weight_kg
            FROM weight_logs
            WHERE user_id = %s
            ORDER BY logged_on ASC
        """, (user_id,))
        rows = cursor.fetchall()

        cursor.execute("SELECT weight_kg FROM users WHERE user_id = %s", (user_id,))
        profile = cursor.fetchone()

    fallback = profile["weight_kg"] if profile else None

    if not rows:
        # Falls back to the signup figure so a user who never logged still sees
        # a current weight; there is still no history to derive a change from.
        return {
            "current_weight": float(fallback) if fallback else None,
            "starting_weight": None,
            "weight_change_30d": None,
        }

    current = float(rows[-1]["weight_kg"])
    cutoff = date.today() - timedelta(days=CHANGE_WINDOW_DAYS)

    # Best estimate of "weight 30 days ago" is the log closest to that date:
    # the last one before the window if there is one, otherwise the oldest
    # inside it. With a single entry there is no baseline distinct from the
    # current value, so the change is unknown.
    before_window = [row for row in rows if row["logged_on"] < cutoff]
    inside_window = [row for row in rows if row["logged_on"] >= cutoff]

    if before_window:
        baseline = before_window[-1]
    elif len(inside_window) >= 2:
        baseline = inside_window[0]
    else:
        baseline = None

    return {
        "current_weight": current,
        "starting_weight": float(rows[0]["weight_kg"]),
        "weight_change_30d": (
            round(current - float(baseline["weight_kg"]), 2) if baseline else None
        ),
    }
