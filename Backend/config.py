"""Environment-driven configuration.

Import fails loudly rather than letting the app boot with a guessable session
secret or an anonymous database login. A default secret is worse than a crash:
the crash is noticed, the default is not.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

# Load the .env sitting next to this file so the server behaves identically no
# matter which directory it was launched from.
load_dotenv(Path(__file__).with_name(".env"))


class ConfigError(RuntimeError):
    """Raised at import time when required configuration is absent."""


def _required(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(
            f"{name} is not set.\n"
            f"  Copy EzGrind/Backend/.env.example to EzGrind/Backend/.env "
            f"and fill in {name}.\n"
            f"  Secrets have no fallback default - refusing to start."
        )
    return value


def _int(name, default):
    raw = os.getenv(name, default)
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer, got {raw!r}")


SECRET_KEY = _required("SECRET_KEY")
DB_PASSWORD = _required("DB_PASSWORD")

# Required too. A server that boots without it looks healthy while every
# password reset silently fails - the user is told a link was sent, and none
# was. Refusing to start is the honest failure. Set EMAIL_BACKEND=console to
# develop without a key.
RESEND_API_KEY = (_required("RESEND_API_KEY")
                  if os.getenv("EMAIL_BACKEND", "").strip().lower() == "resend"
                  else os.getenv("RESEND_API_KEY", "").strip())

# Defaults to production so that an environment which forgets to declare itself
# gets the locked-down settings, never the permissive ones. .env.example ships
# FLASK_ENV=development, and the app cannot start without a .env anyway.
FLASK_ENV = os.getenv("FLASK_ENV", "production").strip().lower()
IS_PRODUCTION = FLASK_ENV != "development"
DEBUG = not IS_PRODUCTION

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": _int("DB_PORT", "3306"),
    "user": os.getenv("DB_USER", "root"),
    "password": DB_PASSWORD,
    "database": os.getenv("DB_NAME", "ezgrind_db"),
}

# mysql-connector caps a pool at 32. Rejecting a bad value here beats a
# PoolError surfacing on the first request that touches the database.
DB_POOL_SIZE = _int("DB_POOL_SIZE", "5")
if not 1 <= DB_POOL_SIZE <= 32:
    raise ConfigError(f"DB_POOL_SIZE must be between 1 and 32, got {DB_POOL_SIZE}")

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500"
    ).split(",")
    if origin.strip()
]

# Lax everywhere now that Flask serves the frontend: the cookie is same-site by
# construction, so it never needs SameSite=None - which is the weaker setting
# and only existed to survive a split-origin setup that no longer exists.
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = IS_PRODUCTION
SESSION_COOKIE_HTTPONLY = True
PERMANENT_SESSION_LIFETIME = timedelta(days=7)


# =========================
# EMAIL
# =========================
# Deliberately NOT passed through _required(). Email is a feature, not a
# prerequisite: a missing API key must not take down login, the workout log or
# the exercise catalogue. services/email_service.py warns once at boot and
# fails the individual send with a message that says what to fix.

# console prints the message to the terminal; resend actually sends it. Console
# is the default in development so signup can be run fifty times while building
# without spending any of the 100/day free-tier quota.
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "resend" if IS_PRODUCTION else "console"
).strip().lower()

MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "EzGrind").strip()

# onboarding@resend.dev is the only sender an unverified Resend account may
# use, and such an account may only send to the address that owns it. Both
# restrictions lift once a domain is verified at https://resend.com/domains.
MAIL_FROM_ADDRESS = os.getenv("MAIL_FROM_ADDRESS", "onboarding@resend.dev").strip()

# Where links in emails point. Emails cannot use a relative URL, so this is the
# one place a full absolute site address is still needed - and in production it
# must be the public https:// one, or every link sent is dead.
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:5000").strip().rstrip("/")

# Long enough to find the email in a spam folder, short enough that a link
# left in a browser history or a forwarded message is worthless by the time
# anyone else reaches it.
RESET_TOKEN_TTL = timedelta(minutes=20)
