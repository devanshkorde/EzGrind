"""Queries against the users table."""

from datetime import datetime, timezone

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


# Matched on lower(email), not email, and that is not cosmetic.
#
# Under MySQL the column collation made every comparison case-insensitive, so
# "Devansh@x.com" and "devansh@x.com" were one account and nothing in Python
# had to care. Postgres compares text exactly. Left alone, the same person
# would sign up once and then fail to log in the first time they typed their
# address in a different case - with their row sitting right there.
#
# Two halves keep that impossible: validators.validate_email lowercases on the
# way in so what is stored is already lowercase, and uq_users_email is UNIQUE
# on lower(email) so the database enforces it rather than trusting the caller.
# Reading through lower() as well is what lets the lookup use that index.
def find_by_email(email):
    with get_cursor() as cursor:
        cursor.execute(
            f"SELECT {_CREDENTIAL_FIELDS} FROM users WHERE lower(email) = %s",
            (email.strip().lower(),)
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
        cursor.execute("SELECT user_id FROM users WHERE lower(email) = %s",
                       (email.strip().lower(),))
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
        # THE STAMP COMES FROM PYTHON, NOT FROM now(). It is compared against
        # session["auth_at"], which is time.time() - so both sides must be read
        # off the SAME CLOCK or the comparison measures clock skew instead of
        # ordering.
        #
        # Under MySQL that was free: the database ran on the same machine as
        # Flask. Against a hosted Postgres it is not. Measured against Neon,
        # this laptop is 0.67s behind the server - so a password_changed_at
        # written by now() lands 0.67s AFTER the refresh_session_stamp() that
        # follows it, and the check meant to end everyone ELSE's sessions ends
        # this one too. The user changes their password and is immediately
        # signed out. Caught by smoke.py's "password change must not sign the
        # user out".
        #
        # Sub-second precision is what makes this sensitive, and it is
        # deliberate: a whole-second stamp would let a session opened in the
        # same second as a reset survive it. MySQL needed NOW(6) and a
        # DATETIME(6) column to get that; here microseconds are the default and
        # TIMESTAMPTZ keeps the zone, so .timestamp() is true UTC on the way
        # back out.
        #
        # THE RULE: any column compared against a Python clock is written by
        # the Python clock. That covers this and reset_token_repo.expires_at.
        # used_at is only ever tested for NULL, so it may keep now().
        cursor.execute(
            "UPDATE users SET password_hash = %s, password_changed_at = %s"
            " WHERE user_id = %s",
            (password_hash, datetime.now(timezone.utc), user_id)
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
            RETURNING user_id
        """, (full_name, email, password_hash, contact_number,
              date_of_birth, height_cm, weight_kg, fitness_goal))
        return cursor.fetchone()[0]
