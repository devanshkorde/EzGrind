"""Request field extraction and the signup validation rules.

The backend is the source of truth for these rules. Frontend/js/signup.js
repeats them so the user gets an instant answer, but that copy is a convenience
only - it can be bypassed by anyone with a terminal, so nothing here may be
skipped on the assumption the browser already checked.

Every failure names the field it blames, so a form can attach the message to
the input that caused it rather than parsing the message text.

Two layers, deliberately separate:
  require_* / optional_*  - "is this field present and the right kind of thing"
  validate_*              - "is this value acceptable to the domain"
"""

import re
from datetime import date, datetime

from flask import request

from errors import ApiError

NAME_PATTERN = re.compile(r'^[A-Za-z ]+$')
EMAIL_PATTERN = re.compile(r'^[^@]+@[^@]+\.[^@]+$')
PHONE_PATTERN = re.compile(r'^[0-9]{10}$')
MAX_AGE_YEARS = 120

# =========================
# PASSWORD POLICY
# =========================
# This module is the only authority on these rules. Frontend/js/ui.js repeats
# them so the user gets an answer as they type, but that copy is a convenience:
# it can be bypassed by anyone with a terminal, so nothing here may be skipped
# on the assumption the browser already checked.
#
# NOT APPLIED AT LOGIN, ON PURPOSE. validate_password runs when a password is
# WRITTEN - signup, change-password, reset - and never when one is CHECKED.
# Existing accounts with older, weaker passwords keep working exactly as before;
# tightening the policy must not lock anyone out of an account they already have.

MIN_PASSWORD_LENGTH = 8

# Spelled out rather than described as "a symbol", and interpolated into the
# error message, so nobody has to guess which characters count.
PASSWORD_SPECIALS = "!@#$%^&*()-_=+[]{};:,.<>?/~`|\\'\"" + " "

# The handful that show up first in every credential-stuffing list. Not a
# serious dictionary - that belongs in a library and a bloom filter - just the
# ones that would otherwise sail through "8 chars, upper, digit, symbol".
PASSWORD_BLOCKLIST = frozenset({
    "password", "password1", "password123", "password!", "passw0rd",
    "12345678", "123456789", "1234567890", "qwerty123", "qwertyuiop",
    "letmein", "letmein123", "welcome1", "welcome123", "admin123",
    "iloveyou", "sunshine", "princess", "football", "monkey123",
    "abc12345", "trustno1", "dragon123", "baseball", "superman",
    "ezgrind", "ezgrind1", "ezgrind123",
})

# Below this length a fragment is too generic to test for. A user named "Al"
# would otherwise be unable to choose any password containing "al".
MIN_PERSONAL_FRAGMENT = 4

# The four values the signup form offers. The column has no constraint, so this
# is the only thing keeping the field to a known set.
FITNESS_GOALS = {"gain", "lose", "maintain", "muscle"}

# Mirrored in Frontend/js/logWorkout.js. These are the authoritative copy.
WEIGHT_MIN, WEIGHT_MAX = 0, 500
WEIGHT_DECIMALS = 1
REPS_MIN, REPS_MAX = 1, 100

# Bodyweight is a different measure with a different column: weight_logs.weight_kg
# is DECIMAL(5,2), and a bodyweight below 20kg is a typo rather than a person.
BODYWEIGHT_MIN, BODYWEIGHT_MAX = 20, 500
BODYWEIGHT_DECIMALS = 2


def _invalid(message, field=None):
    return ApiError(400, "validation_error", message, field)


# =========================
# EXTRACTION
# =========================

def require_json():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise _invalid("Request body must be a JSON object.")
    return data


def require_str(data, key, strip=True):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _invalid(f"'{key}' is required.", key)
    return value.strip() if strip else value


def require_int(data, key):
    value = data.get(key)
    if value is None or isinstance(value, bool):
        raise _invalid(f"'{key}' is required.", key)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise _invalid(f"'{key}' must be a whole number.", key)


def require_number(data, key):
    value = data.get(key)
    if value is None or isinstance(value, bool):
        raise _invalid(f"'{key}' is required.", key)
    try:
        return float(value)
    except (TypeError, ValueError):
        raise _invalid(f"'{key}' must be a number.", key)


def optional(data, key):
    """Missing and blank both mean 'not provided'.

    Empty HTML inputs post "" rather than omitting the key, and "" reaching a
    DATE or INT column is a 500 the user can trigger from the normal form.
    """
    value = data.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return value.strip() if isinstance(value, str) else value


def optional_int(data, key):
    value = optional(data, key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise _invalid(f"'{key}' must be a whole number.", key)


def require_weight(data, key="weight"):
    """Kilograms, 0-500, at most one decimal place."""
    value = require_number(data, key)

    if value < WEIGHT_MIN or value > WEIGHT_MAX:
        raise _invalid(f"Weight must be between {WEIGHT_MIN} and {WEIGHT_MAX} kg.", key)

    # Compare against the scaled integer rather than round(): float equality on
    # a rounded value gives the wrong answer for cases like 60.25.
    scaled = value * (10 ** WEIGHT_DECIMALS)
    if abs(scaled - round(scaled)) > 1e-9:
        raise _invalid("Weight can have at most one decimal place.", key)

    return round(value, WEIGHT_DECIMALS)


def require_bodyweight(data, key="weight_kg"):
    """Kilograms, 20-500, at most two decimal places."""
    value = require_number(data, key)

    if value < BODYWEIGHT_MIN or value > BODYWEIGHT_MAX:
        raise _invalid(
            f"Weight must be between {BODYWEIGHT_MIN} and {BODYWEIGHT_MAX} kg.", key
        )

    scaled = value * (10 ** BODYWEIGHT_DECIMALS)
    if abs(scaled - round(scaled)) > 1e-9:
        raise _invalid("Weight can have at most two decimal places.", key)

    return round(value, BODYWEIGHT_DECIMALS)


def validate_log_date(value, field="logged_on"):
    """Optional YYYY-MM-DD, never in the future.

    A future entry would sit at the end of the series and be read as the
    current weight, which it is not.
    """
    if value is None:
        return None

    try:
        parsed = datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        raise _invalid("Date must be formatted YYYY-MM-DD.", field)

    today = date.today()
    if parsed > today:
        raise _invalid("You cannot log a weight for a future date.", field)
    if parsed.year < today.year - MAX_AGE_YEARS:
        raise _invalid("That date looks too far back.", field)

    return parsed.isoformat()


def require_reps(data, key="reps"):
    """Whole repetitions, 1-100."""
    value = require_int(data, key)
    if value < REPS_MIN or value > REPS_MAX:
        raise _invalid(f"Reps must be between {REPS_MIN} and {REPS_MAX}.", key)
    return value


def optional_text(data, key, max_length):
    """Free text with a ceiling, so a paste-bomb cannot reach the column."""
    value = optional(data, key)
    if value is None:
        return None
    text = str(value)
    if len(text) > max_length:
        raise _invalid(f"'{key}' must be {max_length} characters or fewer.", key)
    return text


# =========================
# QUERY STRING
# =========================
# Query args arrive as strings from anywhere. Bounding them here is what stops
# ?limit=999999 turning a paginated endpoint back into an unbounded one.

def int_arg(name, default, minimum, maximum):
    raw = request.args.get(name)
    if raw is None or raw.strip() == "":
        return default

    try:
        value = int(raw)
    except ValueError:
        raise _invalid(f"'{name}' must be a whole number.", name)

    if value < minimum or value > maximum:
        raise _invalid(f"'{name}' must be between {minimum} and {maximum}.", name)
    return value


def optional_int_arg(name):
    raw = request.args.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw)
    except ValueError:
        raise _invalid(f"'{name}' must be a whole number.", name)


def csv_int_arg(name):
    """Comma-separated ids: ?muscle_id=1,5,7.

    A single id is simply a one-item list, so callers that pass one value keep
    working unchanged.
    """
    raw = request.args.get(name)
    if raw is None or not raw.strip():
        return None

    values = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(int(part))
        except ValueError:
            raise _invalid(
                f"'{name}' must be a comma-separated list of whole numbers.", name
            )
    return values or None


def choice_arg(name, allowed, default):
    """One of a fixed set. Anything else is a 400, never a silent fallback -
    a typo'd sort order should be reported, not ignored."""
    raw = request.args.get(name)
    if raw is None or not raw.strip():
        return default

    value = raw.strip().lower()
    if value not in allowed:
        raise _invalid(f"'{name}' must be one of: {', '.join(sorted(allowed))}.", name)
    return value


def text_arg(name, max_length=100):
    raw = request.args.get(name)
    if raw is None or not raw.strip():
        return None

    text = raw.strip()
    if len(text) > max_length:
        raise _invalid(f"'{name}' must be {max_length} characters or fewer.", name)
    return text


def date_arg(name):
    """ISO date, or None. Returned as a string - psycopg2 binds it to DATE."""
    raw = request.args.get(name)
    if raw is None or raw.strip() == "":
        return None

    text = raw.strip()
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        raise _invalid(f"'{name}' must be a date formatted YYYY-MM-DD.", name)
    return text


# =========================
# DOMAIN RULES
# =========================

def validate_name(value, field="full_name"):
    if not NAME_PATTERN.match(value):
        raise _invalid("Name should contain only letters and spaces.", field)
    return value


def validate_email(value, field="email"):
    """Valid shape, and normalised to lowercase.

    Lowercasing is not cosmetic. MySQL's collation made email comparison
    case-insensitive for free, so "Devansh@x.com" and "devansh@x.com" were one
    account. Postgres compares exactly, and without this they become two - the
    second signup succeeds, and whichever case the user types next may not be
    the row holding their password. uq_users_email is UNIQUE on lower(email)
    so the database refuses the duplicate either way; this is what stops the
    stored value and the indexed value drifting apart.

    Only the address is lowered. The local part of an email address is
    technically case-sensitive per RFC 5321, but no mail provider anyone signs
    up with treats it that way, and matching the old behaviour beats being
    right in a way that loses people their accounts.
    """
    if not EMAIL_PATTERN.match(value):
        raise _invalid("Enter a valid email address.", field)
    return value.lower()


def password_problems(value, full_name=None, email=None):
    """Every rule the password fails, in the order they are shown in the UI.

    A list rather than the first failure. Being told "needs a number" only
    after already fixing the length, then "too short" again after adding one,
    is how a signup form gets abandoned.
    """
    value = value or ""
    problems = []

    if len(value) < MIN_PASSWORD_LENGTH:
        problems.append(f"At least {MIN_PASSWORD_LENGTH} characters")
    if not any(character.isupper() for character in value):
        problems.append("At least one uppercase letter")
    if not any(character.isdigit() for character in value):
        problems.append("At least one number")
    if not any(character in PASSWORD_SPECIALS for character in value):
        problems.append(
            f"At least one special character ({PASSWORD_SPECIALS.strip()})"
        )

    lowered = value.lower()

    # Checked with trailing punctuation stripped as well as verbatim.
    # "Password123!" satisfies every rule above and is exactly the password the
    # rules were meant to stop; without this it passes because the blocklist
    # holds "password123" and the "!" makes the strings differ.
    if lowered in PASSWORD_BLOCKLIST or lowered.rstrip(PASSWORD_SPECIALS) in PASSWORD_BLOCKLIST:
        problems.append("Too common - pick something less guessable")

    # Personal fragments: a password built from the name or email on the same
    # form is the first thing anyone who knows the person would try.
    for fragment in _personal_fragments(full_name, email):
        if fragment in lowered:
            problems.append("Must not contain your name or email address")
            break

    return problems


def _personal_fragments(full_name, email):
    """Lowercased pieces of the user's own identity, long enough to matter."""
    fragments = []

    for word in (full_name or "").split():
        if len(word) >= MIN_PERSONAL_FRAGMENT:
            fragments.append(word.lower())

    local_part = (email or "").split("@")[0]
    if len(local_part) >= MIN_PERSONAL_FRAGMENT:
        fragments.append(local_part.lower())
        # "devansh.korde" and "devansh_korde" are the same person as "devansh".
        for piece in re.split(r"[._\-+]", local_part):
            if len(piece) >= MIN_PERSONAL_FRAGMENT:
                fragments.append(piece.lower())

    return fragments


def validate_password(value, field="password", full_name=None, email=None):
    """Enforce the policy, reporting every failure at once.

    full_name and email are optional so existing callers keep working, but both
    should be passed wherever they are known - they are what turns
    "Devansh2026!" from a passing password into a rejected one.
    """
    problems = password_problems(value, full_name, email)
    if problems:
        raise ApiError(
            400, "weak_password",
            "That password does not meet the requirements.",
            field, details=problems,
        )
    return value


def validate_phone(value, field="contact_number"):
    """Optional field: None passes, a present value must be ten digits."""
    if value is None:
        return None
    if not PHONE_PATTERN.match(str(value)):
        raise _invalid("Contact number must be 10 digits.", field)
    return str(value)


def validate_fitness_goal(value, field="fitness_goal"):
    """Optional here: None means the user has not chosen one."""
    if value is None:
        return None
    goal = str(value).strip().lower()
    if goal not in FITNESS_GOALS:
        raise _invalid("Select a fitness goal from the list.", field)
    return goal


def validate_birth_date(value, field="date_of_birth"):
    """Optional. YYYY-MM-DD, the format <input type="date"> posts.

    Bounded on both sides: a future date would produce a negative age, and a
    date 120 years back is a typo rather than a birthday.
    """
    if value is None:
        return None

    try:
        parsed = datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        raise _invalid("Date of birth must be formatted YYYY-MM-DD.", field)

    today = date.today()
    if parsed > today:
        raise _invalid("Date of birth cannot be in the future.", field)
    if parsed.year < today.year - MAX_AGE_YEARS:
        raise _invalid("Check that date of birth - it looks too far back.", field)

    return parsed.isoformat()


def validate_positive_number(value, label, field):
    """Optional field. Whole numbers only, matching the pre-existing int() cast.

    The columns are FLOAT, so "175.5" is rejected here purely to preserve
    current behaviour - that mismatch is audit B8, scheduled for a later phase.
    """
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise _invalid(f"{label} must be a number.", field)
    if number <= 0:
        raise _invalid(f"{label} must be greater than zero.", field)
    return number
