"""End-to-end check of the API contract. Run directly:

    python smoke.py            read-only; proves 9 of the 11 flows
    python smoke.py --write    also proves signup and log-a-set

Uses Flask's test client, so it binds no port. Without --write it inserts
nothing. With --write it creates exactly one throwaway user
(smoke+<timestamp>@ezgrind.test) and one workout set belonging to that user,
prints their ids, and touches no pre-existing row.

Guards what Phases 1 and 2 exist to enforce: no endpoint may return HTML, every
success body is {"data": ...}, every failure is {"error": {...}}, and the
session cookie may never carry SameSite=None without Secure.
"""

import importlib
import os
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import app  # noqa: E402
from db import get_cursor  # noqa: E402

app.config["DEBUG"] = False  # let the 500 handler run instead of re-raising

WRITE = "--write" in sys.argv
ORIGIN = "http://127.0.0.1:5500"
PROTECTED = ("/api/me", "/api/today-workout", "/api/workout-history")


def show(label, resp):
    """Print a response, and enforce that no /api route ever returns HTML.

    Scoped to /api because Flask now also serves the frontend, where HTML is
    the entire point. The guarantee this protects is unchanged: an API client
    doing res.json() must never be handed a Werkzeug error page.
    """
    ctype = resp.headers.get("Content-Type", "")
    body = resp.get_data(as_text=True)
    path = getattr(resp.request, "path", "") if hasattr(resp, "request") else ""
    if path.startswith("/api") or "/api" in label:
        assert "text/html" not in ctype, f"{label}: returned HTML! {body[:200]}"
    print(f"  {label:<38} {resp.status_code}  {body.strip()[:90]}")
    return resp


def data_of(resp):
    body = resp.get_json()
    assert "data" in body, f"success body must carry 'data': {body}"
    return body["data"]


print("\n-- streak arithmetic (moved here from check_stats.js) ---------")
# Pure functions, so they are testable without a database or a session.
from datetime import date, timedelta  # noqa: E402
from repositories import stats_repo  # noqa: E402


def days_ago(*offsets):
    today = date.today()
    return [today - timedelta(days=offset) for offset in offsets]


assert stats_repo._current_streak(days_ago(0, 1, 2)) == 3, "three days ending today"
assert stats_repo._current_streak(days_ago(1, 2, 3)) == 3, "yesterday still counts"
assert stats_repo._current_streak(days_ago(0, 2, 3)) == 1, "a gap ends it"
assert stats_repo._current_streak(days_ago(2, 3)) == 0, "two idle days break it"
assert stats_repo._current_streak([]) == 0

assert stats_repo._longest_streak(days_ago(0, 1, 2, 5, 6)) == 3
assert stats_repo._longest_streak(days_ago(9, 8, 7, 6, 0)) == 4, "order must not matter"
assert stats_repo._longest_streak(days_ago(0)) == 1
assert stats_repo._longest_streak([]) == 0
# A day logged twice must not inflate the run.
assert stats_repo._longest_streak(days_ago(0, 0, 1)) == 2

week = stats_repo._week_activity(days_ago(0, 3))
assert len(week) == 7, week
assert week[-1]["date"] == date.today().isoformat(), "last entry is today"
assert week[-1]["trained"] is True and week[-4]["trained"] is True, week
assert sum(1 for day in week if day["trained"]) == 2, week
print("  streaks, longest-run and week activity     all pass")


print("\n-- public endpoints ------------------------------------------")
anon = app.test_client()

# / now serves the frontend, not a JSON greeting: Flask hosts both halves so the
# app is one origin. The greeting route is gone; /api/health is the liveness
# check and always was.
resp = show("GET / (frontend index)", anon.get("/"))
assert resp.status_code == 200
assert b"<!DOCTYPE html>" in resp.data[:120], "/ must serve index.html"

resp = show("GET /api/health", anon.get("/api/health"))
assert resp.status_code in (200, 503)
if resp.status_code == 503:
    assert resp.get_json()["error"]["code"] == "database_unavailable"
    sys.exit("\nDatabase unreachable - start MySQL and re-run.")
assert data_of(resp) == {"status": "ok", "database": "connected"}

muscles = data_of(show("GET /api/muscles", anon.get("/api/muscles")))
assert isinstance(muscles, list) and muscles, "muscle_groups is empty"

exercises = data_of(show("GET /api/exercises", anon.get("/api/exercises")))
assert isinstance(exercises, list) and exercises, "exercises is empty"
# The library page renders every one of these on a card or in the detail panel.
for field in ("exercise_id", "exercise_name", "equipment", "description",
              "muscle_id", "muscle_name", "image_path"):
    assert field in exercises[0], f"/api/exercises is missing {field!r}: {exercises[0]}"
assert exercises[0]["image_path"].startswith("assets/"), exercises[0]["image_path"]

equipment_values = data_of(show("GET /api/equipment", anon.get("/api/equipment")))
assert isinstance(equipment_values, list) and equipment_values, equipment_values
assert all(isinstance(value, str) for value in equipment_values), equipment_values
assert len(equipment_values) == len(set(equipment_values)), "equipment must be distinct"

# --- catalogue filters ------------------------------------------------
resp = show("exercises ?q=press", anon.get("/api/exercises?q=press"))
by_name = data_of(resp)
assert by_name, "expected at least one match for 'press'"
assert all("press" in e["exercise_name"].lower() for e in by_name), by_name

resp = show("exercises ?q=%  (LIKE wildcard)", anon.get("/api/exercises?q=%25"))
assert data_of(resp) == [], "a literal % must not match every row"

first_equipment = equipment_values[0]
resp = show(f"exercises ?equipment={first_equipment}",
            anon.get(f"/api/exercises?equipment={first_equipment}"))
assert all(e["equipment"] == first_equipment for e in data_of(resp)), first_equipment

two_muscles = [str(muscles[0]["muscle_id"]), str(muscles[1]["muscle_id"])]
resp = show("exercises ?muscle_id=1,2 (multi)",
            anon.get("/api/exercises?muscle_id=" + ",".join(two_muscles)))
multi = data_of(resp)
assert multi, multi
assert {str(e["muscle_id"]) for e in multi} <= set(two_muscles), multi

resp = show("exercises ?sort=muscle", anon.get("/api/exercises?sort=muscle"))
sorted_names = [e["muscle_name"] for e in data_of(resp)]
assert sorted_names == sorted(sorted_names), "sort=muscle must group by muscle name"

for bad in ("?sort=sideways", "?muscle_id=abc", "?muscle_id=1,x", "?q=" + "z" * 101):
    resp = anon.get("/api/exercises" + bad)
    assert resp.status_code == 400, (bad, resp.get_json())
print(f"  {'catalogue bad query args rejected':<38} 400  sort/muscle_id/q")

# --- detail: public facts, personal numbers withheld -------------------
detail_id = exercises[0]["exercise_id"]
resp = show("GET /api/exercises/<id> (anon)", anon.get(f"/api/exercises/{detail_id}"))
detail = data_of(resp)
assert detail["exercise"]["exercise_id"] == detail_id, detail
assert "description" in detail["exercise"], detail
assert detail["history"] is None, "an anonymous visitor must get no personal history"

resp = show("GET /api/exercises/999999", anon.get("/api/exercises/999999"))
assert resp.status_code == 404 and resp.get_json()["error"]["code"] == "not_found"

muscle_id = muscles[0]["muscle_id"]
filtered = data_of(show(f"GET /api/exercises?muscle_id={muscle_id}",
                        anon.get(f"/api/exercises?muscle_id={muscle_id}")))
assert isinstance(filtered, list)
assert len(filtered) <= len(exercises), "filter returned more than the full list"


print("\n-- logged out: every protected route is JSON 401 --------------")
for path in PROTECTED:
    resp = show(f"GET {path}", anon.get(path))
    assert resp.status_code == 401
    assert resp.get_json() == {"error": {"code": "unauthorized",
                                         "message": "Authentication required."}}

for path in ("/api/stats/summary", "/api/stats/volume",
             "/api/stats/muscle-distribution", "/api/personal-records"):
    assert show(f"GET {path}", anon.get(path)).status_code == 401

resp = show("POST /api/log-workout", anon.post("/api/log-workout", json={}))
assert resp.status_code == 401 and resp.get_json()["error"]["code"] == "unauthorized"

resp = show("GET /api/nope", anon.get("/api/nope"))
assert resp.status_code == 404 and resp.get_json()["error"]["code"] == "not_found"
resp = show("GET /api/login (wrong method)", anon.get("/api/login"))
assert resp.status_code == 405 and resp.get_json()["error"]["code"] == "method_not_allowed"

# No framework text may reach a user. Werkzeug's own descriptions read like
# "The method is not allowed for the requested URL" and "If you entered the URL
# manually please check your spelling", and the limiter's 429 is the raw rule.
FRAMEWORK_TELLS = ("requested URL", "check your spelling", "per 1 minute",
                   "Traceback", "werkzeug", "The server")
for path, method in (("/api/nope", "get"), ("/api/login", "get")):
    message = getattr(anon, method)(path).get_json()["error"]["message"]
    for tell in FRAMEWORK_TELLS:
        assert tell.lower() not in message.lower(), (path, message)
print(f"  {'error copy is human, not framework text':<38} 404 and 405 checked")


if WRITE:
    print("\n-- signup, login, log a set (writes rows) ---------------------")
    user = app.test_client()
    email = f"smoke+{int(time.time())}@ezgrind.test"
    account = {
        "full_name": "Smoke Test", "email": email, "password": "smoke-password",
        "contact_number": "9999999999", "date_of_birth": "1990-01-01",
        "height_cm": "180", "weight_kg": "75", "fitness_goal": "muscle",
    }

    resp = show("POST /api/signup", user.post("/api/signup", json=account))
    assert resp.status_code == 200, resp.get_json()
    new_user_id = data_of(resp)["user_id"]
    assert resp.get_json()["message"] == "Signup successful \U0001f389"

    resp = show("POST /api/signup (duplicate)", user.post("/api/signup", json=account))
    assert resp.status_code == 400 and resp.get_json()["error"]["code"] == "email_exists"
    # The form attaches this to the email input, so it must name the field.
    assert resp.get_json()["error"]["field"] == "email", resp.get_json()

    for bad_field, payload in (
        ("full_name", {**account, "full_name": "Sm0ke"}),
        ("email", {**account, "email": "not-an-email"}),
        ("password", {**account, "password": "short"}),
        ("contact_number", {**account, "contact_number": "123"}),
        ("height_cm", {**account, "height_cm": "-5"}),
        ("fitness_goal", {**account, "fitness_goal": ""}),
    ):
        resp = user.post("/api/signup", json=payload)
        assert resp.status_code == 400, (bad_field, resp.get_json())
        assert resp.get_json()["error"].get("field") == bad_field, resp.get_json()
    print(f"  {'per-field validation errors':<38} 400  all six name their field")

    resp = show("POST /api/login (wrong password)",
                user.post("/api/login", json={"email": email, "password": "wrong-one"}))
    assert resp.status_code == 401 and resp.get_json()["error"]["code"] == "invalid_credentials"

    resp = show("POST /api/login", user.post(
        "/api/login", json={"email": email, "password": account["password"]}))
    assert resp.status_code == 200
    payload = data_of(resp)
    # Rule 6: login must return the user, or login.html can never redirect.
    assert set(payload) == {"user_id", "full_name", "email"}, payload
    assert payload["user_id"] == new_user_id and payload["email"] == email

    resp = show("GET /api/me", user.get("/api/me"))
    profile = data_of(resp)
    assert profile["email"] == email and profile["full_name"] == "Smoke Test"
    assert "password_hash" not in profile, "password hash leaked into /api/me"

    resp = show("POST /api/log-workout", user.post("/api/log-workout", json={
        "exercise_id": exercises[0]["exercise_id"], "weight": "60", "reps": "8",
        "comments": "",   # blank optional must not 500
    }))
    assert resp.status_code == 200, resp.get_json()
    logged = data_of(resp)
    # set_order arrives with migration 002; a KeyError here means it has not
    # been applied yet.
    assert set(logged) == {"workout_id", "set_id", "set_order"}, logged
    assert logged["set_order"] >= 1, logged

    # Logging twice on the same day must reuse the workout and advance the order.
    resp = show("POST /api/log-workout (2nd set)", user.post("/api/log-workout", json={
        "exercise_id": exercises[0]["exercise_id"], "weight": "62.5", "reps": "6",
    }))
    second = data_of(resp)
    assert second["workout_id"] == logged["workout_id"], "duplicate workout row created"
    assert second["set_order"] == logged["set_order"] + 1, second

    resp = show("POST /api/log-workout (with comment)", user.post("/api/log-workout", json={
        "exercise_id": exercises[0]["exercise_id"], "weight": "65", "reps": "5",
        "comments": "Felt heavy, dropped the last rep.",
    }))
    assert resp.status_code == 200, resp.get_json()

    resp = show("POST /api/log-workout (comment too long)", user.post("/api/log-workout", json={
        "exercise_id": exercises[0]["exercise_id"], "weight": "65", "reps": "5",
        "comments": "x" * 501,
    }))
    assert resp.status_code == 400 and resp.get_json()["error"]["code"] == "validation_error"

    today = data_of(show("GET /api/today-workout", user.get("/api/today-workout")))
    assert any(row["total_sets"] >= 1 for row in today), today

    # --- today-sets: individual rows, addressable by id ---------------
    rows = data_of(show("GET /api/today-sets", user.get("/api/today-sets")))
    assert len(rows) == 3, rows
    for field in ("set_id", "exercise_name", "weight", "reps", "set_order", "created_at"):
        assert field in rows[0], f"/api/today-sets missing {field!r}: {rows[0]}"
    assert [r["set_order"] for r in rows] == [1, 2, 3], rows

    # --- last-set prefill ---------------------------------------------
    resp = show("GET /api/exercises/<id>/last-set",
                user.get(f"/api/exercises/{exercises[0]['exercise_id']}/last-set"))
    last = data_of(resp)
    assert last is not None and "weight" in last and "reps" in last, last

    unlogged = next(e for e in exercises if e["exercise_id"] != exercises[0]["exercise_id"])
    resp = show("GET last-set (never logged)",
                user.get(f"/api/exercises/{unlogged['exercise_id']}/last-set"))
    assert data_of(resp) is None, "an exercise with no history must resolve to null"

    # --- delete, and the ownership check -------------------------------
    victim_set = rows[0]["set_id"]

    stranger = app.test_client()
    resp = show("DELETE someone else's set", stranger.delete(f"/api/workout-sets/{victim_set}"))
    assert resp.status_code == 401, "signed out must not reach the handler"

    other_email = f"smoke-other+{int(time.time())}@ezgrind.test"
    other_signup = stranger.post("/api/signup", json={**account, "email": other_email})
    other_user_id = other_signup.get_json()["data"]["user_id"]
    stranger.post("/api/login", json={"email": other_email, "password": account["password"]})

    resp = show("DELETE another user's set", stranger.delete(f"/api/workout-sets/{victim_set}"))
    # 404, never 403: a 403 would confirm the id exists and turn this into an oracle.
    assert resp.status_code == 404, resp.get_json()
    assert resp.get_json()["error"]["code"] == "not_found", resp.get_json()

    assert len(data_of(user.get("/api/today-sets"))) == 3, "the set must still be there"

    resp = show("DELETE own set", user.delete(f"/api/workout-sets/{victim_set}"))
    assert resp.status_code == 200, resp.get_json()

    remaining = data_of(user.get("/api/today-sets"))
    assert len(remaining) == 2, remaining
    assert victim_set not in [r["set_id"] for r in remaining]

    resp = show("DELETE the same set again", user.delete(f"/api/workout-sets/{victim_set}"))
    assert resp.status_code == 404, "a second delete must not report success"

    # The deleted set was the heaviest (60x8 -> 1RM 76.0), so the record it
    # created must NOT survive it. A stale PR here would be a claim about a set
    # that no longer exists - which is what happens if delete forgets to
    # recompute, and a mistyped weight is the usual reason to delete.
    after_delete = data_of(user.get("/api/personal-records"))
    assert len(after_delete) == 1, after_delete
    assert after_delete[0]["best_weight"] == 65.0, \
        f"PR still points at the deleted set: {after_delete[0]}"
    print(f"  {'PR recomputed after delete':<38} stale record did not survive")

    # --- bounds, mirrored from validators.py ---------------------------
    for label, payload in (
        ("weight 501", {"weight": "501", "reps": "5"}),
        ("weight 2dp", {"weight": "60.25", "reps": "5"}),
        ("reps 0", {"weight": "60", "reps": "0"}),
        ("reps 101", {"weight": "60", "reps": "101"}),
    ):
        body = {"exercise_id": exercises[0]["exercise_id"], **payload}
        resp = user.post("/api/log-workout", json=body)
        assert resp.status_code == 400, (label, resp.get_json())
        assert resp.get_json()["error"].get("field") in ("weight", "reps"), resp.get_json()
    print(f"  {'set bounds rejected':<38} 400  weight 0-500/1dp, reps 1-100")

    # --- history: sessions, not rows -----------------------------------
    resp = show("GET /api/workout-history", user.get("/api/workout-history"))
    body = resp.get_json()
    sessions = body["data"]
    assert "meta" in body, body
    for key in ("page", "limit", "total", "has_more"):
        assert key in body["meta"], body["meta"]
    assert body["meta"]["page"] == 1 and body["meta"]["limit"] == 20

    assert len(sessions) == 1, sessions
    today_session = sessions[0]
    for key in ("workout_date", "total_sets", "total_volume", "exercise_count",
                "duration_estimate", "exercises"):
        assert key in today_session, today_session

    # Two sets survive the earlier delete, and the totals must reflect that.
    assert today_session["total_sets"] == 2, today_session
    assert today_session["exercise_count"] == 1, today_session
    assert len(today_session["exercises"]) == 1

    exercise = today_session["exercises"][0]
    for key in ("exercise_name", "muscle_name", "sets"):
        assert key in exercise, exercise
    assert len(exercise["sets"]) == 2, exercise
    for key in ("set_id", "weight", "reps", "set_order"):
        assert key in exercise["sets"][0], exercise["sets"][0]

    # 62.5 x 6 + 65 x 5 = 700
    assert abs(today_session["total_volume"] - 700) < 0.01, today_session["total_volume"]

    # --- pagination ----------------------------------------------------
    resp = show("history ?limit=1", user.get("/api/workout-history?limit=1"))
    meta = resp.get_json()["meta"]
    assert meta["limit"] == 1 and meta["total"] == 1
    assert meta["has_more"] is False, meta

    resp = show("history ?page=99 (past the end)", user.get("/api/workout-history?page=99"))
    assert data_of(resp) == [], "a page past the end is empty, not an error"

    for bad in ("?limit=0", "?limit=101", "?page=0", "?limit=abc", "?from=29-07-2026"):
        resp = user.get("/api/workout-history" + bad)
        assert resp.status_code == 400, (bad, resp.get_json())
    print(f"  {'history bad query args rejected':<38} 400  limit/page bounds, date format")

    # --- filters -------------------------------------------------------
    muscle_of_logged = exercise["muscle_name"]
    matching_muscle = next(m for m in muscles if m["muscle_name"] == muscle_of_logged)
    other_muscle = next(m for m in muscles if m["muscle_name"] != muscle_of_logged)

    resp = show("history ?muscle_id=<matching>",
                user.get(f"/api/workout-history?muscle_id={matching_muscle['muscle_id']}"))
    assert len(data_of(resp)) == 1, "the session trained this muscle"

    resp = show("history ?muscle_id=<other>",
                user.get(f"/api/workout-history?muscle_id={other_muscle['muscle_id']}"))
    assert data_of(resp) == [], "no session trained that muscle"

    resp = show("history ?from=tomorrow", user.get("/api/workout-history?from=2099-01-01"))
    assert data_of(resp) == [], "nothing is logged in 2099"

    resp = show("history ?to=yesterday", user.get("/api/workout-history?to=2000-01-01"))
    assert data_of(resp) == [], "nothing is logged in 2000"

    # --- exercise detail: personal stats, scoped to the session ---------
    logged_id = exercises[0]["exercise_id"]
    resp = show("exercise detail (signed in)", user.get(f"/api/exercises/{logged_id}"))
    stats = data_of(resp)["history"]
    assert stats is not None, "a signed-in user must get their history block"
    assert stats["total_sets"] == 2, stats
    assert stats["best_set"] is not None and stats["estimated_1rm"] > 0, stats
    assert stats["last_performed"] is not None, stats
    assert 0 < len(stats["recent_sets"]) <= 10, stats

    # 65 x 5 beats 62.5 x 6 on Epley, so it must be the best set.
    assert stats["best_set"]["weight"] == 65.0, stats["best_set"]

    # The other account logged nothing: same exercise, empty numbers, and
    # crucially not the first user's.
    resp = show("exercise detail (other user)", stranger.get(f"/api/exercises/{logged_id}"))
    other_stats = data_of(resp)["history"]
    assert other_stats["total_sets"] == 0, other_stats
    assert other_stats["best_set"] is None and other_stats["recent_sets"] == [], other_stats

    # --- one user's history never leaks into another's ------------------
    resp = show("history as the other user", stranger.get("/api/workout-history"))
    assert data_of(resp) == [], "the second account logged nothing and must see nothing"

    # Survives a reload: two of the three sets remain after the delete above.
    assert len(data_of(user.get("/api/today-sets"))) == 2

    # --- stats: shape, scoping, and no user_id parameter ----------------
    resp = show("GET /api/stats/summary", user.get("/api/stats/summary"))
    stats = data_of(resp)
    for key in ("current_streak", "longest_streak", "workouts_this_week",
                "workouts_this_month", "total_workouts", "total_sets",
                "total_volume_kg", "favourite_muscle_group",
                "avg_sets_per_workout", "week_activity"):
        assert key in stats, f"summary missing {key!r}: {sorted(stats)}"

    # Three sets logged today, one of them deleted -> two remain, one workout.
    assert stats["total_workouts"] == 1, stats
    assert stats["total_sets"] == 2, stats
    assert stats["current_streak"] == 1 and stats["longest_streak"] == 1, stats
    assert stats["workouts_this_week"] == 1, stats
    # 62.5 x 6 + 65 x 5 = 700
    assert abs(stats["total_volume_kg"] - 700) < 0.01, stats["total_volume_kg"]
    assert stats["avg_sets_per_workout"] == 2.0, stats
    assert stats["favourite_muscle_group"] is not None, stats
    assert len(stats["week_activity"]) == 7 and stats["week_activity"][-1]["trained"]

    # THE SCOPING TEST: a user_id in the query string must be ignored, and the
    # caller must still see only their own numbers.
    resp = show("summary ?user_id=<other user>",
                user.get(f"/api/stats/summary?user_id={other_user_id}"))
    assert data_of(resp)["total_sets"] == 2, "a supplied user_id must change nothing"

    resp = show("summary as the other user", stranger.get("/api/stats/summary"))
    empty = data_of(resp)
    assert empty["total_workouts"] == 0 and empty["total_sets"] == 0, empty
    assert empty["current_streak"] == 0 and empty["total_volume_kg"] == 0, empty
    assert empty["favourite_muscle_group"] is None, empty
    assert empty["avg_sets_per_workout"] == 0, "must not divide by zero"

    # --- volume series --------------------------------------------------
    for period in ("week", "month", "year"):
        resp = show(f"volume ?period={period}", user.get(f"/api/stats/volume?period={period}"))
        body = resp.get_json()
        assert body["meta"]["period"] == period, body["meta"]
        points = body["data"]
        assert len(points) == 1, points
        for key in ("date", "volume", "sets"):
            assert key in points[0], points[0]
        assert abs(points[0]["volume"] - 700) < 0.01, points[0]
        # Must be a real ISO date, not an unsubstituted format string. Checking
        # only that the key exists let "%Y-%m-01" through once already.
        try:
            datetime.strptime(points[0]["date"], "%Y-%m-%d")
        except ValueError:
            raise AssertionError(
                f"period={period} returned {points[0]['date']!r}, not an ISO date")

    assert user.get("/api/stats/volume?period=decade").status_code == 400

    # --- muscle distribution --------------------------------------------
    resp = show("muscle-distribution", user.get("/api/stats/muscle-distribution"))
    spread = data_of(resp)
    assert len(spread) == 1, spread
    assert spread[0]["sets"] == 2, spread
    assert abs(spread[0]["percentage"] - 100.0) < 0.01, spread
    assert sum(row["percentage"] for row in spread) <= 100.01, spread
    assert data_of(stranger.get("/api/stats/muscle-distribution")) == []

    # --- personal records, written by log_set in the same transaction -----
    resp = show("GET /api/personal-records", user.get("/api/personal-records"))
    prs = data_of(resp)
    assert len(prs) == 1, prs
    record = prs[0]
    for key in ("exercise_name", "muscle_name", "best_weight", "best_reps",
                "estimated_1rm", "achieved_on"):
        assert key in record, record

    # 65x5 -> 65*(1+5/30) = 75.83 beats 62.5x6 -> 72.92, so the heavier set wins.
    assert record["best_weight"] == 65.0, record
    assert record["best_reps"] == 5, record
    assert abs(record["estimated_1rm"] - 75.83) < 0.05, record
    # The stored 1RM must agree with its own weight and reps - this is what the
    # ON DUPLICATE KEY assignment order protects.
    assert abs(record["estimated_1rm"]
               - record["best_weight"] * (1 + record["best_reps"] / 30)) < 0.05, record

    assert data_of(stranger.get("/api/personal-records")) == [], "PRs must not cross users"
    print(f"  {'PR agrees with its own weight/reps':<38} upsert order verified")

    # --- bodyweight log --------------------------------------------------
    # Runs after the profile checks: logging a weight rewrites users.weight_kg,
    # which is exactly what the BMI assertions above depend on.
    fresh = data_of(user.get("/api/stats/summary"))
    assert fresh["starting_weight"] is None, fresh
    assert fresh["weight_change_30d"] is None, "no history means no change, not 0.0"
    assert fresh["current_weight"] == 75.0, "falls back to the signup figure"

    resp = show("POST /api/weight-logs", user.post("/api/weight-logs", json={"weight_kg": "80.5"}))
    logged = data_of(resp)
    assert logged["weight_kg"] == 80.5, logged
    first_log_id = logged["log_id"]

    # Logging twice in one day corrects rather than duplicates.
    resp = show("POST again, same day", user.post("/api/weight-logs", json={"weight_kg": "81"}))
    assert data_of(resp)["log_id"] == first_log_id, "a second entry must reuse the row"
    assert len(data_of(user.get("/api/weight-logs"))) == 1, "one entry per day"

    # The profile figure and BMI follow the log.
    assert data_of(user.get("/api/me"))["weight_kg"] == 81.0, "profile did not follow"

    # A BACKDATED entry must not clobber the current weight.
    old_day = (date.today() - timedelta(days=40)).isoformat()
    resp = show("POST backdated 40 days",
                user.post("/api/weight-logs", json={"weight_kg": "90", "logged_on": old_day}))
    assert data_of(resp)["weight_kg"] == 90.0
    assert data_of(user.get("/api/me"))["weight_kg"] == 81.0, \
        "a backdated log overwrote the current weight"

    entries = data_of(show("GET /api/weight-logs", user.get("/api/weight-logs")))
    assert len(entries) == 2, entries
    assert entries[0]["weight_kg"] == 90.0, "oldest first"
    assert entries[-1]["weight_kg"] == 81.0, entries

    # 81 now vs the 90 logged before the window opened -> -9.0
    stats_now = data_of(user.get("/api/stats/summary"))
    assert stats_now["current_weight"] == 81.0, stats_now
    assert stats_now["starting_weight"] == 90.0, stats_now
    assert stats_now["weight_change_30d"] == -9.0, stats_now["weight_change_30d"]

    # Range filters.
    recent_only = data_of(user.get(f"/api/weight-logs?from={date.today().isoformat()}"))
    assert len(recent_only) == 1 and recent_only[0]["weight_kg"] == 81.0, recent_only
    assert data_of(user.get("/api/weight-logs?to=2000-01-01")) == []

    for bad in ('{"weight_kg": "5"}', '{"weight_kg": "900"}',
                '{"weight_kg": "80.555"}', '{"weight_kg": "x"}'):
        resp = user.post("/api/weight-logs", data=bad,
                         content_type="application/json")
        assert resp.status_code == 400, (bad, resp.get_json())
        assert resp.get_json()["error"]["field"] == "weight_kg", resp.get_json()

    future = (date.today() + timedelta(days=1)).isoformat()
    resp = user.post("/api/weight-logs", json={"weight_kg": "80", "logged_on": future})
    assert resp.status_code == 400 and resp.get_json()["error"]["field"] == "logged_on"
    print(f"  {'weight bounds and future dates rejected':<38} 400  20-500kg, 2dp, no future")

    # Ownership: 404 rather than 403, so the id space stays private.
    resp = show("DELETE another user's entry", stranger.delete(f"/api/weight-logs/{first_log_id}"))
    assert resp.status_code == 404, resp.get_json()
    assert len(data_of(user.get("/api/weight-logs"))) == 2, "the entry must survive"

    # Deleting the NEWEST entry must roll the profile back to the previous one.
    resp = show("DELETE own newest entry", user.delete(f"/api/weight-logs/{first_log_id}"))
    assert resp.status_code == 200, resp.get_json()
    assert data_of(user.get("/api/me"))["weight_kg"] == 90.0, \
        "profile still points at the deleted entry"
    print(f"  {'delete resynced the profile weight':<38} rolled back to the previous log")

    assert stranger.get("/api/weight-logs").status_code == 200
    assert data_of(stranger.get("/api/weight-logs")) == [], "logs must not cross users"

    # Leave the fixture as it was found. The profile assertions below expect the
    # signup figures, and a block that mutates shared state should clean up
    # after itself rather than making the next block's failure a mystery.
    for entry in data_of(user.get("/api/weight-logs")):
        user.delete(f"/api/weight-logs/{entry['log_id']}")
    assert data_of(user.get("/api/weight-logs")) == []

    # Removing every log must NOT null the profile weight - the signup figure is
    # still the best answer available.
    assert data_of(user.get("/api/me"))["weight_kg"] == 90.0, \
        "deleting every log wiped the profile weight"

    user.patch("/api/me", json={"weight_kg": "75"})
    assert data_of(user.get("/api/me"))["weight_kg"] == 75.0

    # --- profile: computed fields, null-safe ----------------------------
    resp = show("GET /api/me (computed)", user.get("/api/me"))
    me = data_of(resp)
    for key in ("created_at", "age", "bmi", "bmi_category", "contact_number"):
        assert key in me, f"/api/me missing {key!r}: {sorted(me)}"
    # The signup fixture supplies 180cm / 75kg -> 23.1, "Normal".
    assert me["bmi"] == 23.1, me["bmi"]
    assert me["bmi_category"] == "Normal", me["bmi_category"]
    assert me["age"] is not None and me["age"] > 0, me["age"]

    # --- PATCH: partial, unknown keys ignored, empty clears -------------
    resp = show("PATCH /api/me (one field)",
                user.patch("/api/me", json={"fitness_goal": "lose"}))
    patched = data_of(resp)
    assert patched["fitness_goal"] == "lose", patched
    assert patched["full_name"] == "Smoke Test", "an unsent field must not change"

    resp = show("PATCH with an unknown key",
                user.patch("/api/me", json={"nonsense": "x", "full_name": "Smoke Tested"}))
    assert data_of(resp)["full_name"] == "Smoke Tested", "unknown keys are ignored"

    resp = show("PATCH clears via empty string",
                user.patch("/api/me", json={"contact_number": ""}))
    assert data_of(resp)["contact_number"] is None, "empty string must clear the column"

    # Clearing height must take BMI with it rather than leaving a stale number.
    resp = show("PATCH clears height -> bmi null",
                user.patch("/api/me", json={"height_cm": ""}))
    cleared = data_of(resp)
    assert cleared["height_cm"] is None, cleared
    assert cleared["bmi"] is None and cleared["bmi_category"] is None, cleared

    resp = show("PATCH restores height", user.patch("/api/me", json={"height_cm": "180"}))
    assert data_of(resp)["bmi"] == 23.1

    for label, body, field in (
        ("empty full_name", {"full_name": ""}, "full_name"),
        ("numeric name", {"full_name": "R2D2"}, "full_name"),
        ("bad goal", {"fitness_goal": "swimming"}, "fitness_goal"),
        ("future dob", {"date_of_birth": "2099-01-01"}, "date_of_birth"),
        ("malformed dob", {"date_of_birth": "01-01-1990"}, "date_of_birth"),
        ("negative height", {"height_cm": "-5"}, "height_cm"),
        ("short phone", {"contact_number": "123"}, "contact_number"),
    ):
        resp = user.patch("/api/me", json=body)
        assert resp.status_code == 400, (label, resp.get_json())
        assert resp.get_json()["error"].get("field") == field, (label, resp.get_json())
    print(f"  {'PATCH validation rejects bad fields':<38} 400  all seven name their field")

    resp = user.patch("/api/me", json={})
    assert resp.status_code == 400, resp.get_json()

    # --- password change ------------------------------------------------
    resp = show("password (wrong current)", user.post("/api/me/password", json={
        "current_password": "not-my-password", "new_password": "another-secret"}))
    assert resp.status_code == 400
    assert resp.get_json()["error"]["field"] == "current_password", resp.get_json()

    resp = show("password (too short)", user.post("/api/me/password", json={
        "current_password": account["password"], "new_password": "abc"}))
    assert resp.status_code == 400 and resp.get_json()["error"]["field"] == "new_password"

    resp = show("password (same as current)", user.post("/api/me/password", json={
        "current_password": account["password"], "new_password": account["password"]}))
    assert resp.status_code == 400 and resp.get_json()["error"]["field"] == "new_password"

    rotated = account["password"] + "-rotated"
    resp = show("password (valid)", user.post("/api/me/password", json={
        "current_password": account["password"], "new_password": rotated}))
    assert resp.status_code == 200, resp.get_json()

    # The session must survive: the user just proved who they are.
    assert user.get("/api/me").status_code == 200, "password change must not sign the user out"

    # The old password must be dead and the new one live.
    checker = app.test_client()
    assert checker.post("/api/login", json={
        "email": email, "password": account["password"]}).status_code == 401
    assert checker.post("/api/login", json={
        "email": email, "password": rotated}).status_code == 200
    print(f"  {'old password rejected, new accepted':<38} 401/200")

    resp = show("POST /api/logout", user.post("/api/logout"))
    assert resp.get_json()["message"] == "Logged out"
    assert show("GET /api/me (after logout)", user.get("/api/me")).status_code == 401

    # --- account deletion, last because it is irreversible ---------------
    doomed = app.test_client()
    doomed.post("/api/login", json={"email": email, "password": rotated})

    resp = show("DELETE /api/me (wrong password)",
                doomed.delete("/api/me", json={"password": "not-it"}))
    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json()["error"]["field"] == "password", resp.get_json()
    assert doomed.get("/api/me").status_code == 200, \
        "a refused deletion must not sign the user out"

    resp = show("DELETE /api/me", doomed.delete("/api/me", json={"password": rotated}))
    assert resp.status_code == 200, resp.get_json()
    assert doomed.get("/api/me").status_code == 401, "the session must be cleared"

    assert app.test_client().post("/api/login", json={
        "email": email, "password": rotated}).status_code == 401, \
        "a deleted account must not be able to log back in"

    with get_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS n FROM users WHERE user_id = %s", (new_user_id,))
        assert cursor.fetchone()["n"] == 0, "the user row survived deletion"

        cursor.execute("SELECT COUNT(*) AS n FROM workouts WHERE user_id = %s", (new_user_id,))
        assert cursor.fetchone()["n"] == 0, "workouts survived deletion"

        # The cascade must not leave sets pointing at a workout that is gone.
        cursor.execute("""
            SELECT COUNT(*) AS n FROM workout_sets ws
            LEFT JOIN workouts w ON w.workout_id = ws.workout_id
            WHERE w.workout_id IS NULL
        """)
        assert cursor.fetchone()["n"] == 0, "orphaned workout_sets left behind"

    print(f"  {'deletion cascaded':<38} user, workouts and sets all gone")

    # Tidy up the second account too, so a --write run leaves nothing behind.
    stranger.delete("/api/me", json={"password": account["password"]})
    print(f"\n  test accounts cleaned up ({email} and the second one)")
else:
    print("\n-- skipping signup / log-a-set (pass --write to include them) --")


print("\n-- bad input is 400, never 500 --------------------------------")
assert show("POST /api/login (no body)", anon.post("/api/login")).status_code == 400
assert show("POST /api/login (not JSON)", anon.post("/api/login", data="hi")).status_code == 400
resp = show("POST /api/signup (missing keys)", anon.post("/api/signup", json={"email": "a@b.co"}))
assert resp.status_code == 400 and resp.get_json()["error"]["code"] == "validation_error"


print("\n-- CORS -------------------------------------------------------")
resp = anon.get("/api/me", headers={"Origin": ORIGIN})
assert resp.headers.get("Access-Control-Allow-Origin") == ORIGIN, dict(resp.headers)
assert resp.headers.get("Access-Control-Allow-Credentials") == "true"
print(f"  allow-listed origin                    -> {ORIGIN} (credentials ok)")

resp = anon.get("/api/me", headers={"Origin": "https://evil.example"})
assert resp.headers.get("Access-Control-Allow-Origin") in (None, ""), dict(resp.headers)
print("  unknown origin                         -> no allow-origin header")


print("\n-- rate limiting ----------------------------------------------")
codes = [anon.post("/api/login", json={"email": "x@y.co", "password": "no"}).status_code
         for _ in range(12)]
assert 429 in codes, codes
resp = anon.post("/api/login", json={"email": "x@y.co", "password": "no"})
assert resp.get_json()["error"]["code"] == "rate_limited", resp.get_json()
print(f"  /api/login                             -> {codes.count(429)} of 12 got JSON 429")


print("\n-- session cookie flags ---------------------------------------")


def cookie_for(flask_env):
    os.environ["FLASK_ENV"] = flask_env
    for name in ("app", "config", "db", "errors", "auth", "validators"):
        sys.modules.pop(name, None)
    rebuilt = importlib.import_module("app").app
    with rebuilt.test_client() as fresh:
        with fresh.session_transaction() as sess:
            sess.permanent = True
            sess["user_id"] = 1
        return rebuilt, fresh.get("/").headers.get("Set-Cookie", "")


def expiry_days(header):
    """Werkzeug may express lifetime as Max-Age or Expires; accept either."""
    if "Max-Age=" in header:
        return round(int(header.split("Max-Age=")[1].split(";")[0]) / 86400)
    stamp = header.split("Expires=")[1].split(";")[0]
    return round((parsedate_to_datetime(stamp) - datetime.now(timezone.utc)).total_seconds() / 86400)


rebuilt, dev = cookie_for("development")
print(f"  development: {dev}")
assert "HttpOnly" in dev and "SameSite=Lax" in dev
assert "Secure" not in dev.replace("SameSite", "")
assert expiry_days(dev) == 7, expiry_days(dev)

rebuilt, prod = cookie_for("production")
print(f"  production:  {prod}")
assert "HttpOnly" in prod
# Lax in production too, now that Flask serves the frontend: the cookie is
# same-site by construction, so it never needs the weaker SameSite=None.
assert "SameSite=Lax" in prod and "Secure" in prod
assert expiry_days(prod) == 7, expiry_days(prod)
assert rebuilt.config["DEBUG"] is False

print("\nsmoke: all assertions passed"
      f"{'' if WRITE else '  (read-only run; --write covers signup and log-a-set)'}")
