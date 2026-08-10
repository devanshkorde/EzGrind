"""Session identity and the rate limiter.

The auth check used to be copy-pasted into four routes with two different
messages, which meant a frontend could not reliably key off either one. It lives
here once now.

The limiter is constructed here rather than in app.py because auth_routes.py
needs it as a decorator, and importing it from app.py would be a cycle
(app -> routes -> app). Login and signup are the only limited endpoints, so
this is also where it belongs by subject.
"""

import time
from functools import wraps

from flask import session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from errors import ApiError

limiter = Limiter(get_remote_address, storage_uri="memory://")


def _session_is_current(user_id):
    """False once the account's password has changed since this session began.

    Flask sessions are signed cookies held by the client, so there is nothing
    server-side to delete when a password is reset. Instead every session
    carries the time it started, and users.password_changed_at is the line
    behind which those stamps stop counting. Resetting a password moves that
    line, and every cookie issued earlier stops working on its next request.

    THIS COSTS ONE INDEXED PRIMARY-KEY LOOKUP PER AUTHENTICATED REQUEST. That
    is the price of being able to end a session at all with cookie-based auth,
    and it is what makes "reset my password because someone else has it"
    actually do something. Measured at well under a millisecond against the
    connection pool; if it ever stops being negligible, the fix is a per-process
    cache keyed on user_id with a short TTL, not removing the check.

    Imported here rather than at module scope: auth.py is imported by app.py
    before the pool exists, and a top-level repository import would make the
    module graph depend on the database being up.
    """
    from repositories import user_repo

    started_at = session.get("auth_at")
    if started_at is None:
        # A cookie from before this check existed. Honoured rather than
        # rejected: applying the migration should not sign out everyone who is
        # already logged in. It is upgraded on their next login.
        return True

    changed_at = user_repo.password_changed_at(user_id)
    if changed_at is None:
        return True
    return started_at >= changed_at.timestamp()


def current_user_id():
    user_id = session.get("user_id")
    if user_id is None:
        raise ApiError(401, "unauthorized", "Authentication required.")

    if not _session_is_current(user_id):
        session.clear()
        raise ApiError(401, "session_expired",
                       "Your password was changed. Please sign in again.")
    return user_id


def optional_user_id():
    """For endpoints that serve everyone but personalise for a signed-in user.

    Returns None instead of raising, so a route can decide to omit the personal
    half of a response rather than reject the whole request.
    """
    user_id = session.get("user_id")
    if user_id is None:
        return None
    if not _session_is_current(user_id):
        session.clear()
        return None
    return user_id


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        current_user_id()
        return view(*args, **kwargs)

    return wrapped


def login_user(user):
    session.permanent = True
    session["user_id"] = user["user_id"]
    session["full_name"] = user["full_name"]
    # When this session began. Compared against users.password_changed_at on
    # every request - see _session_is_current. A plain epoch float rather than a
    # datetime because the session is JSON-serialised.
    session["auth_at"] = time.time()


def refresh_session_stamp():
    """Move this session's clock forward past a password change.

    Used by change-password, where the user proved who they are by supplying
    the current password. Without this they would change their password and be
    signed out one request later by the very check that is supposed to sign out
    everyone ELSE. Their other sessions still die, because only this cookie
    gets the new stamp.
    """
    if "user_id" in session:
        session["auth_at"] = time.time()


def logout_user():
    session.clear()
