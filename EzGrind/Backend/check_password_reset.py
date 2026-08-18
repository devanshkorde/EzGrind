"""End-to-end check of password reset and the password policy.

    python check_password_reset.py            # policy, tokens, non-disclosure
    python check_password_reset.py --write    # + the full six-case walkthrough

--write creates two throwaway accounts at @example.invalid, runs them through
the whole reset flow, and deletes them in a finally block. It never touches an
account it did not create, and never sends real mail: the email backend is
forced to console for the duration regardless of .env.

Requires Database/migrations/001_schema.sql.
"""

import argparse
import io
import json
import logging
import secrets
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

import config
from app import create_app
from db import get_cursor
from repositories import reset_token_repo, user_repo
from services import email_service
from werkzeug.security import check_password_hash

PASSED, FAILED = [], []

GOOD_PASSWORD = "Str0ng-Pass!1"
NEW_PASSWORD = "An0ther-Pass!2"


def check(label, condition, detail=""):
    (PASSED if condition else FAILED).append(label)
    print(f"  {'ok  ' if condition else 'FAIL'} {label}{('  ' + detail) if detail else ''}")


APPLY_SCHEMA = 'psql "$DATABASE_URL" -f ../Database/migrations/001_schema.sql'


def require_schema():
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT to_regclass('password_reset_tokens') IS NOT NULL AS present"
        )
        has_table = cursor.fetchone()["present"]

        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'users'
        """)
        columns = {row["column_name"]: row["data_type"]
                   for row in cursor.fetchall()}

    if not has_table or "password_changed_at" not in columns:
        sys.exit(
            "The password-reset schema is missing.\n"
            f"  password_reset_tokens exists: {has_table}\n"
            f"  users.password_changed_at exists: "
            f"{'password_changed_at' in columns}\n"
            f"  Apply it first:\n"
            f"    {APPLY_SCHEMA}"
        )

    # THE TIME ZONE IS LOAD-BEARING, not cosmetic. auth._session_is_current
    # compares this column against a session's time.time(), which is UTC. Read
    # back naive, it is interpreted as the WEB PROCESS's local time instead -
    # so against a database in another zone (Neon runs UTC) every session is
    # either killed the instant it is created or never killed at all. Checked
    # here so the suite refuses to run rather than passing case 6 by accident
    # on a machine that happens to sit at UTC.
    #
    # Sub-second precision needs no check any more: MySQL truncated to whole
    # seconds unless told otherwise, which is what migration 008 existed to
    # fix. Postgres timestamps carry microseconds by default.
    if columns["password_changed_at"] != "timestamp with time zone":
        sys.exit(
            f"users.password_changed_at is {columns['password_changed_at']}, "
            f"not TIMESTAMPTZ.\n"
            "  Without a time zone, session invalidation is wrong by the offset\n"
            "  between this machine and the database. Re-apply the schema:\n"
            f"    {APPLY_SCHEMA}"
        )


# ============================================================
# READ-ONLY
# ============================================================

def check_policy():
    from validators import (MIN_PASSWORD_LENGTH, PASSWORD_BLOCKLIST,
                            PASSWORD_SPECIALS, password_problems)

    print("\n-- password policy -----------------------------------------")
    check("minimum length is 8", MIN_PASSWORD_LENGTH == 8)
    check("specials are a named constant", bool(PASSWORD_SPECIALS))
    check("blocklist is a named constant", len(PASSWORD_BLOCKLIST) >= 10,
          f"{len(PASSWORD_BLOCKLIST)} entries")

    problems = password_problems("abc")
    check("all failed rules are returned at once", len(problems) == 4,
          f"{len(problems)}: {problems}")
    check("the allowed specials appear in the message",
          any("!@#$" in p for p in problems))
    check("a compliant password passes", not password_problems(GOOD_PASSWORD))
    check("'Password123!' is caught by the blocklist",
          any("Too common" in p for p in password_problems("Password123!")),
          "trailing punctuation is stripped before the lookup")
    check("a password containing the user's name is rejected",
          any("name or email" in p for p in password_problems(
              "Devansh99!", full_name="Devansh Korde", email="d@x.com")))


def check_token_mechanics():
    print("\n-- token mechanics -----------------------------------------")
    raw = secrets.token_urlsafe(reset_token_repo.TOKEN_BYTES)
    check("token is 43+ url-safe chars", len(raw) >= 43, f"{len(raw)}")
    digest = reset_token_repo._hash(raw)
    check("hash is 64 hex chars (CHAR(64))", len(digest) == 64)
    check("hashing is deterministic", digest == reset_token_repo._hash(raw))
    check("the raw token is not recoverable from the hash", raw not in digest)
    check("an empty token never reaches the database",
          reset_token_repo._lookup("") is None
          and reset_token_repo._lookup(None) is None)
    check("comparison uses hmac.compare_digest",
          "compare_digest" in open(
              "repositories/reset_token_repo.py", encoding="utf-8").read())
    check("expiry is 20 minutes",
          config.RESET_TOKEN_TTL == timedelta(minutes=20))


def check_non_disclosure(client):
    print("\n-- non-disclosure ------------------------------------------")
    real = f"ezgrind-selftest-{secrets.token_hex(6)}@example.invalid"
    fake = f"ezgrind-nobody-{secrets.token_hex(6)}@example.invalid"

    known = client.post("/api/forgot-password", json={"email": real})
    unknown = client.post("/api/forgot-password", json={"email": fake})

    check("both requests return the same status",
          known.status_code == unknown.status_code, str(known.status_code))
    check("both requests return the identical message",
          json.loads(known.data) == json.loads(unknown.data),
          json.loads(known.data).get("message", "")[:60])
    check("the message does not confirm the account",
          "if an account exists" in json.loads(known.data)["message"].lower())


# ============================================================
# THE SIX CASES
# ============================================================

def make_user(client, email):
    response = client.post("/api/signup", json={
        "full_name": "Ez Selftest", "email": email,
        "password": GOOD_PASSWORD, "fitness_goal": "muscle",
    })
    body = json.loads(response.data)
    if response.status_code != 200:
        raise SystemExit(f"could not create test user: {body}")
    return body["data"]["user_id"]


def latest_raw_token(email):
    """Issue a token and return the raw value.

    Straight through the repository, because the database stores only the hash -
    there is no way to recover the raw token from a row, which is the whole
    design. The HTTP endpoint is exercised separately in case 2 and in the
    non-disclosure checks; calling both here was what produced two concurrent
    issues for one user and surfaced the deadlock.
    """
    user = user_repo.find_by_email(email)
    return reset_token_repo.issue(user["user_id"], config.RESET_TOKEN_TTL,
                                  "127.0.0.1")


def check_concurrent_issue(user_id):
    """Two resets requested at the same instant must not deadlock.

    A regression test, not a hypothetical: before _lock_user existed this
    raised MySQL error 1213 the first time it ran. Postgres has no gap locks,
    so that exact deadlock cannot recur here - what this now guards is the
    invariant underneath it, that exactly one live token survives the race.
    """
    import threading

    print("\n-- concurrent requests do not deadlock ---------------------")
    # Capped at the pool size. More threads than connections exhausts the pool
    # and reports PoolError, which is a capacity limit rather than a deadlock -
    # it would mask the thing this is actually testing.
    workers = min(config.DB_POOL_SIZE, 5)
    errors = []
    barrier = threading.Barrier(workers)

    def worker():
        try:
            barrier.wait(timeout=10)
            reset_token_repo.issue(user_id, config.RESET_TOKEN_TTL, "127.0.0.1")
        except Exception as exc:                             # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    deadlocks = [e for e in errors if "Deadlock" in str(e) or "1213" in str(e)]
    check(f"{workers} simultaneous issues, no deadlock", not deadlocks,
          f"{len(deadlocks)} deadlock(s)" if deadlocks else "")
    check("no other error either", not errors,
          f"{errors[:1]}" if errors else "")

    with get_cursor() as cursor:
        cursor.execute("""SELECT COUNT(*) AS n FROM password_reset_tokens
                          WHERE user_id = %s AND used_at IS NULL""", (user_id,))
        live = cursor.fetchone()["n"]
    check("exactly one token survives the race", live == 1, f"{live} live")


def walk_cases():
    app = create_app()
    client = app.test_client()

    email = f"ezgrind-reset-{secrets.token_hex(6)}@example.invalid"
    user_id = None

    saved_backend = config.EMAIL_BACKEND
    config.EMAIL_BACKEND = "console"

    try:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            user_id = make_user(client, email)

        # ---- 1 ------------------------------------------------------
        print("\n-- 1. reset for a real account -----------------------------")
        with redirect_stdout(buffer):
            raw = latest_raw_token(email)

        response = client.get(f"/api/reset-password/validate?token={raw}")
        check("the link validates before use",
              json.loads(response.data)["data"]["valid"] is True)

        with redirect_stdout(buffer):
            response = client.post("/api/reset-password",
                                   json={"token": raw, "new_password": NEW_PASSWORD})
        check("the reset succeeds", response.status_code == 200,
              str(response.status_code))

        stored = user_repo.find_password_hash(user_id)
        check("the new password works", check_password_hash(stored, NEW_PASSWORD))
        check("the OLD password no longer works",
              not check_password_hash(stored, GOOD_PASSWORD))

        login = client.post("/api/login",
                            json={"email": email, "password": GOOD_PASSWORD})
        check("logging in with the old password is refused",
              login.status_code == 401, str(login.status_code))

        check("the user is NOT auto-logged-in by the reset",
              "Set-Cookie" not in response.headers
              or "session=;" in response.headers.get("Set-Cookie", ""))

        # ---- 2 ------------------------------------------------------
        print("\n-- 2. reset for an address with no account -----------------")
        nobody = f"ezgrind-nobody-{secrets.token_hex(6)}@example.invalid"
        with get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM password_reset_tokens")
            before = cursor.fetchone()["n"]

        buffer2 = io.StringIO()
        with redirect_stdout(buffer2):
            unknown = client.post("/api/forgot-password", json={"email": nobody})
            import time
            time.sleep(1.5)          # let the worker thread finish

        with get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM password_reset_tokens")
            after = cursor.fetchone()["n"]

        check("the response is 200, same as a real account",
              unknown.status_code == 200)
        check("no token row was created", after == before, f"{before} -> {after}")
        check("no email was rendered or sent",
              "EMAIL" not in buffer2.getvalue())

        check_concurrent_issue(user_id)

        # ---- 3 ------------------------------------------------------
        print("\n-- 3. clicking the same link twice -------------------------")
        with redirect_stdout(buffer):
            raw3 = latest_raw_token(email)
            first = client.post("/api/reset-password",
                                json={"token": raw3, "new_password": "Third-Pass!3"})
            second = client.post("/api/reset-password",
                                 json={"token": raw3, "new_password": "Fourth-Pass!4"})
        check("the first use succeeds", first.status_code == 200)
        check("the second use is refused", second.status_code == 400,
              str(second.status_code))
        check("and says the link was already used",
              json.loads(second.data)["error"]["code"] == "token_used",
              json.loads(second.data)["error"]["code"])

        # ---- 4 ------------------------------------------------------
        print("\n-- 4. a token older than 20 minutes ------------------------")
        with redirect_stdout(buffer):
            raw4 = latest_raw_token(email)
        with get_cursor(dictionary=False) as cursor:
            # Aware, because expires_at is TIMESTAMPTZ. A naive value would be
            # read in the session time zone, so "one minute ago" would land
            # hours out and this case would test nothing.
            cursor.execute("""UPDATE password_reset_tokens SET expires_at = %s
                              WHERE user_id = %s AND used_at IS NULL""",
                           (datetime.now(timezone.utc) - timedelta(minutes=1),
                            user_id))

        validate = client.get(f"/api/reset-password/validate?token={raw4}")
        payload = json.loads(validate.data)["data"]
        check("validate reports it expired ON PAGE LOAD",
              payload["status"] == "expired" and payload["valid"] is False,
              payload["status"])
        check("validate did NOT consume the token",
              reset_token_repo.classify(raw4)[0] == "expired",
              "still expired, not 'used'")

        with redirect_stdout(buffer):
            submitted = client.post("/api/reset-password",
                                    json={"token": raw4, "new_password": "Fifth-Pass!5"})
        check("submitting it is also refused", submitted.status_code == 400)

        # ---- 5 ------------------------------------------------------
        print("\n-- 5. requesting two resets --------------------------------")
        with redirect_stdout(buffer):
            first_token = latest_raw_token(email)
            second_token = latest_raw_token(email)

        check("the FIRST link is dead",
              reset_token_repo.classify(first_token)[0] == "used",
              reset_token_repo.classify(first_token)[0])
        check("the second link is live",
              reset_token_repo.classify(second_token)[0] == "valid")

        with get_cursor() as cursor:
            cursor.execute("""SELECT COUNT(*) AS n FROM password_reset_tokens
                              WHERE user_id = %s AND used_at IS NULL""", (user_id,))
            check("exactly one unused token remains", cursor.fetchone()["n"] == 1)

        # ---- 6 ------------------------------------------------------
        print("\n-- 6. sessions elsewhere are ended -------------------------")
        # A second client stands in for "logged in on another device".
        elsewhere = app.test_client()
        with redirect_stdout(buffer):
            login = elsewhere.post("/api/login",
                                   json={"email": email, "password": "Third-Pass!3"})
        check("the other device is logged in", login.status_code == 200,
              str(login.status_code))

        me = elsewhere.get("/api/me")
        check("and can read its own profile", me.status_code == 200)

        with redirect_stdout(buffer):
            client.post("/api/reset-password",
                        json={"token": second_token, "new_password": "Sixth-Pass!6"})

        after_reset = elsewhere.get("/api/me")
        body = json.loads(after_reset.data)
        check("after the reset it is signed out", after_reset.status_code == 401,
              str(after_reset.status_code))
        # Guarded: on a failure the body is a profile, not an error, and an
        # unguarded lookup turns a reported FAIL into a traceback that hides
        # every check after it.
        check("with a code explaining why",
              body.get("error", {}).get("code") == "session_expired",
              body.get("error", {}).get("code", "no error key"))

        # ---- existing users -----------------------------------------
        print("\n-- existing accounts keep working --------------------------")
        with get_cursor() as cursor:
            cursor.execute("""SELECT COUNT(*) AS n FROM users
                              WHERE password_changed_at IS NOT NULL
                                AND user_id <> %s""", (user_id,))
            check("no other account was stamped", cursor.fetchone()["n"] == 0)

    finally:
        config.EMAIL_BACKEND = saved_backend
        if user_id:
            with get_cursor(dictionary=False) as cursor:
                cursor.execute("DELETE FROM password_reset_tokens WHERE user_id = %s",
                               (user_id,))
                cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
            print(f"\n  cleaned up test user {user_id}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="run the six-case walkthrough against temp accounts")
    args = parser.parse_args()

    logging.disable(logging.CRITICAL)
    require_schema()

    app = create_app()
    check_policy()
    check_token_mechanics()

    saved = config.EMAIL_BACKEND
    config.EMAIL_BACKEND = "console"
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        pass
    check_non_disclosure(app.test_client())
    config.EMAIL_BACKEND = saved

    if args.write:
        walk_cases()
    else:
        print("\n-- skipping the six-case walkthrough (pass --write) --------")

    print()
    if FAILED:
        print(f"check_password_reset: {len(FAILED)} FAILED, {len(PASSED)} passed")
        for label in FAILED:
            print(f"   FAILED: {label}")
        sys.exit(1)
    print(f"check_password_reset: all {len(PASSED)} checks passed")


if __name__ == "__main__":
    main()
