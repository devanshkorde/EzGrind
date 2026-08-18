"""EXPLAIN every query the application runs, and say which index it used.

    python scripts/check_plans.py

Postgres plans differently from MySQL. An index that was load-bearing there can
be ignored here, and a composite index whose columns are in the wrong order for
this planner produces a correct answer at the wrong cost - which no test that
only checks results will ever notice. This is the check that notices.

READ-ONLY. The SELECTs run under EXPLAIN ANALYZE, so they really execute; the
two upserts run under plain EXPLAIN, which plans without executing, so nothing
here writes a row.

OUTCOMES
    ok      the expected index was used
    warn    a sequential scan on a table small enough that the planner is
            probably right - reported, not failed
    FAIL    the expected index was not used on a table big enough to care

Exits non-zero on any FAIL, so it can gate a deploy.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db import get_cursor  # noqa: E402

# Below this, a sequential scan is usually the cheapest plan and arguing with
# the planner about it is wrong. Above it, an unused index is a real finding.
SMALL_TABLE_ROWS = 500

PASSED, WARNED, FAILED = [], [], []


def explain(cursor, sql, params, analyze=True):
    mode = "ANALYZE, BUFFERS, " if analyze else ""
    cursor.execute(f"EXPLAIN ({mode}COSTS OFF) {sql}", params)
    return "\n".join(row[0] for row in cursor.fetchall())


def check(cursor, label, sql, params, expect_index, table_rows, analyze=True):
    """expect_index may be one index name or several acceptable ones.

    SEVERAL, because Postgres costs plans rather than following rules, and more
    than one plan can be right. A search for a common term under ORDER BY ...
    LIMIT 25 legitimately walks the ordering index and filters - it finds 25
    matches after skipping a few hundred rows, which beats building a bitmap
    over the trigram index and then sorting the result. Demanding one specific
    index there would be asserting a preference, not a property.

    What IS a property: some index is used, and it is not a sequential scan of
    a table big enough to hurt.
    """
    if isinstance(expect_index, str):
        expect_index = (expect_index,)

    try:
        plan = explain(cursor, sql, params, analyze)
    except Exception as exc:                                     # noqa: BLE001
        FAILED.append(label)
        print(f"  FAIL {label}\n       query failed: {exc}")
        return

    used = next((name for name in expect_index if name in plan), None)
    if used:
        PASSED.append(label)
        print(f"  ok   {label:<44} {used}")
        return

    if table_rows < SMALL_TABLE_ROWS:
        WARNED.append(label)
        print(f"  warn {label:<44} seq scan, table has {table_rows} rows")
        return

    FAILED.append(label)
    print(f"  FAIL {label:<44} expected one of {', '.join(expect_index)}")
    print("       " + plan.replace("\n", "\n       "))


def row_counts(cursor):
    counts = {}
    for table in ("users", "muscle_groups", "exercises", "workouts",
                  "workout_sets", "weight_logs", "personal_records",
                  "password_reset_tokens"):
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        counts[table] = cursor.fetchone()[0]
    return counts


def sample_ids(cursor):
    """A real user and exercise, so the plans are the ones users actually get.

    Planning against an id that matches nothing produces a plan for an empty
    result, which is not the plan worth checking.
    """
    cursor.execute("SELECT MIN(user_id) FROM users")
    user_id = cursor.fetchone()[0]
    cursor.execute("SELECT MIN(exercise_id) FROM exercises")
    exercise_id = cursor.fetchone()[0]
    return user_id, exercise_id


def main():
    with get_cursor(dictionary=False) as cursor:
        # Without stats the planner guesses, and a freshly loaded database has
        # none - which is the single most common reason a migration "loses" an
        # index. Doing it here means the numbers below describe the real thing.
        print("\n  collecting statistics (ANALYZE)...")
        cursor.execute("ANALYZE")

        counts = row_counts(cursor)
        user_id, exercise_id = sample_ids(cursor)

        print("\n  rows: " + "  ".join(f"{t}={n}" for t, n in counts.items()))

        if exercise_id is None:
            sys.exit("\n  No exercises. Apply the seed first - there is nothing"
                     " to plan against.")

        # The catalogue checks are the ones worth having: 2,900 rows is where
        # an unused index actually costs something. The user-scoped tables are
        # empty on a fresh database, and every plan over an empty table is a
        # sequential scan whatever the indexes say - so those are skipped
        # rather than reported as passes that prove nothing.
        scoped = user_id is not None

        print("\n-- catalogue -------------------------------------------------")

        check(cursor, "exercises page 1, sort=name", """
            SELECT e.exercise_id, e.exercise_name, m.muscle_name
            FROM exercises e JOIN muscle_groups m ON m.muscle_id = e.muscle_id
            ORDER BY e.exercise_name, e.muscle_id LIMIT 25
        """, (), "idx_exercises_name_muscle", counts["exercises"])

        check(cursor, "exercises keyset seek, sort=name", """
            SELECT e.exercise_id, e.exercise_name
            FROM exercises e
            WHERE (e.exercise_name > %s
                   OR (e.exercise_name = %s AND e.muscle_id > %s))
            ORDER BY e.exercise_name, e.muscle_id LIMIT 25
        """, ("Squat", "Squat", 0), "idx_exercises_name_muscle",
              counts["exercises"])

        check(cursor, "exercises keyset seek, sort=muscle", """
            SELECT e.exercise_id, e.exercise_name
            FROM exercises e
            WHERE (e.muscle_id > %s
                   OR (e.muscle_id = %s AND e.exercise_name > %s))
            ORDER BY e.muscle_id, e.exercise_name LIMIT 25
        """, (3, 3, "Bench Press"), "idx_exercises_muscle_name",
              counts["exercises"])

        # The combobox. A SELECTIVE term is where the trigram index has to
        # earn its place, and where a missing one would really hurt - so this
        # case demands it specifically.
        check(cursor, "search, selective term ('%zercher%')", """
            SELECT exercise_id, exercise_name FROM exercises
            WHERE exercise_name ILIKE %s
            ORDER BY exercise_name, muscle_id LIMIT 25
        """, ("%zercher%",), "idx_exercises_name_trgm", counts["exercises"])

        # Two partial words - what "bench pr" actually sends.
        check(cursor, "search, two terms ('%bench%' AND '%pr%')", """
            SELECT exercise_id, exercise_name FROM exercises
            WHERE exercise_name ILIKE %s AND exercise_name ILIKE %s
            ORDER BY exercise_name, muscle_id LIMIT 25
        """, ("%bench%", "%pr%"), "idx_exercises_name_trgm", counts["exercises"])

        # A term matching NOTHING is the case that would degenerate to a full
        # scan if the trigram index were missing or unusable.
        check(cursor, "search, no matches ('%qqqqzz%')", """
            SELECT exercise_id, exercise_name FROM exercises
            WHERE exercise_name ILIKE %s
            ORDER BY exercise_name, muscle_id LIMIT 25
        """, ("%qqqqzz%",), "idx_exercises_name_trgm", counts["exercises"])

        # A COMMON term is the one case where walking the ordering index and
        # filtering is genuinely cheaper than a bitmap plus a sort - matches
        # are dense, so LIMIT 25 is satisfied after a few hundred rows. Either
        # index is a correct answer; a sequential scan would not be.
        check(cursor, "search, common term ('%squ%')", """
            SELECT exercise_id, exercise_name FROM exercises
            WHERE exercise_name ILIKE %s
            ORDER BY exercise_name, muscle_id LIMIT 25
        """, ("%squ%",), ("idx_exercises_name_trgm", "idx_exercises_name_muscle"),
              counts["exercises"])

        # Without LIMIT there is no cheap early exit, so this is the shape that
        # actually tests whether the equipment index exists and is usable.
        check(cursor, "equipment filter (full result)", """
            SELECT exercise_id FROM exercises WHERE equipment = %s
        """, ("Barbell",), "idx_exercises_equipment", counts["exercises"])

        check(cursor, "exercise detail by id", """
            SELECT e.exercise_id, m.muscle_name
            FROM exercises e JOIN muscle_groups m ON m.muscle_id = e.muscle_id
            WHERE e.exercise_id = %s
        """, (exercise_id,), "exercises_pkey", counts["exercises"])

        if not scoped:
            print("\n-- training data, accounts, upserts --------------------------")
            print("  skipped: no users yet, so every user-scoped plan would be a")
            print("           sequential scan over an empty table. Sign up, log a")
            print("           set, and re-run to check these.")
            summarise()
            return

        print("\n-- training data ---------------------------------------------")

        check(cursor, "distinct training days (streaks)", """
            SELECT DISTINCT workout_date FROM workouts
            WHERE user_id = %s ORDER BY workout_date DESC
        """, (user_id,), "uq_workouts_user_date", counts["workouts"])

        check(cursor, "today's sets", """
            SELECT ws.set_id, e.exercise_name
            FROM workout_sets ws
            JOIN workouts w  ON w.workout_id = ws.workout_id
            JOIN exercises e ON e.exercise_id = ws.exercise_id
            WHERE w.user_id = %s AND w.workout_date = CURRENT_DATE
            ORDER BY ws.set_order
        """, (user_id,), "uq_workouts_user_date", counts["workout_sets"])

        check(cursor, "lifetime set totals", """
            SELECT COUNT(*), COALESCE(SUM(ws.weight * ws.reps), 0)
            FROM workout_sets ws
            JOIN workouts w ON w.workout_id = ws.workout_id
            WHERE w.user_id = %s
        """, (user_id,), "idx_workout_sets_workout", counts["workout_sets"])

        check(cursor, "history page (derived table)", """
            SELECT page.workout_date, ws.set_id
            FROM (
                SELECT DISTINCT w.workout_id, w.workout_date
                FROM workouts w WHERE w.user_id = %s
                ORDER BY w.workout_date DESC LIMIT 20 OFFSET 0
            ) AS page
            JOIN workout_sets ws ON ws.workout_id = page.workout_id
        """, (user_id,), "uq_workouts_user_date", counts["workouts"])

        check(cursor, "personal records for a user", """
            SELECT pr.exercise_id, pr.estimated_1rm
            FROM personal_records pr
            WHERE pr.user_id = %s ORDER BY pr.estimated_1rm DESC
        """, (user_id,), "uq_personal_records_user_exercise",
              counts["personal_records"])

        check(cursor, "weight log series", """
            SELECT log_id, logged_on, weight_kg FROM weight_logs
            WHERE user_id = %s ORDER BY logged_on ASC
        """, (user_id,), "uq_weight_logs_user_day", counts["weight_logs"])

        print("\n-- accounts --------------------------------------------------")

        check(cursor, "login lookup by email", """
            SELECT user_id, password_hash FROM users WHERE lower(email) = %s
        """, ("nobody@example.invalid",), "uq_users_email", counts["users"])

        check(cursor, "reset token by hash", """
            SELECT token_id FROM password_reset_tokens
            WHERE token_hash = %s LIMIT 1
        """, ("0" * 64,), "idx_reset_tokens_hash",
              counts["password_reset_tokens"])

        check(cursor, "a user's unused tokens", """
            SELECT token_id FROM password_reset_tokens
            WHERE user_id = %s AND used_at IS NULL
        """, (user_id,), "idx_reset_tokens_user",
              counts["password_reset_tokens"])

        print("\n-- upserts (planned, not executed) ---------------------------")

        # Plain EXPLAIN: these WRITE, so they must never be ANALYZEd. What is
        # being confirmed is the arbiter - that ON CONFLICT resolved against
        # the intended unique index rather than some other one.
        check(cursor, "workout upsert arbiter", """
            INSERT INTO workouts (user_id, workout_date) VALUES (%s, CURRENT_DATE)
            ON CONFLICT (user_id, workout_date) DO UPDATE
                SET workout_date = EXCLUDED.workout_date
            RETURNING workout_id
        """, (user_id,), "uq_workouts_user_date", counts["workouts"],
              analyze=False)

        check(cursor, "personal record upsert arbiter", """
            INSERT INTO personal_records
                (user_id, exercise_id, best_weight, best_reps, estimated_1rm,
                 achieved_on)
            VALUES (%s, %s, 100, 5, 116.67, CURRENT_DATE)
            ON CONFLICT (user_id, exercise_id) DO UPDATE SET
                estimated_1rm = EXCLUDED.estimated_1rm
            WHERE EXCLUDED.estimated_1rm > personal_records.estimated_1rm
        """, (user_id, exercise_id), "uq_personal_records_user_exercise",
              counts["personal_records"], analyze=False)

    summarise()


def summarise():
    print("\n" + "=" * 62)
    print(f"  {len(PASSED)} using the expected index, "
          f"{len(WARNED)} seq scan on a small table, {len(FAILED)} failed")
    if WARNED:
        print("\n  warnings (fine while these tables are small, re-check once"
              " they grow):")
        for label in WARNED:
            print(f"    {label}")
    if FAILED:
        print("\n  FAILURES:")
        for label in FAILED:
            print(f"    {label}")
        sys.exit(1)


if __name__ == "__main__":
    main()
