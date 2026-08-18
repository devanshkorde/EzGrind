# EzGrind API

Base URL in development: `http://127.0.0.1:5000`

All endpoints live under `/api` except the root banner. Every response is JSON —
**no endpoint ever returns HTML**, including on error, so a client can parse the
body unconditionally.

---

## Conventions

### Success

```jsonc
{ "data": [...] }                                  // collection
{ "data": { ... } }                                // single object
{ "data": { ... }, "message": "Set deleted" }      // mutation
{ "data": [...], "meta": { "page": 1, ... } }      // paginated
```

### Error

```jsonc
{
  "error": {
    "code": "validation_error",
    "message": "Contact number must be 10 digits.",
    "field": "contact_number"     // present only when one field is at fault
  }
}
```

`field` is **omitted, not null**, when no single field is to blame — so a form can
attach the message to the right input without parsing the message text.

Messages are written for people. Framework text never reaches a client: a 404 says
"We couldn't find that", not Werkzeug's "If you entered the URL manually please
check your spelling".

### Authentication

A signed session cookie set by `POST /api/login`. `HttpOnly`, 7-day lifetime,
`SameSite=Lax` + insecure in development, `SameSite=None` + `Secure` in
production.

Endpoints marked **Auth: required** answer `401` when signed out:

```json
{ "error": { "code": "unauthorized", "message": "Authentication required." } }
```

### Scoping

**No endpoint accepts a user id.** Not in a path, not in a query string, not in a
body. Identity comes only from `session["user_id"]`. A stray `?user_id=9` is
ignored because nothing reads it.

Ownership failures answer **`404`, never `403`** — a 403 would confirm the id
exists and turn the endpoint into a way to enumerate other people's rows.

### Common error codes

| Status | `code` | When |
|---|---|---|
| 400 | `validation_error` | A field failed validation |
| 400 | `email_exists` | Signup with an address already registered |
| 400 | `invalid_password` | Current password wrong on change or delete |
| 401 | `unauthorized` | Not signed in |
| 401 | `invalid_credentials` | Wrong email or password on login |
| 404 | `not_found` | Missing, or not yours |
| 405 | `method_not_allowed` | Wrong verb |
| 429 | `rate_limited` | Too many attempts (10/min on the marked routes) |
| 500 | `internal_error` | Unexpected. Details are logged server-side, never returned |
| 503 | `database_unavailable` | `/api/health` only |

---

## Health

### `GET /`
**Auth:** none. Banner. → `{ "message": "EzGrind backend is running successfully 🚀" }`

### `GET /api/health`
**Auth:** none. → `200 { "data": { "status": "ok", "database": "connected" } }`
or `503 database_unavailable`. The only endpoint that must answer while the
database is down.

---

## Authentication

### `POST /api/signup`
**Auth:** none · **Rate limited:** 10/min

```jsonc
{
  "full_name": "Dev Korde",        // letters and spaces
  "email": "dev@example.com",
  "password": "at-least-6-chars",
  "contact_number": "9876543210",  // 10 digits, optional
  "date_of_birth": "1994-03-11",   // optional, not future
  "height_cm": "180",              // optional, whole number, > 0
  "weight_kg": "78",               // optional, whole number, > 0
  "fitness_goal": "muscle"         // gain | lose | maintain | muscle
}
```

→ `200 { "data": { "user_id": 12 }, "message": "Signup successful 🎉" }`
**Errors:** `400 validation_error` (with `field`), `400 email_exists` (`field: "email"`)

### `POST /api/login`
**Auth:** none · **Rate limited:** 10/min

`{ "email": "...", "password": "..." }`

→ `200 { "data": { "user_id", "full_name", "email" }, "message": "Login successful" }`
**Errors:** `401 invalid_credentials` — one message for both unknown-email and
wrong-password, so the endpoint can't be used to test whether an address is
registered.

### `POST /api/logout`
**Auth:** none (a no-op when already signed out) → `200 { "data": {}, "message": "Logged out" }`

---

## Profile

### `GET /api/me` · **Auth: required**

```jsonc
{ "data": {
    "full_name": "Dev Korde", "email": "dev@example.com",
    "contact_number": "9876543210", "date_of_birth": "Fri, 11 Mar 1994 …",
    "height_cm": 180.0, "weight_kg": 78.0, "fitness_goal": "muscle",
    "created_at": "Tue, 28 Jul 2026 …",
    "age": 32, "bmi": 24.1, "bmi_category": "Normal"
} }
```

`age`, `bmi` and `bmi_category` are computed server-side and are **`null`** when
their inputs are missing — never `0`, never a crash.

### `PATCH /api/me` · **Auth: required**

Partial update of `full_name`, `contact_number`, `date_of_birth`, `height_cm`,
`weight_kg`, `fitness_goal`. Unknown keys are ignored.

- **Key omitted** → field untouched
- **Key present but empty** → field cleared to `NULL`
- `full_name` is `NOT NULL`, so empty is a `400`

→ `200 { "data": { …full profile… }, "message": "Profile updated" }`

### `POST /api/me/password` · **Auth: required** · **Rate limited:** 10/min

`{ "current_password": "...", "new_password": "..." }`

Verifies the current password before changing anything. The session stays valid.
**Errors:** `400 invalid_password` (`field: "current_password"`),
`400 validation_error` if the new password is too short or unchanged.

### `DELETE /api/me` · **Auth: required** · **Rate limited:** 10/min

`{ "password": "..." }` — deletes the account, every workout and every set, in one
transaction, then clears the session. Irreversible.

---

## Exercise catalogue

### `GET /api/muscles` · **Auth:** none
→ `[{ "muscle_id", "muscle_name", "image_path" }]`

### `GET /api/equipment` · **Auth:** none
Distinct equipment values in use. → `["Barbell", "Bodyweight", "Cable", …]`

### `GET /api/exercises` · **Auth:** none

| Query | Meaning |
|---|---|
| `muscle_id` | Comma-separated: `?muscle_id=1,5,7`. A single id is a one-item list |
| `q` | Name search, ≤100 chars. LIKE wildcards are escaped, so `%` matches a literal `%` |
| `equipment` | Exact match |
| `sort` | `name` (default) or `muscle` |

→ `[{ "exercise_id", "exercise_name", "equipment", "description", "muscle_id", "muscle_name", "image_path" }]`
**Errors:** `400 validation_error` on an unknown `sort` or a non-numeric `muscle_id`.

### `GET /api/exercises/<id>` · **Auth:** optional

Catalogue facts for anyone; your own numbers only when signed in.

```jsonc
{ "data": {
    "exercise": { … },
    "history": {                    // null when signed out
      "total_sets": 12, "last_performed": "…",
      "best_set": { "weight": 65.0, "reps": 5, "workout_date": "…" },
      "estimated_1rm": 75.83,
      "recent_sets": [ … ]          // last 10
    }
} }
```

**Errors:** `404 not_found`.

### `GET /api/exercises/<id>/last-set` · **Auth: required**
Prefills the set form. → `{ "data": { "weight", "reps", "workout_date" } }` or
`{ "data": null }` when never logged.

---

## Workouts

### `POST /api/log-workout` · **Auth: required**

```jsonc
{ "exercise_id": 3, "weight": "62.5", "reps": 8, "comments": "felt heavy" }
```

- `weight` 0–500 kg, at most one decimal place
- `reps` 1–100, whole numbers
- `comments` optional, ≤500 characters

Reuses today's workout if one exists, creating it otherwise, and updates your
personal record for that exercise — all in one transaction.

→ `200 { "data": { "workout_id", "set_id", "set_order" }, "message": "Workout logged successfully 💪" }`

### `GET /api/today-sets` · **Auth: required**
Today's individual sets, addressable by id, in performed order.
→ `[{ "set_id", "exercise_id", "exercise_name", "weight", "reps", "comments", "set_order", "created_at" }]`

### `GET /api/today-workout` · **Auth: required**
Today's sets grouped by exercise. → `[{ "exercise_name", "total_sets" }]`

### `DELETE /api/workout-sets/<id>` · **Auth: required**
Deletes one set and recomputes that exercise's personal record from what remains,
so a mistyped weight doesn't leave a phantom PR behind.
**Errors:** `404 not_found` — same response whether the set is missing or someone
else's.

### `GET /api/workout-history` · **Auth: required**

| Query | Default | Meaning |
|---|---|---|
| `page` | 1 | |
| `limit` | 20 | 1–100 sessions per page |
| `from`, `to` | — | `YYYY-MM-DD` |
| `muscle_id`, `exercise_id` | — | Selects which **sessions** qualify; all sets in a matching session are returned |

```jsonc
{ "data": [{
     "workout_date": "…", "total_sets": 8, "total_volume": 3120.0,
     "exercise_count": 3, "duration_estimate": 47,
     "exercises": [{ "exercise_name", "muscle_name",
                     "sets": [{ "set_id", "weight", "reps", "tut", "set_order" }] }]
   }],
  "meta": { "page": 1, "limit": 20, "total": 34, "has_more": true } }
```

`duration_estimate` is minutes between the first and last set of the day, and is
`0` for sessions logged before per-set timestamps existed.

---

## Statistics

All **Auth: required** and scoped to the session user.

### `GET /api/stats/summary`

```jsonc
{ "data": {
    "current_streak": 4, "longest_streak": 11,
    "workouts_this_week": 3, "workouts_this_month": 12,
    "total_workouts": 58, "total_sets": 640, "total_volume_kg": 214300.0,
    "favourite_muscle_group": "Chest", "avg_sets_per_workout": 11.0,
    "week_activity": [{ "date": "2026-07-25", "trained": true }, …],
    "current_weight": 78.4, "starting_weight": 81.0, "weight_change_30d": -1.2
} }
```

**Streak rule:** consecutive calendar days with at least one set, counting back
from today; a session logged **today or yesterday** keeps it alive, so it doesn't
appear to break partway through a day you haven't trained yet.

`weight_change_30d` is **`null`**, not `0`, when there isn't enough history to
compare — "no change" and "can't say" are different answers.

### `GET /api/stats/volume?period=week|month|year`
Daily points for `week`/`month`, monthly for `year`.
→ `{ "data": [{ "date", "volume", "sets" }], "meta": { "period" } }`

### `GET /api/stats/muscle-distribution?period=week|month|year`
→ `[{ "muscle_id", "muscle_name", "sets", "percentage" }]`

### `GET /api/personal-records`
Best set per exercise by estimated 1RM (Epley: `weight × (1 + reps/30)`).
→ `[{ "exercise_id", "exercise_name", "muscle_name", "best_weight", "best_reps", "estimated_1rm", "achieved_on" }]`

Maintained inside the set-insert transaction. It is a cache — the statement that
rebuilds it from `workout_sets` is in `Database/queries/scratch.sql`.

---

## Bodyweight

### `POST /api/weight-logs` · **Auth: required**

`{ "weight_kg": "78.4", "logged_on": "2026-07-30" }` — `logged_on` optional,
defaults to today, never in the future. 20–500 kg, ≤2 decimals.

Upserts on `(user_id, logged_on)`, so logging twice in a day **corrects** rather
than duplicating. Also points `users.weight_kg` at your **most recent** entry —
which is why backdating doesn't clobber your current weight.

→ `200 { "data": { "log_id", "logged_on", "weight_kg" }, "message": "Weight logged" }`

### `GET /api/weight-logs` · **Auth: required**
Query: `from`, `to`, `limit` (≤2000). **Oldest first** — the chart is the primary
consumer. A `limit` takes the newest *n* and returns them oldest-first.

### `DELETE /api/weight-logs/<id>` · **Auth: required**
Deletes one entry and resyncs `users.weight_kg` to whatever is now most recent.
**Errors:** `404 not_found`.
