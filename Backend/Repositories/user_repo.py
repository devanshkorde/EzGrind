"""Queries against the users table."""

from db import get_cursor

# password_hash is included deliberately: login has to compare it. Callers must
# never put this row into a response - see profile_fields() for the safe shape.
_CREDENTIAL_FIELDS = "user_id, full_name, email, password_hash"

_PROFILE_FIELDS = ("full_name, email, contact_number, date_of_birth,"
                   " height_cm, weight_kg, fitness_goal, created_at")

# Column names come from this tuple and never from a request body, so a caller
# cannot name its way into updating password_hash or email.
_UPDATABLE_COLUMNS = ("full_name", "contact_number", "date_of_birth",
                      "height_cm", "weight_kg", "fitness_goal")


def find_by_email(email):
    with get_cursor() as cursor:
        cursor.execute(
            f"SELECT {_CREDENTIAL_FIELDS} FROM users WHERE email=%s",
            (email,)
        )
        return cursor.fetchone()


def find_profile(user_id):
    with get_cursor() as cursor:
        cursor.execute(
            f"SELECT {_PROFILE_FIELDS} FROM users WHERE user_id=%s",
            (user_id,)
        )
        return cursor.fetchone()


def email_exists(email):
    with get_cursor() as cursor:
        cursor.execute("SELECT user_id FROM users WHERE email=%s", (email,))
        return cursor.fetchone() is not None


def update_profile(user_id, fields):
    """Partial update: only the keys supplied, only whitelisted columns.

    A key mapped to None clears that column - that is how a user removes a date
    of birth they would rather not store. A key that was never supplied is not
    in `fields` at all and so is left untouched.
    """
    columns = [name for name in _UPDATABLE_COLUMNS if name in fields]
    if not columns:
        return False

    assignments = ", ".join(f"{name} = %s" for name in columns)
    params = [fields[name] for name in columns] + [user_id]

    with get_cursor(dictionary=False) as cursor:
        cursor.execute(f"UPDATE users SET {assignments} WHERE user_id = %s", params)
    # rowcount is 0 when the new values equal the old ones, which is a
    # successful no-op rather than a failure.
    return True


def find_password_hash(user_id):
    with get_cursor(dictionary=False) as cursor:
        cursor.execute("SELECT password_hash FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else None


def password_changed_at(user_id):
    """When this account last had its password changed, or None.

    Read on every authenticated request by auth._session_is_current, so it
    selects one column off the primary key and nothing else.
    """
    with get_cursor(dictionary=False) as cursor:
        cursor.execute(
            "SELECT password_changed_at FROM users WHERE user_id = %s", (user_id,)
        )
        row = cursor.fetchone()
        return row[0] if row else None


def set_password_hash(user_id, password_hash):
    """Replace the hash and stamp the change.

    The stamp is what ends every session opened before now - see
    auth._session_is_current. Written in the same statement as the hash so
    there is no window in which the password is new but old cookies still work.
    """
    with get_cursor(dictionary=False) as cursor:
        # NOW(6), not NOW(). Sessions store their start time as a float, and a
        # whole-second stamp compares as EARLIER than a login that happened
        # 0.7s before it - so a session opened in the same second as the reset
        # would survive the check meant to end it. The column is DATETIME(6)
        # as of migration 008.
        cursor.execute(
            "UPDATE users SET password_hash = %s, password_changed_at = NOW(6)"
            " WHERE user_id = %s",
            (password_hash, user_id)
        )
        return cursor.rowcount > 0


def delete_account(user_id):
    """Delete a user and everything belonging to them, in one transaction.

    Workouts go first on purpose. workouts -> users is ON DELETE RESTRICT, and
    it stays that way: it means no other code path in the application can
    cascade a training history away by accident. Destroying it is deliberate,
    happens here, and nowhere else.

    workout_sets cascade from workouts; weight_logs and personal_records
    cascade from users.
    """
    with get_cursor(dictionary=False) as cursor:
        cursor.execute("DELETE FROM workouts WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        return cursor.rowcount > 0


def create(full_name, email, password_hash, contact_number,
           date_of_birth, height_cm, weight_kg, fitness_goal):
    with get_cursor(dictionary=False) as cursor:
        cursor.execute("""
            INSERT INTO users
            (full_name, email, password_hash, contact_number, date_of_birth,
             height_cm, weight_kg, fitness_goal)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (full_name, email, password_hash, contact_number,
              date_of_birth, height_cm, weight_kg, fitness_goal))
        return cursor.lastrowid
