"""Queries against workouts and workout_sets."""

from db import get_cursor


def _upsert_personal_record(cursor, user_id, exercise_id, weight, reps):
    """Keep personal_records in step with the set just inserted.

    Runs on the caller's cursor, so it shares the set insert's transaction: the
    set and the record it implies can never disagree, and a failure rolls both
    back together.

    ASSIGNMENT ORDER IS LOAD-BEARING. MySQL evaluates ON DUPLICATE KEY UPDATE
    left to right, so estimated_1rm must be assigned LAST. Put it first and
    every comparison after it comes out false - because it would be testing the
    value just written against itself - leaving a row whose 1RM disagrees with
    its own weight and reps.

    Stored values are qualified with the table name. Under the `AS new` row
    alias a bare column name is ambiguous between the incoming row and the
    existing one, and MySQL rejects it outright.
    """
    cursor.execute("""
        INSERT INTO personal_records
            (user_id, exercise_id, best_weight, best_reps, estimated_1rm, achieved_on)
        VALUES (%s, %s, %s, %s, ROUND(%s * (1 + %s / 30), 2), CURDATE()) AS new
        ON DUPLICATE KEY UPDATE
            best_weight = IF(new.estimated_1rm > personal_records.estimated_1rm,
                             new.best_weight, personal_records.best_weight),
            best_reps = IF(new.estimated_1rm > personal_records.estimated_1rm,
                           new.best_reps, personal_records.best_reps),
            achieved_on = IF(new.estimated_1rm > personal_records.estimated_1rm,
                             new.achieved_on, personal_records.achieved_on),
            estimated_1rm = IF(new.estimated_1rm > personal_records.estimated_1rm,
                               new.estimated_1rm, personal_records.estimated_1rm)
    """, (user_id, exercise_id, weight, reps, weight, reps))


def log_set(user_id, exercise_id, weight, reps, comments):
    """Find or create today's workout, then append one set to it.

    REQUIRES migration 002: the upsert depends on UNIQUE (user_id, workout_date),
    and set_order must exist. Without the constraint every call inserts a fresh
    workout row instead of reusing the day's.

    The previous SELECT-then-INSERT left a window where two near-simultaneous
    submissions both saw "no workout today" and both created one. The upsert
    closes it: the database decides, not the application. LAST_INSERT_ID() is
    what makes lastrowid return the existing row's id on the duplicate branch
    as well as on the insert branch.

    All three statements share one transaction, so a failed set insert cannot
    strand an empty workout row.
    """
    with get_cursor(dictionary=False) as cursor:
        cursor.execute("""
            INSERT INTO workouts (user_id, workout_date)
            VALUES (%s, CURDATE())
            ON DUPLICATE KEY UPDATE workout_id = LAST_INSERT_ID(workout_id)
        """, (user_id,))
        workout_id = cursor.lastrowid

        cursor.execute(
            "SELECT COALESCE(MAX(set_order), 0) + 1 FROM workout_sets WHERE workout_id = %s",
            (workout_id,)
        )
        set_order = cursor.fetchone()[0]

        # time_under_tension is intentionally not written: the input was
        # removed in migration 004, but the column and its history remain.
        cursor.execute("""
            INSERT INTO workout_sets
            (workout_id, exercise_id, weight, reps, comments, set_order)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (workout_id, exercise_id, weight, reps, comments, set_order))
        set_id = cursor.lastrowid

        # A bodyweight set has no weight, so it implies no 1RM and no record -
        # personal_records.best_weight is NOT NULL.
        if weight is not None and reps:
            _upsert_personal_record(cursor, user_id, exercise_id, weight, reps)

        return {
            "workout_id": workout_id,
            "set_id": set_id,
            "set_order": set_order,
        }


def today_sets(user_id):
    """Every individual set logged today, in the order performed.

    today_summary() groups by exercise and cannot address a single set;
    the logger needs set_id to delete, and created_at to show elapsed time.
    """
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT ws.set_id, ws.exercise_id, e.exercise_name,
                   ws.weight, ws.reps, ws.comments, ws.set_order, ws.created_at
            FROM workout_sets ws
            JOIN workouts w  ON w.workout_id = ws.workout_id
            JOIN exercises e ON e.exercise_id = ws.exercise_id
            WHERE w.user_id = %s AND w.workout_date = CURDATE()
            ORDER BY ws.set_order
        """, (user_id,))
        return cursor.fetchall()


def _recompute_personal_record(cursor, user_id, exercise_id):
    """Rebuild one exercise's record from whatever sets remain.

    Runs on the caller's cursor, inside the delete's transaction.

    Without this, deleting a set leaves behind the record it created - and a
    mistyped weight is the single most common reason to delete a set, so the
    bogus record would be exactly the one that survives. Someone who fat-fingers
    600kg instead of 60kg would carry that PR forever.

    Delete-then-insert rather than an upsert: if no weighted set is left, the
    exercise correctly ends up with no record at all.
    """
    cursor.execute(
        "DELETE FROM personal_records WHERE user_id = %s AND exercise_id = %s",
        (user_id, exercise_id)
    )
    cursor.execute("""
        INSERT INTO personal_records
            (user_id, exercise_id, best_weight, best_reps, estimated_1rm, achieved_on)
        SELECT %s, %s, ws.weight, ws.reps,
               ROUND(ws.weight * (1 + ws.reps / 30), 2), w.workout_date
        FROM workout_sets ws
        JOIN workouts w ON w.workout_id = ws.workout_id
        WHERE w.user_id = %s AND ws.exercise_id = %s
          AND ws.weight IS NOT NULL AND ws.reps IS NOT NULL
        ORDER BY ws.weight * (1 + ws.reps / 30) DESC, w.workout_date ASC
        LIMIT 1
    """, (user_id, exercise_id, user_id, exercise_id))


def delete_set(user_id, set_id):
    """Delete one set, but only if it belongs to this user. Returns success.

    Ownership is in the WHERE clause of both statements rather than checked
    once and trusted, so there is no window between checking and deleting.
    """
    with get_cursor(dictionary=False) as cursor:
        # Which exercise the set belonged to, needed to rebuild its record.
        # Scoped to the user, so this cannot be used to probe other accounts.
        cursor.execute("""
            SELECT ws.exercise_id
            FROM workout_sets ws
            JOIN workouts w ON w.workout_id = ws.workout_id
            WHERE ws.set_id = %s AND w.user_id = %s
        """, (set_id, user_id))
        row = cursor.fetchone()
        if not row:
            return False
        exercise_id = row[0]

        cursor.execute("""
            DELETE ws FROM workout_sets ws
            JOIN workouts w ON w.workout_id = ws.workout_id
            WHERE ws.set_id = %s AND w.user_id = %s
        """, (set_id, user_id))

        if cursor.rowcount == 0:
            return False

        _recompute_personal_record(cursor, user_id, exercise_id)
        return True


def exercise_stats(user_id, exercise_id, recent_limit=10):
    """One user's record on one exercise.

    Always scoped to user_id through the workouts join - there is no code path
    here that can return another account's numbers.

    Three queries rather than one: the totals, the single best set, and the
    recent list answer different shapes of question, and MySQL has no clean way
    to return a scalar aggregate and two row sets together. All three are
    constant-cost for one user and one exercise.
    """
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) AS total_sets,
                   MAX(w.workout_date) AS last_performed
            FROM workout_sets ws
            JOIN workouts w ON w.workout_id = ws.workout_id
            WHERE w.user_id = %s AND ws.exercise_id = %s
        """, (user_id, exercise_id))
        totals = cursor.fetchone()

        if not totals or totals["total_sets"] == 0:
            return {
                "total_sets": 0,
                "last_performed": None,
                "best_set": None,
                "estimated_1rm": None,
                "recent_sets": [],
            }

        # Epley, ranked in SQL so "best" is decided once and consistently.
        cursor.execute("""
            SELECT ws.weight, ws.reps, w.workout_date,
                   ROUND(ws.weight * (1 + ws.reps / 30), 2) AS estimated_1rm
            FROM workout_sets ws
            JOIN workouts w ON w.workout_id = ws.workout_id
            WHERE w.user_id = %s AND ws.exercise_id = %s
              AND ws.weight IS NOT NULL AND ws.reps IS NOT NULL
            ORDER BY estimated_1rm DESC, w.workout_date ASC
            LIMIT 1
        """, (user_id, exercise_id))
        best = cursor.fetchone()

        cursor.execute("""
            SELECT ws.set_id, ws.weight, ws.reps, ws.comments,
                   ws.set_order, w.workout_date
            FROM workout_sets ws
            JOIN workouts w ON w.workout_id = ws.workout_id
            WHERE w.user_id = %s AND ws.exercise_id = %s
            ORDER BY w.workout_date DESC, ws.set_order DESC
            LIMIT %s
        """, (user_id, exercise_id, recent_limit))
        recent = cursor.fetchall()

    return {
        "total_sets": totals["total_sets"],
        "last_performed": totals["last_performed"],
        "best_set": None if not best else {
            "weight": float(best["weight"]),
            "reps": best["reps"],
            "workout_date": best["workout_date"],
        },
        "estimated_1rm": None if not best else float(best["estimated_1rm"]),
        "recent_sets": [{
            "set_id": row["set_id"],
            "weight": float(row["weight"]) if row["weight"] is not None else None,
            "reps": row["reps"],
            "comments": row["comments"],
            "set_order": row["set_order"],
            "workout_date": row["workout_date"],
        } for row in recent],
    }


def last_set_for_exercise(user_id, exercise_id):
    """The most recent set this user logged for an exercise, or None."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT ws.weight, ws.reps, w.workout_date
            FROM workout_sets ws
            JOIN workouts w ON w.workout_id = ws.workout_id
            WHERE w.user_id = %s AND ws.exercise_id = %s
            ORDER BY w.workout_date DESC, ws.set_order DESC
            LIMIT 1
        """, (user_id, exercise_id))
        return cursor.fetchone()


def recent_exercises(user_id, limit=5):
    """The exercises this user logged most recently, most recent first.

    Exists because the catalogue is now ~2,900 rows: scrolling to find the lift
    you did on Monday is worse than being handed it. Most people rotate through
    a small set of movements, so the top of that rotation is almost always what
    the picker should offer first.

    MAX(workout_date) rather than a plain DISTINCT so the ordering is by when
    the exercise was last done, not by which row the join happened to reach.
    """
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT e.exercise_id, e.exercise_name, e.equipment,
                   m.muscle_id, m.muscle_name, m.image_path,
                   MAX(w.workout_date) AS last_performed
            FROM workouts w
            JOIN workout_sets ws ON ws.workout_id = w.workout_id
            JOIN exercises e ON e.exercise_id = ws.exercise_id
            JOIN muscle_groups m ON m.muscle_id = e.muscle_id
            WHERE w.user_id = %s
            GROUP BY e.exercise_id, e.exercise_name, e.equipment,
                     m.muscle_id, m.muscle_name, m.image_path
            ORDER BY last_performed DESC, e.exercise_name
            LIMIT %s
        """, (user_id, limit))
        return cursor.fetchall()


def today_summary(user_id):
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT e.exercise_name, COUNT(ws.set_id) AS total_sets
            FROM workouts w
            JOIN workout_sets ws ON w.workout_id = ws.workout_id
            JOIN exercises e ON ws.exercise_id = e.exercise_id
            WHERE w.user_id = %s AND w.workout_date = CURDATE()
            GROUP BY e.exercise_name
        """, (user_id,))
        return cursor.fetchall()


def _session_filter(user_id, date_from, date_to, muscle_id, exercise_id):
    """SQL fragments selecting which workouts match the caller's filters.

    A muscle or exercise filter has to reach into the set tables to decide
    whether a session qualifies, so those joins are added only when asked
    for - an unfiltered page never pays for them.

    Filters choose which *sessions* appear; every set in a matching session is
    then returned. Filtering the sets too would show a "Chest" filter hiding
    half of a day that genuinely was a chest day.
    """
    joins = ""
    where = ["w.user_id = %s"]
    params = [user_id]

    if muscle_id or exercise_id:
        joins = (" JOIN workout_sets fs ON fs.workout_id = w.workout_id"
                 " JOIN exercises fe ON fe.exercise_id = fs.exercise_id")

    if date_from:
        where.append("w.workout_date >= %s")
        params.append(date_from)
    if date_to:
        where.append("w.workout_date <= %s")
        params.append(date_to)
    if muscle_id:
        where.append("fe.muscle_id = %s")
        params.append(muscle_id)
    if exercise_id:
        where.append("fs.exercise_id = %s")
        params.append(exercise_id)

    return joins, " AND ".join(where), params


def _assemble_sessions(rows):
    """Fold a flat set list into sessions -> exercises -> sets.

    Rows arrive ordered by date desc, exercise, set order, and Python dicts
    keep insertion order, so nothing needs re-sorting here.
    """
    sessions = {}

    for row in rows:
        date = row["workout_date"]

        if date not in sessions:
            sessions[date] = {
                "workout_date": date,
                "total_sets": 0,
                "total_volume": 0.0,
                "exercise_count": 0,
                "duration_estimate": 0,
                "exercises": {},
                "_first": row["created_at"],
                "_last": row["created_at"],
            }
        session = sessions[date]

        name = row["exercise_name"]
        if name not in session["exercises"]:
            session["exercises"][name] = {
                "exercise_id": row["exercise_id"],
                "exercise_name": name,
                "muscle_name": row["muscle_name"],
                "sets": [],
            }

        session["exercises"][name]["sets"].append({
            "set_id": row["set_id"],
            "weight": float(row["weight"]) if row["weight"] is not None else None,
            "reps": row["reps"],
            "tut": row["time_under_tension"],
            "comments": row["comments"],
            "set_order": row["set_order"],
        })

        session["total_sets"] += 1
        session["total_volume"] += float(row["weight"] or 0) * (row["reps"] or 0)

        stamp = row["created_at"]
        if stamp is not None:
            if session["_first"] is None or stamp < session["_first"]:
                session["_first"] = stamp
            if session["_last"] is None or stamp > session["_last"]:
                session["_last"] = stamp

    result = []
    for session in sessions.values():
        first, last = session.pop("_first"), session.pop("_last")
        # Zero for anything logged before per-set timestamps existed: migration
        # 002 backfilled those from the parent workout, so they all share one
        # stamp. Real sessions from now on carry a real spread.
        if first and last:
            session["duration_estimate"] = int((last - first).total_seconds() // 60)

        session["exercise_count"] = len(session["exercises"])
        session["exercises"] = list(session["exercises"].values())
        session["total_volume"] = round(session["total_volume"], 2)
        result.append(session)

    return result


def sessions(user_id, page=1, limit=20, date_from=None, date_to=None,
             muscle_id=None, exercise_id=None):
    """One page of training sessions, newest first, plus the total available.

    Two queries, both O(1) in the page size:
      1. how many sessions match the filters, for the pagination meta
      2. the page of workout ids, joined out to every set they contain

    The page is chosen in a derived table so the set join runs against a
    bounded set of workouts. A derived table rather than IN (... LIMIT ...)
    because MySQL still rejects LIMIT inside an IN subquery.

    There is deliberately no query inside a loop: the flat result is folded
    into sessions by _assemble_sessions in a single pass.
    """
    joins, where, params = _session_filter(
        user_id, date_from, date_to, muscle_id, exercise_id
    )
    offset = (page - 1) * limit

    with get_cursor() as cursor:
        cursor.execute(f"""
            SELECT COUNT(DISTINCT w.workout_id) AS total
            FROM workouts w{joins}
            WHERE {where}
        """, params)
        total = cursor.fetchone()["total"]

        cursor.execute(f"""
            SELECT page.workout_date,
                   ws.set_id, ws.weight, ws.reps, ws.time_under_tension,
                   ws.comments, ws.set_order, ws.created_at,
                   e.exercise_id, e.exercise_name, m.muscle_name
            FROM (
                SELECT DISTINCT w.workout_id, w.workout_date
                FROM workouts w{joins}
                WHERE {where}
                ORDER BY w.workout_date DESC
                LIMIT %s OFFSET %s
            ) AS page
            JOIN workout_sets ws ON ws.workout_id = page.workout_id
            JOIN exercises e     ON e.exercise_id = ws.exercise_id
            JOIN muscle_groups m ON m.muscle_id = e.muscle_id
            ORDER BY page.workout_date DESC, e.exercise_name, ws.set_order
        """, params + [limit, offset])
        rows = cursor.fetchall()

    return _assemble_sessions(rows), total
