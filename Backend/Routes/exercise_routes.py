"""The exercise catalogue: muscle groups, exercises, equipment.

Mostly public - the catalogue is identical for every user and the log-workout
form needs it before anyone has signed in. Two routes personalise for a
signed-in user, and both scope that personal half strictly to the session user.
"""

from flask import Blueprint, jsonify

from auth import current_user_id, login_required, optional_user_id
from errors import ApiError
from repositories import exercise_repo, workout_repo
from validators import choice_arg, csv_int_arg, int_arg, text_arg

bp = Blueprint("exercises", __name__)

SORT_OPTIONS = {"name", "muscle"}
RECENT_LIMIT = 5


@bp.get("/muscles")
def get_muscles():
    return jsonify({"data": exercise_repo.list_muscles()})


@bp.get("/equipment")
def get_equipment():
    return jsonify({"data": exercise_repo.distinct_equipment()})


@bp.get("/exercise-filters")
def get_filter_options():
    """Everything the filter bar needs, so it costs one request instead of four."""
    return jsonify({"data": exercise_repo.filter_options()})


def _cursor_arg():
    """The (name, muscle_id) pair from the previous page, or None.

    Both halves must be present or neither is: half a cursor would silently
    page from the wrong place rather than failing, and the client only ever
    sends back what the previous response handed it.
    """
    first = text_arg("after", 100)
    second = text_arg("after_2", 100)
    if first is None or second is None:
        return None
    return [first, second]


@bp.get("/exercises")
def get_exercises():
    """Query args: muscle_id, q, equipment, difficulty, type, sort, limit, after.

    The total is computed only on the first page. "Load more" appends to a list
    whose total has not changed, so recounting 2,900 rows on every append would
    be work nobody reads.
    """
    filters = {
        "muscle_ids": csv_int_arg("muscle_id"),
        "query": text_arg("q"),
        "equipment": text_arg("equipment", 50),
        "difficulty": text_arg("difficulty", 20),
        "exercise_type": text_arg("type", 30),
    }
    after = _cursor_arg()

    rows, next_cursor = exercise_repo.list_exercises(
        sort=choice_arg("sort", SORT_OPTIONS, "name"),
        limit=int_arg("limit", exercise_repo.PAGE_DEFAULT, 1,
                      exercise_repo.PAGE_MAX),
        after=after,
        **filters,
    )

    meta = {"next": next_cursor}
    if after is None:
        meta["total"] = exercise_repo.count_exercises(**filters)

    return jsonify({"data": rows, "meta": meta})


@bp.get("/exercises/recent")
@login_required
def get_recent_exercises():
    """The caller's own recent lifts, most recent first.

    Personal, so unlike the rest of this blueprint it is behind auth. No
    conflict with /exercises/<int:exercise_id>: the int converter does not
    match "recent".
    """
    return jsonify({
        "data": workout_repo.recent_exercises(current_user_id(), RECENT_LIMIT)
    })


@bp.get("/exercises/<int:exercise_id>")
def get_exercise_detail(exercise_id):
    """Catalogue facts for anyone; personal numbers only when signed in.

    Gating the whole response behind auth would mean an anonymous visitor
    browsing the library gets an error on every card they open. The facts are
    public anyway - only `history` is personal, and it is None when there is no
    session to scope it to.
    """
    exercise = exercise_repo.find_detail(exercise_id)
    if not exercise:
        raise ApiError(404, "not_found", "That exercise does not exist.")

    user_id = optional_user_id()
    history = workout_repo.exercise_stats(user_id, exercise_id) if user_id else None

    return jsonify({"data": {"exercise": exercise, "history": history}})


@bp.get("/exercises/<int:exercise_id>/last-set")
@login_required
def get_last_set(exercise_id):
    """Prefills the set form. Resolves to null when there is no history."""
    return jsonify({
        "data": workout_repo.last_set_for_exercise(current_user_id(), exercise_id)
    })
