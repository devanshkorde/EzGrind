# EzGrind — Pre-Launch Audit

**Date:** 2026-08-01 · **Scope:** report only, nothing fixed
**Method:** static cross-referencing plus one live end-to-end run against the
development database.

---

## 0. A correction to the premise, because it changes the conclusion

The brief says per-phase verification was skipped. That is half true, and the
half that is true is the important one.

**What did run, every phase:** `smoke.py`, `check_frontend.py` and
`check_stats.js`. They passed each time, and they caught real defects —
a personal-record upsert that corrupted its own row through MySQL's
left-to-right assignment order, a `?period=year` bucket returning the literal
string `%Y-%m-01`, and a stale PR surviving the deletion of the set that created
it.

**What has never happened:** anybody opening the app in a browser. No rendered
page has been looked at. No click path has been walked. Every phase report closed
with "not verified: anything visual."

So this audit can speak with confidence about the API, the data layer and the
structural integrity of the frontend. It **cannot** tell you whether the app
looks right, and neither can any check in the repository.

---

## 1. Critical path

Exercised live against MySQL on 2026-08-01 via `smoke.py --write`, which drives
the real Flask app through its test client. Exit code 0.

| Step | Verdict | Evidence |
|---|---|---|
| **Signup** | ✅ Works | `POST /api/signup` → `200 {"data":{"user_id":45}}`. Validation covered: seven bad-field cases each return 400 naming the offending field. Duplicate email → `400 email_exists`, `field: "email"`. |
| **Login** | ✅ Works | `POST /api/login` → `200` with `{user_id, full_name, email}`. Wrong password → `401 invalid_credentials`, same message for unknown email so the endpoint can't test whether an address is registered. |
| **Session survives refresh** | ✅ Works | Cookie asserted in `smoke.py`: dev emits `HttpOnly; Path=/; SameSite=Lax`, 7-day expiry; production emits `Secure; HttpOnly; SameSite=None`. Both verified by rebuilding the app under each `FLASK_ENV`. `GET /api/me` on a fresh request with only the cookie → `200`. |
| **Log a set** | ✅ Works | `POST /api/log-workout` → `200 {"set_id":70,"set_order":1,"workout_id":60}`. Three sets logged in one run all share `workout_id`, proving the upsert reuses the day's workout rather than creating duplicates. |
| **Today's workout** | ✅ Works | `GET /api/today-workout` → `[{"exercise_name":"Back Extensions","total_sets":3}]`. `GET /api/today-sets` returns the three individually with `set_order` 1,2,3. |
| **History** | ✅ Works | `GET /api/workout-history` returns grouped sessions with `total_sets`, `total_volume`, `exercise_count`, nested exercises and sets. Volume arithmetic checked against known input (62.5×6 + 65×5 = 700 kg). Pagination, four filters and `?page=99` (empty, not an error) all asserted. |
| **Profile** | ✅ Works | `GET /api/me` → `200` with computed `age`, `bmi` 23.1, `bmi_category` "Normal". Clearing height returns `bmi: null` **and** `bmi_category: null`, so derived fields can't go stale behind their inputs. |
| **Logout** | ✅ Works | `POST /api/logout` → `200`, then `GET /api/me` → `401`. |
| **Protected routes reject** | ✅ Works | Signed out, all of `/api/me`, `/api/today-workout`, `/api/workout-history`, `/api/log-workout`, `/api/today-sets`, and all four `/api/stats/*` plus `/api/personal-records` return `401 unauthorized`. |

**The caveat that matters:** every one of these was driven through Flask's test
client, not a browser. The API contract is proven. What is *not* proven is that
the HTML forms post the right shapes to it, because no form has ever been
submitted by a human.

---

## 2. Half-finished work

### Endpoints the frontend calls that don't exist

**None.** All 27 distinct `window.api.*` call sites resolve to a registered
route (method and path both).

### Functions referenced but never defined

**None.** Every `window.ui.*`, `window.api.*` and `window.charts.*` member called
from a page script exists in the corresponding module.

> My first cross-reference reported seven missing `api.*` members. That was a bug
> in the checker — `api.js:152` assigns `window.api = api` from a named const, and
> the regex only matched inline object literals. Verified directly at
> `api.js:103–153`: all of `get`, `post`, `patch`, `del`, `session`,
> `requireSession`, `clearSession` are present.

### Element IDs referenced by JS but missing from HTML

**None**, across all nine pages — 90 `getElementById` targets checked.

### CSS classes applied but never defined

**None.**

### Dead code and files

| Item | Size | Note |
|---|---|---|
| `assets/DB.png` | **351 KB** | Unreferenced since Phase 6 replaced the steps section. Pure dead weight. |
| `.container--narrow` | — | Defined, never applied |
| `.grid--stats` | — | Defined, never applied |
| `.section--tight` | — | Orphaned when the dashboard was restructured in 11a |
| `.session-skeleton` | — | Orphaned when `ui.renderSkeleton` replaced it in 11c |
| `.stack--sm` | — | Defined, never applied |
| `Frontend/__pycache__/` | — | Build artefact, gitignored but present on disk |

The twelve `assets/muscles/*.png` appear unreferenced to a source scan but are
**live** — `muscle_groups.image_path` points at them from the database.

### Built but never wired

| Item | State |
|---|---|
| `GET /api/stats/volume` | Implemented, EXPLAIN-verified, smoke-tested for all three periods — **no UI consumes it.** History derives its own chart from session totals. |
| `weight_logs` … | in use since 11b |
| `personal_records` | in use, **but empty for pre-existing history** — the backfill in `queries/scratch.sql` was explicitly declined, so PRs only reflect sets logged since Phase 11a |
| `404.html` / `500.html` | Styled, unreachable. Live Server has no custom-error support, and the API answers JSON on every error, so nothing can produce a 500 HTML page in this architecture. |

### TODO / FIXME / HACK comments

**Zero.** Two `ponytail:` markers exist, both in dev tooling
(`check_frontend.py:242`, `check_stats.js:15`), both documenting a deliberate
simplification with its ceiling. Neither is in application code.

---

## 3. Security

### SECRET_KEY loaded from the environment with no fallback

✅ **Yes.** `config.py:43` — `SECRET_KEY = _required("SECRET_KEY")`.
`_required` (`config.py:23`) raises `ConfigError` on missing *or blank*, so the
app refuses to start rather than booting with a guessable key. Same for
`DB_PASSWORD` at `config.py:44`. Consumed once at `app.py:27`.

Asserted by `check_config.py:46–48`, including the whitespace-only case.

### .env gitignored, no secret in a tracked file

✅ **Yes.** `.gitignore:16` is `.env`. Confirmed against `.git/index`: no `.env`
is tracked.

The only secret-shaped strings in tracked files are in `docs/AUDIT.md:96` and
`:579`, which quote the *old* hardcoded `"ezgrind_secret_key"` while documenting
that it was removed. That is documentation of a fixed defect, not a live secret.

⚠️ **`.env.example` is also untracked** — along with every migration, the seed,
all four docs, `run.ps1` and every check script. Nothing has been `git add`ed
since Phase 1. A fresh clone gets none of it.

### Every protected endpoint enforces the auth check

✅ **Yes.** All 17 protected routes carry `@login_required` (`auth.py:40`), which
calls `current_user_id()` (`auth.py:24`) and raises `ApiError(401)` when
`session["user_id"]` is absent.

**Public by design (9):** `GET /`, `/api/health`, `/api/muscles`,
`/api/equipment`, `/api/exercises`, `/api/exercises/<id>`, `POST /api/signup`,
`/api/login`, `/api/logout`.

`/api/exercises/<id>` is the deliberate hybrid: catalogue facts for anyone,
`history: null` unless signed in (`exercise_routes.py:44–60`, via
`auth.optional_user_id()` at `auth.py:31`).

### Every query touching user data filters on session["user_id"]

✅ **Yes.** Endpoint by endpoint:

| Endpoint | Scoping |
|---|---|
| `GET/PATCH/DELETE /api/me` | `user_repo` keyed on `user_id` from the session |
| `POST /api/me/password` | Password hash fetched and written by `user_id` |
| `POST /api/log-workout` | `workout_repo.log_set(user_id, …)`; upsert keyed `(user_id, workout_date)` |
| `GET /api/today-sets`, `/api/today-workout` | `JOIN workouts w … WHERE w.user_id = %s` |
| `DELETE /api/workout-sets/<id>` | Ownership **in the DELETE's own WHERE**, joined through `workouts` |
| `GET /api/workout-history` | `_session_filter` always emits `w.user_id = %s` as its first predicate |
| `GET /api/exercises/<id>/last-set` | `WHERE w.user_id = %s AND ws.exercise_id = %s` |
| `GET /api/exercises/<id>` (history half) | `workout_repo.exercise_stats(user_id, …)` |
| All four `/api/stats/*`, `/api/personal-records` | `stats_repo`, `user_id` first positional argument, always in the WHERE |
| All three `/api/weight-logs` | `weight_repo`, same pattern |

**Can another user's data be read by manipulating a parameter?**

**No — because there is no parameter to manipulate.** No endpoint accepts a user
id in a path, query string or body. Identity comes only from the session cookie.

Proven, not asserted: `smoke.py` issues
`GET /api/stats/summary?user_id=<other user>` and gets **the caller's** numbers
back. A second account queries every endpoint and sees its own zeros and empty
lists, never the first user's data.

Ownership failures return **404, never 403** — a 403 would confirm the id exists
and turn the endpoint into a way to enumerate other people's rows. `smoke.py`
verifies a second user deleting someone else's set gets 404 *and* that the set
survives.

### Every SQL statement parameterised

✅ **Yes.** Every value reaches MySQL as a `%s` placeholder.

Eight statements build SQL with f-strings. Each interpolates **only whitelisted
fragments**, never a request value:

| Location | Interpolated | Source |
|---|---|---|
| `exercise_repo.py:75,88` | `{_EXERCISE_FIELDS}` | Module constant |
| `exercise_repo.py:60` | `IN ({placeholders})` | `", ".join(["%s"] * n)` — placeholders, not values |
| `workout_repo.py:399,406` | `{joins}`, `{where}` | Fixed strings from `_session_filter` |
| `user_repo.py:57` | `{assignments}` | Built from `_UPDATABLE_COLUMNS` |
| `weight_repo.py:93,105` | `{clause}` | Fixed strings |
| `stats_repo.py:199` | `{selection}`, `{grouping}` | Chosen by a boolean |

`?q=` escapes LIKE wildcards, so searching `%` matches a literal `%` rather than
everything — asserted in `smoke.py`.

### User-supplied strings written into innerHTML

✅ **No — there is zero `innerHTML` in the codebase.**

The brief states "exercise names and full names both flow into the DOM." They do,
but via `textContent` and `createElement`. That was true when the original audit
was written and was eliminated across Phases 4–11. A grep for `innerHTML` across
all of `Frontend/` returns nothing.

### Debug mode off by default

✅ **Yes.** `config.py:49–51` — `FLASK_ENV` defaults to **`production`**, so
`IS_PRODUCTION` is True and `DEBUG` is False unless something explicitly declares
development. `app.py:58` passes `config.DEBUG` to `app.run`.

`.env.example` ships `FLASK_ENV=development`, so a developer following the README
gets debug on; an environment that forgets to declare itself gets it off.
Asserted at `check_config.py:53`.

---

## 4. What would break or embarrass you

### 1. Nobody has ever seen this application render — **critical**

Every visual decision across twelve phases is unverified: the split auth layout,
the muscle grid, the steppers, the streak dots and gold pulse, the SVG charts,
skeletons, toasts, the offline banner, the mobile pass at 360px, and every
contrast fix.

The structural checks prove IDs resolve, classes exist and stylesheets load in
order. They cannot prove anything is legible, aligned, or the right size. A
CSS mistake that makes a page unusable would pass every check in the repository.

**This is the single largest risk and the cheapest to retire:** thirty minutes
with the app open.

### 2. No HTTPS, and the cookie configuration assumes it — **critical**

`config.py:79–80` sets `SameSite=None; Secure` in production. Browsers **discard**
a `Secure` cookie over plain HTTP. Deploy to `http://` and nobody can log in at
all — login will return 200 and the session will never persist.

Underneath that: passwords and session cookies would cross the wire in cleartext.

### 3. No CSRF protection on a cross-site cookie — **critical**

`SameSite=Lax` is what protects development. Production runs `SameSite=None`,
which switches that protection **off** by design, and nothing replaces it. Every
state-changing endpoint — log a set, change password, delete account — becomes
forgeable from any origin the user visits while signed in.

### 4. Account recovery does not exist — **high**

No password reset, no email verification. A forgotten password is a permanently
lost account with no support path, and anyone can register any address without
proving they own it. On a hosted app this generates support load immediately.

### 5. Personal records are empty for all existing history — **medium, visible**

`personal_records` is only written by `log_set`, and the backfill was declined.
Every set logged before Phase 11a is invisible to the feature: a user with months
of history opens the dashboard and sees "No records yet."

The fix is one statement already written and sitting in
`Database/queries/scratch.sql`.

---

## Also worth knowing

- **Nothing is committed.** No `git add` since Phase 1. Migrations, seeds, docs,
  `.env.example`, `run.ps1` and all four check scripts are untracked, and
  `EzGrind/Backend/bin` (a committed virtualenv) is still in the index.
- **`DB.png` is 351 KB of dead weight**; `step2.png` and `step3.png` carry 1.8
  bytes per pixel against `step1.png`'s 0.59 — roughly 1 MB recoverable across
  the landing page.
- **Streaks use the server's `CURDATE()`.** Correct for one user in one timezone;
  wrong the moment there are two.
- **Sessions can't be revoked.** Flask's signed cookie is stateless — logout
  clears the client only. A stolen cookie is valid for its full seven days.
- **Rate limiting is in-memory and per-process.** It resets on restart and won't
  hold across more than one worker.
- **`smoke.py --write` has been leaving test accounts behind** in earlier runs;
  it self-cleans now, but the database has accumulated `smoke+*@ezgrind.test`
  users from before that.
