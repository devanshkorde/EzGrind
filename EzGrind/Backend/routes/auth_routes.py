"""Account lifecycle: signup, login, logout, password reset."""

import logging
import threading

import config
from flask import Blueprint, copy_current_request_context, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from auth import limiter, login_user, logout_user
from errors import ApiError
from repositories import reset_token_repo, user_repo
from services import email_service, email_templates
from validators import (
    optional,
    require_json,
    require_str,
    text_arg,
    validate_email,
    validate_name,
    validate_password,
    validate_phone,
    validate_positive_number,
)

bp = Blueprint("auth", __name__)
logger = logging.getLogger("ezgrind.auth")

# One sentence, returned for every outcome of a forgot-password request:
# unknown address, known address, send failure. Anything that varied would make
# this endpoint an account-existence oracle - a way to ask "does this person
# have an EzGrind account" and get a straight answer.
FORGOT_MESSAGE = ("If an account exists for that email, we've sent a reset "
                  "link. It expires in 20 minutes.")


def _send_welcome_email(full_name, email):
    """Queue the welcome email. Cannot fail the caller, by construction.

    Called only AFTER user_repo.create() has returned, which means the row is
    committed - get_cursor() commits on clean exit. Nobody is ever welcomed to
    an account that failed to insert.

    Everything is caught, including template rendering. Resend's free tier caps
    at 100 emails/day and 2 requests/second, and that cap will be reached; a
    signup that 500s because an email quota ran out is a bug, not a safeguard.
    """
    try:
        subject, html, text = email_templates.welcome(full_name)
        email_service.send_async(email, subject, html, text, template="welcome")
    except Exception:                                            # noqa: BLE001
        logger.exception("welcome email could not be queued for %s",
                         email_service.mask_email(email))


def _signup_payload(data):
    """Everything users.create() needs, validated, in insert order."""
    password = require_str(data, "password", strip=False)
    fitness_goal = optional(data, "fitness_goal")
    if not fitness_goal:
        raise ApiError(400, "validation_error", "Select a fitness goal.", "fitness_goal")

    full_name = validate_name(require_str(data, "full_name"))
    email = validate_email(require_str(data, "email"))

    return {
        "full_name": full_name,
        "email": email,
        # Name and email are passed in so the policy can reject a password built
        # out of either - the first thing anyone who knows the person would try.
        "password_hash": generate_password_hash(
            validate_password(password, full_name=full_name, email=email)),
        "contact_number": validate_phone(optional(data, "contact_number")),
        "date_of_birth": optional(data, "date_of_birth"),
        "height_cm": validate_positive_number(
            optional(data, "height_cm"), "Height", "height_cm"),
        "weight_kg": validate_positive_number(
            optional(data, "weight_kg"), "Weight", "weight_kg"),
        "fitness_goal": fitness_goal,
    }


@bp.post("/signup")
@limiter.limit("10 per minute")
def signup():
    payload = _signup_payload(require_json())

    if user_repo.email_exists(payload["email"]):
        raise ApiError(400, "email_exists",
                       "That email is already registered.", "email")

    # The insert commits inside create(). Only then is anyone emailed.
    user_id = user_repo.create(**payload)
    _send_welcome_email(payload["full_name"], payload["email"])

    return jsonify({
        "data": {"user_id": user_id},
        "message": "Signup successful 🎉",
    })


@bp.post("/login")
@limiter.limit("10 per minute")
def login():
    data = require_json()
    email = require_str(data, "email")
    password = require_str(data, "password", strip=False)

    user = user_repo.find_by_email(email)
    if not user or not check_password_hash(user["password_hash"], password):
        # One message for both causes, so the endpoint cannot be used to test
        # whether an email is registered.
        raise ApiError(401, "invalid_credentials", "Invalid credentials")

    login_user(user)
    return jsonify({
        "data": {
            "user_id": user["user_id"],
            "full_name": user["full_name"],
            "email": user["email"],
        },
        "message": "Login successful",
    })


@bp.post("/logout")
def logout():
    logout_user()
    return jsonify({"data": {}, "message": "Logged out"})


# =========================
# PASSWORD RESET
# =========================

def _forgot_email_key():
    """Rate-limit key: the address in the body, so one account cannot be
    mail-bombed from a hundred different IPs."""
    data = request.get_json(silent=True)
    email = (data or {}).get("email")
    return f"forgot:{str(email).strip().lower()}" if email else "forgot:anonymous"


def _issue_and_send_reset(email, client_ip):
    """Look the user up, mint a token, send the link. Runs on a worker thread.

    OFF THE REQUEST THREAD FOR A SECURITY REASON, not a performance one. A real
    address costs a token insert and an API call; an unknown one costs a single
    SELECT. Doing that work inline would make the response 400ms for accounts
    that exist and 20ms for accounts that do not - the same oracle the identical
    wording is there to prevent, just measured with a stopwatch instead of read.

    Everything is caught: this thread has no caller to raise into, and a failure
    here must never change what the user was already told.
    """
    try:
        user = user_repo.find_by_email(email)
        if not user:
            logger.info("forgot-password for an address with no account: %s",
                        email_service.mask_email(email))
            return

        raw_token = reset_token_repo.issue(
            user["user_id"], config.RESET_TOKEN_TTL, client_ip)
        subject, html, text = email_templates.password_reset(raw_token)
        # Synchronous here - this IS the background thread.
        email_service.send(user["email"], subject, html, text, template="reset")
    except Exception:                                            # noqa: BLE001
        logger.exception("reset link could not be issued for %s",
                         email_service.mask_email(email))


@bp.post("/forgot-password")
@limiter.limit("10 per hour")                              # per IP (default key)
@limiter.limit("3 per hour", key_func=_forgot_email_key)   # per email address
def forgot_password():
    """Always the same answer, in the same time, whatever the truth is.

    Rate limited twice over: per IP stops one machine working through a list of
    addresses, per email stops a distributed attempt from filling one person's
    inbox with reset links.
    """
    data = require_json()
    email = validate_email(require_str(data, "email"))

    # copy_current_request_context so the thread can render templates, which
    # need an app context. Started before the response is built, and never
    # joined - the answer does not depend on what it finds.
    worker = copy_current_request_context(_issue_and_send_reset)
    threading.Thread(
        target=worker,
        args=(email, request.remote_addr),
        name="ezgrind-reset",
        daemon=True,
    ).start()

    return jsonify({"data": {}, "message": FORGOT_MESSAGE})


@bp.get("/reset-password/validate")
@limiter.limit("30 per hour")
def validate_reset_token():
    """Is this link still good? Answered WITHOUT spending it.

    Called when the reset page loads, so someone holding a dead link is told
    before they choose a password, type it twice, and submit.
    """
    status, _ = reset_token_repo.classify(text_arg("token", 200))
    return jsonify({"data": {"status": status, "valid": status == "valid"}})


@bp.post("/reset-password")
@limiter.limit("10 per hour")
def reset_password():
    """Spend the token, replace the password, end every existing session.

    Deliberately does NOT sign the user in. Whoever is holding this link proved
    they can read the mailbox, which is not the same as proving they are the
    account owner - and if the reset was an attacker's, handing them a live
    session is the last thing to do. They go to the login page and use the
    password they just set.
    """
    data = require_json()
    raw_token = require_str(data, "token")
    new_password = require_str(data, "new_password", strip=False)

    status, row = reset_token_repo.classify(raw_token)
    if status != "valid":
        raise ApiError(400, f"token_{status}", _TOKEN_MESSAGES[status], "token")

    user = user_repo.find_profile(row["user_id"])
    validate_password(new_password, field="new_password",
                      full_name=user["full_name"] if user else None,
                      email=user["email"] if user else None)

    # Spend the token first. If the update below somehow fails, a spent token is
    # a wasted link; an unspent one after a successful change is a live link to
    # an account whose password just moved.
    if not reset_token_repo.redeem(row["token_id"], row["user_id"]):
        raise ApiError(400, "token_used", _TOKEN_MESSAGES["used"], "token")

    # Stamps password_changed_at in the same statement, which is what ends every
    # session opened before now - see auth._session_is_current.
    user_repo.set_password_hash(row["user_id"], generate_password_hash(new_password))

    # This session too, if the person resetting happened to be signed in.
    logout_user()

    if user:
        try:
            subject, html, text = email_templates.password_changed()
            email_service.send_async(user["email"], subject, html, text,
                                     template="password_changed")
        except Exception:                                        # noqa: BLE001
            # The password is already changed and committed. A failed
            # notification is a log line, not a reason to report failure.
            logger.exception("password-changed email could not be queued")

    logger.info("password reset completed for user_id=%s", row["user_id"])
    return jsonify({
        "data": {},
        "message": "Password updated. Sign in with your new password.",
    })


_TOKEN_MESSAGES = {
    "invalid": "That reset link isn't valid. Request a new one.",
    "expired": "That reset link has expired. Request a new one.",
    "used": "That reset link has already been used. Request a new one.",
}
