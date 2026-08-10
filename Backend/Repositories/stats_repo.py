"""Aggregate statistics: streaks, totals, volume over time, personal records.

Read-only. Every function takes user_id as its first positional argument and
puts it in the WHERE clause; set-level queries reach the user by joining
through workouts. No function here reads a session, and no route above it
passes anything except session["user_id"], so there is no parameter a caller
could supply to read another account.
"""

from datetime import date, timedelta

from db import get_cursor
from repositories import weight_repo

# Rolling windows, not calendar boundaries: "this week" means the last seven
# days including today, not since Monday. Consistent across every endpoint.
PERIOD_DAYS = {"week": 7, "month": 30, "year": 365}

WEEK_DAYS = 7
MONTH_DAYS = 30


# ============================================================
# TRAINING DAYS
# ============================================================

def _training_days(user_id):
    """Every distinct day this user trained, newest first.

    A covering read: uq_workouts_user_date holds both columns, so this never
    touches the table itself. The result is bounded by days trained - a few
    hundred rows after years of use - which is small enough to hand to Python,
    where the streak rules read far more clearly than they would in SQL.
    """
    with get_cursor(dictionary=False) as cursor:
        cursor.execute("""
            SELECT DISTINCT workout_date
            FROM workouts
            WHERE user_id = %s
            ORDER BY workout_date DESC
        """, (user_id,))
        return [row[0] for row in cursor.fetchall()]


def _current_streak(days):
    """Consecutive calendar days with at least one logged set, counting back
    from today.

    A session logged today OR yesterday keeps the streak alive, so a user does
    not watch it drop to zero partway through a day they simply have not
    trained yet.

    KNOWN LIMITATION: "today" is the database server's date, not the user's.
    Someone training late in the evening from a timezone behind the server has
    that session filed under the following day. Invisible with one user in one
    timezone; real the moment there are two.
    """
    trained = set(days)
    cursor = date.today()

    if cursor not in trained:
        cursor -= timedelta(days=1)

    streak = 0
    while cursor in trained:
        streak += 1
        cursor -= timedelta(days=1)

    return streak


def _longest_streak(days):
    """The longest run of consecutive days anywhere in the history."""
    if not days:
        return 0

    ascending = sorted(set(days))
    longest = run = 1

    for previous, current in zip(ascending, ascending[1:]):
        run = run + 1 if (current - previous).days == 1 else 1
        longest = max(longest, run)

    return longest


def _week_activity(days):
    """The last seven days, oldest first, each flagged trained or not.

    Returned with the summary so the dot row does not need its own request.
    """
    trained = set(days)
    today = date.today()

    return [
        {
            "date": (today - timedelta(days=offset)).isoformat(),
            "trained": (today - timedelta(days=offset)) in trained,
        }
        for offset in range(WEEK_DAYS - 1, -1, -1)
    ]


# ============================================================
# SUMMARY
# ============================================================

def _set_totals(user_id):
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) AS total_sets,
                   COALESCE(SUM(ws.weight * ws.reps), 0) AS total_volume
            FROM workout_sets ws
            JOIN workouts w ON w.workout_id = ws.workout_id
            WHERE w.user_id = %s
        """, (user_id,))
        return cursor.fetchone()


def _favourite_muscle(user_id):
    """Most-trained muscle group by set count. None when nothing is logged.

    Ties break on name so the answer is stable between calls rather than
    depending on row order.
    """
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT m.muscle_name, COUNT(*) AS sets
            FROM workout_sets ws
            JOIN workouts w      ON w.workout_id = ws.workout_id
            JOIN exercises e     ON e.exercise_id = ws.exercise_id
            JOIN muscle_groups m ON m.muscle_id = e.muscle_id
            WHERE w.user_id = %s
            GROUP BY m.muscle_id, m.muscle_name
            ORDER BY sets DESC, m.muscle_name
            LIMIT 1
        """, (user_id,))
        row = cursor.fetchone()
        return row["muscle_name"] if row else None


def summary(user_id):
    days = _training_days(user_id)
    totals = _set_totals(user_id)
    today = date.today()

    total_workouts = len(days)
    total_sets = totals["total_sets"]

    week_cutoff = today - timedelta(days=WEEK_DAYS - 1)
    month_cutoff = today - timedelta(days=MONTH_DAYS - 1)

    stats = {
        "current_streak": _current_streak(days),
        "longest_streak": _longest_streak(days),
        "workouts_this_week": sum(1 for day in days if day >= week_cutoff),
        "workouts_this_month": sum(1 for day in days if day >= month_cutoff),
        "total_workouts": total_workouts,
        "total_sets": total_sets,
        "total_volume_kg": round(float(totals["total_volume"]), 1),
        "favourite_muscle_group": _favourite_muscle(user_id),
        "avg_sets_per_workout": (
            round(total_sets / total_workouts, 1) if total_workouts else 0
        ),
        "week_activity": _week_activity(days),
    }

    # current_weight, starting_weight, weight_change_30d. Owned by weight_repo
    # because it owns the table; merged here so the dashboard needs one request.
    stats.update(weight_repo.summary_stats(user_id))
    return stats


# ============================================================
# SERIES
# ============================================================

def volume_series(user_id, period):
    """Total volume over time: daily for week and month, monthly for year.

    Grouped in SQL rather than fetched raw, so the response is one point per
    bucket instead of one row per set.

    Monthly buckets use YEAR()/MONTH() and are assembled into an ISO date in
    Python. DATE_FORMAT would be the obvious choice, but its format string needs
    literal % characters, and those collide with the driver's own %s
    placeholders - escaping them as %% survives into MySQL, which then reads
    %%Y as a literal "%Y" and returns the format string instead of a date.
    """
    cutoff = date.today() - timedelta(days=PERIOD_DAYS[period] - 1)
    monthly = period == "year"

    selection = ("YEAR(w.workout_date) AS bucket_year,"
                 " MONTH(w.workout_date) AS bucket_month"
                 if monthly else "w.workout_date AS bucket_date")
    grouping = "bucket_year, bucket_month" if monthly else "bucket_date"

    with get_cursor() as cursor:
        cursor.execute(f"""
            SELECT {selection},
                   COALESCE(SUM(ws.weight * ws.reps), 0) AS volume,
                   COUNT(*) AS sets
            FROM workout_sets ws
            JOIN workouts w ON w.workout_id = ws.workout_id
            WHERE w.user_id = %s AND w.workout_date >= %s
            GROUP BY {grouping}
            ORDER BY {grouping}
        """, (user_id, cutoff))
        rows = cursor.fetchall()

    return [{
        "date": (f"{row['bucket_year']:04d}-{row['bucket_month']:02d}-01" if monthly
                 else row["bucket_date"].isoformat()),
        "volume": round(float(row["volume"]), 1),
        "sets": row["sets"],
    } for row in rows]


def muscle_distribution(user_id, period):
    """Set counts per muscle group over the period, with percentages."""
    cutoff = date.today() - timedelta(days=PERIOD_DAYS[period] - 1)

    with get_cursor() as cursor:
        cursor.execute("""
            SELECT m.muscle_id, m.muscle_name, COUNT(*) AS sets
            FROM workout_sets ws
            JOIN workouts w      ON w.workout_id = ws.workout_id
            JOIN exercises e     ON e.exercise_id = ws.exercise_id
            JOIN muscle_groups m ON m.muscle_id = e.muscle_id
            WHERE w.user_id = %s AND w.workout_date >= %s
            GROUP BY m.muscle_id, m.muscle_name
            ORDER BY sets DESC, m.muscle_name
        """, (user_id, cutoff))
        rows = cursor.fetchall()

    total = sum(row["sets"] for row in rows)

    return [{
        "muscle_id": row["muscle_id"],
        "muscle_name": row["muscle_name"],
        "sets": row["sets"],
        "percentage": round(row["sets"] / total * 100, 1) if total else 0,
    } for row in rows]


# ============================================================
# PERSONAL RECORDS
# ============================================================

def personal_records(user_id):
    """Best set per exercise, heaviest estimated 1RM first.

    Read from personal_records, which workout_repo.log_set maintains inside the
    set-insert transaction. The table is a cache: queries/scratch.sql holds the
    statement that rebuilds it from workout_sets if it ever drifts.
    """
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT pr.exercise_id, e.exercise_name, m.muscle_name,
                   pr.best_weight, pr.best_reps, pr.estimated_1rm,
                   pr.achieved_on, pr.updated_at
            FROM personal_records pr
            JOIN exercises e     ON e.exercise_id = pr.exercise_id
            JOIN muscle_groups m ON m.muscle_id = e.muscle_id
            WHERE pr.user_id = %s
            ORDER BY pr.estimated_1rm DESC, e.exercise_name
        """, (user_id,))
        rows = cursor.fetchall()

    return [{
        "exercise_id": row["exercise_id"],
        "exercise_name": row["exercise_name"],
        "muscle_name": row["muscle_name"],
        "best_weight": float(row["best_weight"]),
        "best_reps": row["best_reps"],
        "estimated_1rm": float(row["estimated_1rm"]),
        "achieved_on": row["achieved_on"],
    } for row in rows]
