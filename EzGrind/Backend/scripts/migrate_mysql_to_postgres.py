"""Copy the live MySQL data into Postgres, primary keys and all.

    python scripts/migrate_mysql_to_postgres.py --dry-run
    python scripts/migrate_mysql_to_postgres.py

Reads the local MySQL named by the MYSQL_* variables below, writes the Postgres
named by DATABASE_URL in Backend/.env. The Postgres side must already have
migrations/001_schema.sql applied; the seed file is NOT needed, because
muscle_groups and exercises come across from MySQL with their existing ids.

PRIMARY KEYS ARE PRESERVED. That is the whole point: workout_sets rows carry
workout_id and exercise_id, and renumbering either would silently re-point
every set at the wrong exercise. Nothing here lets the database allocate an id.

IDEMPOTENT, in the insert-what-is-missing sense. Every insert is ON CONFLICT
(primary key) DO NOTHING, so a second run adds only rows that are not there
yet. It does NOT propagate edits made in MySQL after the first run - a row that
exists on both sides is left as Postgres has it. Re-running after changing data
in MySQL is not a sync; for that, delete the Postgres rows first.

TIMESTAMPS. MySQL hands back naive datetimes in the server's local time, and
the Postgres columns are TIMESTAMPTZ. Naive values are stamped with THIS
MACHINE's UTC offset on the way over, which is correct because the MySQL being
read is the one on this machine. Reading a MySQL in another zone would need
that offset overridden.

EMAILS ARE LOWERCASED. uq_users_email is UNIQUE on lower(email); the stored
value has to match what is indexed or find_by_email stops finding people.

Run the counts first:
    python scripts/migrate_mysql_to_postgres.py --dry-run
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db import get_cursor  # noqa: E402
from psycopg2.extras import execute_values  # noqa: E402

BATCH_SIZE = 1000

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "ezgrind_db"),
}

# Parents before children. Every table here is inserted only after everything
# its foreign keys point at, so no constraint is ever deferred or disabled -
# a failure means a genuinely broken reference in the source, not an ordering
# accident, and it should stop the run.
TABLES = (
    ("muscle_groups", "muscle_id",
     ("muscle_id", "muscle_name", "image_path")),

    ("exercises", "exercise_id",
     ("exercise_id", "exercise_name", "muscle_id", "equipment", "description",
      "exercise_type", "difficulty_level", "rating")),

    ("users", "user_id",
     ("user_id", "full_name", "email", "password_hash", "created_at",
      "contact_number", "date_of_birth", "height_cm", "weight_kg",
      "fitness_goal", "password_changed_at")),

    ("workouts", "workout_id",
     ("workout_id", "user_id", "workout_date", "created_at")),

    ("workout_sets", "set_id",
     ("set_id", "workout_id", "exercise_id", "weight", "reps",
      "time_under_tension", "comments", "set_order", "created_at")),

    ("weight_logs", "log_id",
     ("log_id", "user_id", "logged_on", "weight_kg", "created_at")),

    ("personal_records", "pr_id",
     ("pr_id", "user_id", "exercise_id", "best_weight", "best_reps",
      "estimated_1rm", "achieved_on", "updated_at")),

    ("password_reset_tokens", "token_id",
     ("token_id", "user_id", "token_hash", "expires_at", "used_at",
      "requested_ip", "created_at")),
)


# ============================================================
# SOURCE
# ============================================================

def mysql_connection():
    """Imported here, not at module scope.

    mysql-connector is not in requirements.txt - it left with the migration -
    and importing it at the top would make this file unimportable on a machine
    that has finished migrating and thrown it away.
    """
    try:
        import mysql.connector
    except ImportError:
        sys.exit(
            "mysql-connector-python is not installed. It is only needed to run\n"
            "this one script, so it is deliberately not in requirements.txt:\n"
            "  pip install mysql-connector-python==8.4.0"
        )

    try:
        return mysql.connector.connect(**MYSQL_CONFIG)
    except Exception as exc:                                     # noqa: BLE001
        sys.exit(
            f"Could not reach MySQL at {MYSQL_CONFIG['host']}:"
            f"{MYSQL_CONFIG['port']}/{MYSQL_CONFIG['database']}\n"
            f"  {exc}\n"
            f"  Override with MYSQL_HOST / MYSQL_PORT / MYSQL_USER /\n"
            f"  MYSQL_PASSWORD / MYSQL_DATABASE."
        )


def read_table(mysql_conn, table, columns):
    cursor = mysql_conn.cursor()
    try:
        cursor.execute(f"SELECT {', '.join(columns)} FROM {table}")
        return cursor.fetchall()
    finally:
        cursor.close()


def source_counts(mysql_conn):
    counts = {}
    cursor = mysql_conn.cursor()
    try:
        for table, _, _ in TABLES:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]
    finally:
        cursor.close()
    return counts


# ============================================================
# PREFLIGHT
# ============================================================

def preflight(mysql_conn):
    """Refuse to start if the source holds rows Postgres cannot represent.

    MySQL's utf8mb4_0900_ai_ci collation made three unique constraints
    case-insensitive. Postgres enforces them on lower(...), which is the same
    rule - so a source that predates those constraints could hold two rows that
    become one collision here. Better to name them now than to fail 4,000 rows
    into an insert.

    In practice this passes: the constraints exist and MySQL already prevented
    the duplicates. It costs three counting queries to know that rather than
    assume it.
    """
    checks = (
        ("users with the same email ignoring case", """
            SELECT LOWER(email), COUNT(*) FROM users
            GROUP BY LOWER(email) HAVING COUNT(*) > 1
        """),
        ("muscle groups with the same name ignoring case", """
            SELECT LOWER(muscle_name), COUNT(*) FROM muscle_groups
            GROUP BY LOWER(muscle_name) HAVING COUNT(*) > 1
        """),
        ("exercises with the same name and muscle ignoring case", """
            SELECT LOWER(exercise_name), muscle_id, COUNT(*) FROM exercises
            GROUP BY LOWER(exercise_name), muscle_id HAVING COUNT(*) > 1
        """),
    )

    problems = []
    cursor = mysql_conn.cursor()
    try:
        for label, sql in checks:
            cursor.execute(sql)
            rows = cursor.fetchall()
            if rows:
                problems.append((label, rows))
    finally:
        cursor.close()

    if problems:
        print("\nREFUSING TO MIGRATE - the source holds rows that collide under")
        print("Postgres' case-insensitive unique indexes:\n")
        for label, rows in problems:
            print(f"  {label}:")
            for row in rows[:10]:
                print(f"    {row}")
            if len(rows) > 10:
                print(f"    ... and {len(rows) - 10} more")
        sys.exit("\nResolve these in MySQL, then re-run.")

    print("  preflight: no case-insensitive key collisions")


# ============================================================
# TRANSFORM
# ============================================================

def localise(value):
    """Attach this machine's UTC offset to a naive datetime.

    datetime is a subclass of date, so the isinstance order matters: a DATE
    column (workout_date, logged_on, achieved_on, date_of_birth) is a calendar
    day with no instant and no zone, and must pass through untouched.
    """
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.astimezone()
    return value


def transform(table, columns, rows):
    """Row tuples ready for Postgres."""
    email_at = columns.index("email") if table == "users" else None

    prepared = []
    for row in rows:
        values = [localise(value) for value in row]
        if email_at is not None and values[email_at]:
            values[email_at] = values[email_at].strip().lower()
        prepared.append(tuple(values))
    return prepared


# ============================================================
# DESTINATION
# ============================================================

def target_counts():
    counts = {}
    with get_cursor(dictionary=False) as cursor:
        for table, _, _ in TABLES:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]
    return counts


def write_table(cursor, table, primary_key, columns, rows):
    """Insert what is missing. Returns how many rows were actually written.

    BARE `ON CONFLICT DO NOTHING`, with no conflict target, and the missing
    target is the point.

    Naming one - ON CONFLICT (primary_key) - arbitrates that index and no
    other, so a row colliding on any OTHER unique constraint raises instead of
    being skipped. exercises has two: the primary key, and
    uq_exercises_name_muscle on (lower(exercise_name), muscle_id). A Postgres
    already holding the catalogue from import_exercises.py numbers those rows
    differently from MySQL, so "Full Moon" exists on both sides under different
    ids - same name, same muscle, different primary key. Targeting the primary
    key sails past that and dies on the second index.

    Untargeted, this means what the migration actually wants: insert unless the
    row collides with ANYTHING already there. It is the same semantic MySQL's
    INSERT IGNORE had. The cost is that "already there" is now decided by any
    unique key rather than only identity - which is correct here, because a
    catalogue entry that exists under a different id IS already there.
    """
    if not rows:
        return 0

    # RETURNING plus fetch=True rather than cursor.rowcount: execute_values
    # sends one statement per page, so rowcount afterwards describes the LAST
    # page only and would under-report every table bigger than BATCH_SIZE.
    sql = f"""
        INSERT INTO {table} ({', '.join(columns)})
        VALUES %s
        ON CONFLICT DO NOTHING
        RETURNING 1
    """
    return len(execute_values(cursor, sql, rows,
                              page_size=BATCH_SIZE, fetch=True))


def reset_sequences(cursor):
    """Point every identity sequence past the ids just inserted.

    THE STEP EVERYONE FORGETS. Supplying an explicit id does not advance the
    sequence behind a GENERATED ... AS IDENTITY column, so without this the
    next signup asks for user_id 1, collides with a row migrated an hour ago,
    and returns a duplicate key error that looks like an application bug.

    The third argument to setval is is_called. Computing it rather than passing
    true is what keeps an empty table correct: setval(seq, 1, true) would make
    the next value 2 and burn id 1 forever, where setval(seq, 1, false) hands
    out 1 as it should.
    """
    print("\n  resetting identity sequences:")
    for table, primary_key, _ in TABLES:
        cursor.execute(f"""
            SELECT setval(
                pg_get_serial_sequence(%s, %s),
                COALESCE((SELECT MAX({primary_key}) FROM {table}), 1),
                (SELECT COUNT(*) > 0 FROM {table})
            )
        """, (table, primary_key))
        print(f"    {table:<22} {primary_key} sequence at {cursor.fetchone()[0]}")


# ============================================================
# MAIN
# ============================================================

def report(source, target):
    print(f"\n  {'table':<24}{'mysql':>8}{'postgres':>10}{'missing':>9}")
    print("  " + "-" * 51)
    for table, _, _ in TABLES:
        gap = max(source[table] - target[table], 0)
        print(f"  {table:<24}{source[table]:>8}{target[table]:>10}{gap:>9}")
    print("  " + "-" * 51)
    print(f"  {'TOTAL':<24}{sum(source.values()):>8}{sum(target.values()):>10}")


def main():
    parser = argparse.ArgumentParser(description="Copy MySQL data into Postgres.")
    parser.add_argument("--dry-run", action="store_true",
                        help="report row counts per table and write nothing")
    args = parser.parse_args()

    mysql_conn = mysql_connection()
    try:
        print(f"\n{'DRY RUN - nothing will be written' if args.dry_run else 'MIGRATE'}")
        print("=" * 62)
        print(f"  source  mysql://{MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}"
              f"/{MYSQL_CONFIG['database']}")
        print("  target  the DATABASE_URL in Backend/.env")

        preflight(mysql_conn)
        report(source_counts(mysql_conn), target_counts())

        if args.dry_run:
            print("\n  nothing written. Re-run without --dry-run to apply.")
            return

        # One transaction for every table. A failure anywhere leaves Postgres
        # exactly as it was, rather than half-populated with a broken FK graph
        # that the next run would have to reason about.
        print("\n  writing:")
        with get_cursor(dictionary=False) as cursor:
            for table, primary_key, columns in TABLES:
                rows = transform(table, columns,
                                 read_table(mysql_conn, table, columns))
                written = write_table(cursor, table, primary_key, columns, rows)
                print(f"    {table:<22} {len(rows):>6} read  {written:>6} inserted")

            reset_sequences(cursor)

        print("\n  done. Verifying:")
        report(source_counts(mysql_conn), target_counts())
    finally:
        mysql_conn.close()


if __name__ == "__main__":
    main()
