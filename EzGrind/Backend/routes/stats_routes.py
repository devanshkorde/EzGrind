"""Aggregate statistics and personal records.

SCOPING: every route here is @login_required and derives its identity from
current_user_id(), which reads session["user_id"]. Not one of them accepts a
user id - not in the path, not in the query string, not in a body - so there is
nothing a caller could supply to read another account's numbers. A stray
?user_id=9 is ignored because no code reads it.
"""

from flask import Blueprint, jsonify

from auth import current_user_id, login_required
from repositories import stats_repo
from validators import choice_arg

bp = Blueprint("stats", __name__)

PERIODS = set(stats_repo.PERIOD_DAYS)
DEFAULT_PERIOD = "month"


@bp.get("/stats/summary")
@login_required
def get_summary():
    return jsonify({"data": stats_repo.summary(current_user_id())})


@bp.get("/stats/volume")
@login_required
def get_volume():
    period = choice_arg("period", PERIODS, DEFAULT_PERIOD)
    return jsonify({
        "data": stats_repo.volume_series(current_user_id(), period),
        "meta": {"period": period},
    })


@bp.get("/stats/muscle-distribution")
@login_required
def get_muscle_distribution():
    period = choice_arg("period", PERIODS, DEFAULT_PERIOD)
    return jsonify({
        "data": stats_repo.muscle_distribution(current_user_id(), period),
        "meta": {"period": period},
    })


@bp.get("/personal-records")
@login_required
def get_personal_records():
    return jsonify({"data": stats_repo.personal_records(current_user_id())})
