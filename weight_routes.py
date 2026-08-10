"""The bodyweight log.

SCOPING: every route is @login_required and takes its identity from
current_user_id(). None of them accepts a user id, so there is nothing a caller
could supply to read or alter another account's entries. Deletion carries the
ownership check into the WHERE clause and returns 404 - not 403 - for a row that
is not theirs, so the endpoint cannot be used to discover which ids exist.
"""

from flask import Blueprint, jsonify

from auth import current_user_id, login_required
from errors import ApiError
from repositories import weight_repo
from validators import (
    date_arg,
    int_arg,
    optional,
    require_bodyweight,
    require_json,
    validate_log_date,
)

bp = Blueprint("weights", __name__)

# A cap rather than a page size: nobody has more entries than this, but the
# parameter should not be a way to ask for unbounded output.
MAX_LOGS = 2000


@bp.post("/weight-logs")
@login_required
def create_weight_log():
    """Upserts on (user_id, logged_on): logging twice in a day corrects it."""
    data = require_json()

    result = weight_repo.log_weight(
        current_user_id(),
        require_bodyweight(data),
        validate_log_date(optional(data, "logged_on")),
    )
    return jsonify({"data": result, "message": "Weight logged"})


@bp.get("/weight-logs")
@login_required
def list_weight_logs():
    """Oldest first. Query args: from, to, limit."""
    return jsonify({
        "data": weight_repo.list_logs(
            current_user_id(),
            date_from=date_arg("from"),
            date_to=date_arg("to"),
            limit=int_arg("limit", MAX_LOGS, 1, MAX_LOGS),
        )
    })


@bp.delete("/weight-logs/<int:log_id>")
@login_required
def delete_weight_log(log_id):
    if not weight_repo.delete_log(current_user_id(), log_id):
        raise ApiError(404, "not_found", "That weight entry does not exist.")
    return jsonify({"data": {"log_id": log_id}, "message": "Entry deleted"})
