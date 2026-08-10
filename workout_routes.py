"""Logging sets and reading back what was logged.

Every query here is scoped to the session's user id, never to an id supplied by
the client, so one account cannot read or write another's training data.
"""

from flask import Blueprint, jsonify

from auth import current_user_id, login_required
from errors import ApiError
from repositories import workout_repo
from validators import (
    date_arg,
    int_arg,
    optional_int_arg,
    optional_text,
    require_int,
    require_json,
    require_reps,
    require_weight,
)

COMMENT_MAX_LENGTH = 500
SESSIONS_PER_PAGE = 20
SESSIONS_PER_PAGE_MAX = 100

bp = Blueprint("workouts", __name__)


@bp.post("/log-workout")
@login_required
def log_workout():
    data = require_json()
    result = workout_repo.log_set(
        user_id=current_user_id(),
        exercise_id=require_int(data, "exercise_id"),
        weight=require_weight(data),
        reps=require_reps(data),
        comments=optional_text(data, "comments", COMMENT_MAX_LENGTH),
    )
    return jsonify({"data": result, "message": "Workout logged successfully 💪"})


@bp.get("/today-sets")
@login_required
def today_sets():
    return jsonify({"data": workout_repo.today_sets(current_user_id())})


@bp.delete("/workout-sets/<int:set_id>")
@login_required
def delete_workout_set(set_id):
    if not workout_repo.delete_set(current_user_id(), set_id):
        # 404 rather than 403 whether the set is missing or someone else's:
        # a 403 would confirm the id exists, turning this into an id oracle.
        raise ApiError(404, "not_found", "That set does not exist.")
    return jsonify({"data": {"set_id": set_id}, "message": "Set deleted"})


@bp.get("/today-workout")
@login_required
def today_workout():
    return jsonify({"data": workout_repo.today_summary(current_user_id())})


@bp.get("/workout-history")
@login_required
def workout_history():
    """Paginated training sessions, newest first.

    Query args: page, limit, from, to, muscle_id, exercise_id.
    """
    page = int_arg("page", 1, 1, 100_000)
    limit = int_arg("limit", SESSIONS_PER_PAGE, 1, SESSIONS_PER_PAGE_MAX)

    sessions, total = workout_repo.sessions(
        current_user_id(),
        page=page,
        limit=limit,
        date_from=date_arg("from"),
        date_to=date_arg("to"),
        muscle_id=optional_int_arg("muscle_id"),
        exercise_id=optional_int_arg("exercise_id"),
    )

    return jsonify({
        "data": sessions,
        "meta": {
            "page": page,
            "limit": limit,
            "total": total,
            "has_more": page * limit < total,
        },
    })
