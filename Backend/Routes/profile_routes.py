"""The signed-in user's own profile: read, edit, password, deletion.

Every route here derives the user from the session. Nothing accepts a user id
from the client, so there is no route that can read or alter another account.
"""

from datetime import date

from flask import Blueprint, current_app, jsonify
from werkzeug.security import check_password_hash, generate_password_hash

from auth import (
    current_user_id,
    limiter,
    login_required,
    logout_user,
    refresh_session_stamp,
)
from errors import ApiError
from repositories import reset_token_repo, user_repo
from services import email_service, email_templates
from validators import (
    optional,
    require_json,
    require_str,
    validate_birth_date,
    validate_fitness_goal,
    validate_name,
    validate_password,
    validate_phone,
    validate_positive_number,
)

bp = Blueprint("profile", __name__)

# WHO bands. Each entry is the exclusive upper bound of its label.
BMI_BANDS = ((18.5, "Underweight"), (25, "Normal"), (30, "Overweight"))
BMI_ABOVE_ALL = "Obese"


def _age_from(date_of_birth):
    if not date_of_birth:
        return None

    today = date.today()
    had_birthday = (today.month, today.day) >= (date_of_birth.month, date_of_birth.day)
    return today.year - date_of_birth.year - (0 if had_birthday else 1)


def _bmi_from(height_cm, weight_kg):
    """None unless both inputs exist and height is usable.

    Returning None rather than 0 matters: the profile renders a prompt for a
    missing value and a real number for a present one, and 0 would be shown as
    a measurement.
    """
    if not height_cm or not weight_kg:
        return None

    metres = float(height_cm) / 100
    if metres <= 0:
        return None

    return round(float(weight_kg) / (metres ** 2), 1)


def _bmi_category(bmi):
    if bmi is None:
        return None
    for ceiling, label in BMI_BANDS:
        if bmi < ceiling:
            return label
    return BMI_ABOVE_ALL


def _profile_payload(user_id):
    profile = user_repo.find_profile(user_id)
    if profile is None:
        # A valid session pointing at a deleted row: treat as not authenticated
        # rather than serialising null.
        raise ApiError(401, "unauthorized", "Authentication required.")

    bmi = _bmi_from(profile["height_cm"], profile["weight_kg"])
    profile["age"] = _age_from(profile["date_of_birth"])
    profile["bmi"] = bmi
    profile["bmi_category"] = _bmi_category(bmi)
    return profile


@bp.get("/me")
@login_required
def get_me():
    return jsonify({"data": _profile_payload(current_user_id())})


@bp.patch("/me")
@login_required
def patch_me():
    """Partial update. Unknown keys are ignored rather than rejected.

    An omitted key leaves its column alone; a key present but empty clears it.
    full_name is the exception - the column is NOT NULL, so empty is a 400.
    """
    data = require_json()
    fields = {}

    if "full_name" in data:
        fields["full_name"] = validate_name(require_str(data, "full_name"))
    if "contact_number" in data:
        fields["contact_number"] = validate_phone(optional(data, "contact_number"))
    if "date_of_birth" in data:
        fields["date_of_birth"] = validate_birth_date(optional(data, "date_of_birth"))
    if "height_cm" in data:
        fields["height_cm"] = validate_positive_number(
            optional(data, "height_cm"), "Height", "height_cm")
    if "weight_kg" in data:
        fields["weight_kg"] = validate_positive_number(
            optional(data, "weight_kg"), "Weight", "weight_kg")
    if "fitness_goal" in data:
        fields["fitness_goal"] = validate_fitness_goal(optional(data, "fitness_goal"))

    if not fields:
        raise ApiError(400, "validation_error", "No editable fields were supplied.")

    user_id = current_user_id()
    user_repo.update_profile(user_id, fields)

    return jsonify({"data": _profile_payload(user_id), "message": "Profile updated"})


@bp.post("/me/password")
@limiter.limit("10 per minute")
@login_required
def change_password():
    data = require_json()
    current = require_str(data, "current_password", strip=False)
    user_id = current_user_id()
    profile = user_repo.find_profile(user_id)

    # Name and email are passed so the policy can reject a password built out of
    # either. Same rules as signup and reset - one implementation, three callers.
    replacement = validate_password(
        require_str(data, "new_password", strip=False), "new_password",
        full_name=profile["full_name"] if profile else None,
        email=profile["email"] if profile else None,
    )

    stored = user_repo.find_password_hash(user_id)

    if not stored or not check_password_hash(stored, current):
        raise ApiError(400, "invalid_password",
                       "That is not your current password.", "current_password")

    if check_password_hash(stored, replacement):
        raise ApiError(400, "validation_error",
                       "That is already your password.", "new_password")

    user_repo.set_password_hash(user_id, generate_password_hash(replacement))

    # set_password_hash stamps password_changed_at, which invalidates every
    # session opened before now - including this one. This user proved who they
    # are by supplying the current password, so their own cookie is moved past
    # the line while everyone else's stays behind it.
    refresh_session_stamp()

    # Any outstanding reset links are now stale: someone who can change their
    # password from inside the app has no use for them, and one sitting in an
    # inbox is a way back in.
    reset_token_repo.invalidate_all(user_id)

    if profile:
        try:
            subject, html, text = email_templates.password_changed()
            email_service.send_async(profile["email"], subject, html, text,
                                     template="password_changed")
        except Exception:                                        # noqa: BLE001
            current_app.logger.exception("password-changed email not queued")

    # The event, never the material.
    current_app.logger.info("Password changed for user_id=%s", user_id)

    return jsonify({"data": {}, "message": "Password updated"})


@bp.delete("/me")
@limiter.limit("10 per minute")
@login_required
def delete_me():
    data = require_json()
    password = require_str(data, "password", strip=False)

    user_id = current_user_id()
    stored = user_repo.find_password_hash(user_id)

    if not stored or not check_password_hash(stored, password):
        raise ApiError(400, "invalid_password", "Password does not match.", "password")

    user_repo.delete_account(user_id)
    logout_user()
    current_app.logger.warning("Account deleted: user_id=%s", user_id)

    return jsonify({"data": {}, "message": "Account deleted"})
