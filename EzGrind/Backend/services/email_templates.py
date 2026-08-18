"""Rendering: template + data -> (subject, html, text).

Separate from email_service.py so copy changes never touch transport code and a
provider swap never touches copy.

Rendering happens on the CALLER's thread, not the sending thread. render_template
needs a Flask app context, and pushing one inside a spawned thread is a footgun;
rendering first also means a broken template surfaces at signup time rather than
silently inside a thread nobody is watching.
"""

from datetime import datetime
from urllib.parse import quote

from flask import render_template

import config

WELCOME_SUBJECT = "Welcome to EzGrind"
RESET_SUBJECT = "Reset your EzGrind password"
PASSWORD_CHANGED_SUBJECT = "Your EzGrind password was changed"


def first_name(full_name):
    """The first word, or a usable fallback.

    "Welcome, " followed by nothing is worse than a generic greeting, so a
    blank or whitespace-only name renders "there" rather than an orphan comma.
    """
    first = (full_name or "").strip().split(" ")[0]
    return first or "there"


def welcome(full_name):
    """(subject, html, text) for the post-signup welcome message."""
    context = {
        "first_name": first_name(full_name),
        "dashboard_url": f"{config.APP_BASE_URL}/index.html",
    }
    return (
        WELCOME_SUBJECT,
        render_template("email/welcome.html", **context),
        render_template("email/welcome.txt", **context),
    )


def password_reset(raw_token):
    """(subject, html, text) for the reset link.

    The token is the whole secret, so it appears exactly here and nowhere else -
    not in a log line, not in a SendResult, not in the database.
    """
    context = {
        "reset_url": (f"{config.APP_BASE_URL}/reset-password.html?token="
                      + quote(raw_token, safe="")),
        "ttl_minutes": int(config.RESET_TOKEN_TTL.total_seconds() // 60),
    }
    return (
        RESET_SUBJECT,
        render_template("email/reset.html", **context),
        render_template("email/reset.txt", **context),
    )


def password_changed(changed_at=None):
    """(subject, html, text) for the after-the-fact notification.

    Sent whether the change came from a reset or from the profile page. If the
    account owner did not do it, this email is how they find out - which is why
    it goes out even though the user just performed the action themselves.
    """
    when = changed_at or datetime.now()
    context = {
        # Spelled out rather than an ISO stamp: this is read by a person who
        # needs to decide "was that me, half an hour ago?".
        "changed_at": when.strftime("%d %B %Y at %H:%M"),
    }
    return (
        PASSWORD_CHANGED_SUBJECT,
        render_template("email/password_changed.html", **context),
        render_template("email/password_changed.txt", **context),
    )
