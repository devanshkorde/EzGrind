# EzGrind — Codebase Audit

Audit date: 2026-07-28
Scope read in full: `EzGrind/Backend/app.py`, `EzGrind/Backend/requirements.txt`,
`EzGrind/Database/EzGrindDB.sql`, every file under `EzGrind/Frontend`
(7 HTML, 2 CSS, 6 JS), `README.md`.
`EzGrind/Backend/bin` exists and holds 11 files — an msys2-layout virtualenv's
launcher stubs (`python.exe`, `pip.exe`, `flask.exe`, `activate`, `Activate.ps1`
and duplicates), all of them tracked in git. There is no `lib/` and no
`pyvenv.cfg`, so that virtualenv has no site-packages and cannot run anything.
No source was skipped: the backend was a single 323-line module.

> **Amended 2026-07-28, after Phase 1.** Three factual corrections are marked
> **[CORRECTED]** below (B2, D8, V1), each with what was actually observed.
> Phase 1 restructured the backend, so **every `Backend/app.py:NNN` citation in
> this document refers to the pre-Phase-1 file** (recoverable from git history).
> Citations to the frontend, CSS and SQL are unaffected. Findings are otherwise
> left as written — this is an audit record, not a live tracker.
>
> **Resolution status added 2026-07-31, after Phase 12.** See the table below.

---

## Resolution status

Every finding above, and where it was fixed. The original text is left untouched
so the before/after stays legible.

### P0 — blocked core use

| ID | Finding | Status | Where |
|---|---|---|---|
| B1 | Login never redirected (`if (data.user)` against a response with no `user`) | **Fixed** | Phase 2 — `/api/login` returns the user; `login.js` keys on `res.ok` |
| B2 | Repo can't reproduce a working database (no seed) | **Fixed** | Phase 3 — `seeds/muscle_groups_and_exercises.sql`, 12 muscles + 48 exercises |
| B3 | `showAuthModal` called out of scope → ReferenceError | **Fixed** | Phase 6 — `dashboard.js` rewritten; the modal is gone entirely |
| B4 | `openProfile()` undefined; `<a>` nested in `<button>` | **Fixed** | Phase 4 — nav injected by `shell.js`, markup valid |

### P1 — visible

| ID | Finding | Status | Where |
|---|---|---|---|
| B5 | Exercise dropdown populated twice, then wiped | **Fixed** | Phase 7 — the unconditional prefetch deleted |
| B6 | `exercises.js` read fields the API never returned | **Fixed** | Phase 4 — `/api/exercises` joins `muscle_groups` |
| B7 | Blank date of birth → 500 | **Fixed** | Phase 1 — `optional()` normalises `""` to `NULL` |
| B8 | Decimal height/weight rejected against a `FLOAT` column | **Open** | Deliberate: `validate_positive_number` is still integer-only |
| B9 | Blank time-under-tension → 500 | **Fixed** | Phase 1, then the field was removed in Phase 4.5 |
| B10 | Profile showed `undefined` / `NaN` when signed out | **Fixed** | Phase 4 — `api.requireSession()` |
| B11 | History blank when signed out | **Fixed** | Phase 4 — same guard |
| B12 | Black text on a near-black gradient | **Fixed** | Phase 4 — `--text-muted`, verified 7.1:1 in Phase 12 |
| B13 | Three pages linked a stylesheet that didn't exist | **Fixed** | Phase 4 — five stylesheets, order enforced by `check_frontend.py` |
| B14 | One `.catch()` in the whole frontend | **Fixed** | Phase 4 → 11c — all errors flow through `api.js`; `unhandledrejection` catches the rest |
| B15 | Exercise library unreachable | **Fixed** | Phase 4 — linked from the shared nav |
| B16 | `GROUP BY exercise_name` merged distinct exercises | **Fixed** | Phase 3 — `UNIQUE (exercise_name, muscle_id)` |

### P2

| ID | Finding | Status |
|---|---|---|
| B17 | Dead `user_id: 1` in the payload | **Fixed** — Phase 7 |
| B18 | Client required a field the server and markup called optional | **Fixed** — Phase 5 |
| B19 | Validation duplicated in two languages, drifting | **Mitigated** — Phase 5: identical copy both sides, server authoritative, mirroring documented |
| B20 | Redirect keyed on an emoji display string | **Fixed** — Phase 5, keys on status |
| B21 | Duplicate CSS rules within one file | **Fixed** — Phase 4 rewrite |
| B22 | `.history-card` meant two different things | **Fixed** — Phase 4 |

### UI

| ID | Finding | Status |
|---|---|---|
| U1–U3 | Broken links, `<link>` in `<body>`, malformed documents | **Fixed** — Phase 4, enforced by `check_frontend.py` |
| U4 | No viewport meta on any page | **Fixed** — Phase 4 |
| U5 | Desktop-only below 768px | **Fixed** — Phase 4, audited to 360px in Phase 10.5 |
| U6 | Two conflicting global themes | **Fixed** — Phase 4, one token file |
| U7 | Hardcoded hex everywhere (three golds, six blacks) | **Fixed** — Phase 4; `check_frontend.py` fails on any hex outside `tokens.css` |
| U8 | No loading or error states | **Fixed** — Phase 11c |
| U9 | Labels, focus rings, modal semantics, contrast | **Fixed** — Phases 4, 5, 9, 10.5, 12 |
| U10 | No favicon | **Fixed** — Phase 4 |
| U11 | No shared navigation | **Fixed** — Phase 4, `shell.js` |

### Backend

| ID | Finding | Status |
|---|---|---|
| R1 | No error handling; HTML tracebacks to the client | **Fixed** — Phase 1 |
| R2 | Connection leak on the duplicate-email path | **Fixed** — Phase 1, context managers |
| R3 | Unguarded `data["key"]` access | **Fixed** — Phase 1 |
| R4 | No validation on the write path | **Fixed** — Phases 1, 7 |
| R5 | Auth check copy-pasted with two messages | **Fixed** — Phase 2, `@login_required` |
| R6 | New connection per request | **Fixed** — Phase 2, pooled |
| R7 | Four inconsistent response shapes | **Fixed** — Phase 2, one envelope |
| R8 | Emoji as protocol | **Mitigated** — messages are display-only; nothing keys on them |
| R9 | Nine routes in one 323-line module | **Fixed** — Phase 2, six blueprints |
| R10 | `/` not under `/api` | **Open** — deliberate, it's the liveness banner |
| R11 | Find-or-create not atomic | **Fixed** — Phase 3, upsert on a unique key |
| R12 | Unpinned dependencies | **Fixed** — Phase 1 |

### Database

| ID | Finding | Status |
|---|---|---|
| D1 | Schema file was a scratchpad | **Fixed** — Phase 3, four numbered migrations |
| D2 | No unique constraint on one-workout-per-day | **Fixed** — Phase 3 |
| D3 | Missing index on the hot path | **Fixed** — Phase 3; `Backward index scan` confirmed |
| D4 | No `ON DELETE` rules | **Fixed** — Phase 3, cascades where a child is meaningless alone |
| D5 | No uniqueness on reference data | **Fixed** — Phase 3 |
| D6 | `weight`/`reps` nullable | **Partly** — still nullable (bodyweight sets); `CHECK (reps > 0)` added |
| D7 | No set ordering | **Fixed** — Phase 3, `set_order` backfilled |
| D8 | Unused columns and assets | **Partly** — `description` now used; `DB.png` now unreferenced and should be deleted |
| D9 | Type drift between schema and code | **Open** — same as B8 |
| D10 | No engine/charset specified | **Was a non-issue** — server defaulted to InnoDB/utf8mb4; now explicit |
| D11 | Nothing modelled what the dashboard advertised | **Fixed** — Phase 11a/b |

### Security

| ID | Finding | Status |
|---|---|---|
| S1 | Credentials hardcoded in source | **Fixed** — Phase 1, `.env`, gitignored, verified untracked |
| S2 | Session secret `"ezgrind_secret_key"` | **Fixed** — Phase 1, required from env, no fallback |
| S3 | `SameSite=None` with `Secure=False` | **Fixed** — Phase 1, driven off `FLASK_ENV`; illegal pair unreachable |
| S4 | CORS wildcard with credentials | **Fixed** — Phase 1, allow-list, verified rejecting unknown origins |
| S5 | No CSRF protection | **Partly** — `SameSite=Lax` covers development; production needs tokens |
| S6 | No rate limiting | **Fixed** — Phase 1, 10/min on login, signup, password change, deletion |
| S7 | `debug=True` in the entrypoint | **Fixed** — Phase 1, defaults to `False` |
| S8 | Password policy length-only | **Open** — still 6 characters minimum |
| S10 | `innerHTML` as a stored-XSS sink | **Fixed** — zero `innerHTML` in the codebase |
| S11 | No transport security | **Open** — HTTPS is a deployment concern |
| S12 | *(Verified good)* No SQL injection, no IDOR | **Still true** — re-verified Phase 12 |

### Performance

| ID | Finding | Status |
|---|---|---|
| P1 | `/api/me` fetched three times per dashboard load | **Fixed** — Phase 6, cached in `api.js` |
| P2 | Log-workout fetched the whole catalogue unnecessarily | **Fixed** — Phase 7 |
| P3 | Unindexed date filtering | **Fixed** — Phase 3 |
| P4 | Unbounded history query | **Fixed** — Phase 8, paginated |
| P5 | Connection per request | **Fixed** — Phase 2 |
| P6 | 1.4 MB of unoptimised PNG on the landing page | **Open** — re-export targets in the Phase 12 report; binaries untouched |
| P7 | Assets shipped and never requested | **Partly** — muscle PNGs are now used; `DB.png` (351 KB) is now the dead one |
| P8 | Render-blocking font request | **Fixed** — Phase 4, system stack, zero webfont requests |
| P9 | Layout thrash from repeated style writes | **Fixed** — Phases 6, 12 |

### Open questions

| ID | Question | Answer |
|---|---|---|
| Q1/Q3 | How is the frontend served? | Live Server on `127.0.0.1:5500`; same-host requirement documented |
| Q2 | Should Flask serve the frontend? | No — kept separate |
| Q4 | Does `exercises.html` ship? | Yes — API joined the muscle data (Phase 9) |
| Q5 | Is the "muscle balance" copy aspirational? | Built for real in Phase 11a |
| Q6 | Are the body fields optional? | Optional in the schema and API; the signup form asks for them |
| Q7 | One workout row per user per day? | Yes — enforced by a unique constraint since Phase 3 |

Every claim below cites `file:line`. Claims that depend on runtime behaviour
(browser cookie policy, MySQL strict mode, library internals) are quarantined in
§11 "Unverified — needs a running instance" and are **not** asserted as fact
elsewhere.

---

## 1. Existing Architecture

### 1.1 Physical layout

```
EzGrind/
  Backend/app.py            323 lines — the entire server
  Backend/requirements.txt  4 unpinned deps
  Database/EzGrindDB.sql    DDL + ad-hoc SELECTs, one file
  Frontend/*.html           7 pages, no templating, no build step
  Frontend/css/style.css    419 lines — dashboard + shared widgets
  Frontend/css/theme.css     86 lines — dark shell, forms, profile
  Frontend/js/*.js          6 scripts, one per page, no modules
  Frontend/assets/          22 PNGs, ~2.7 MB total
```

There is no server-side templating and no route in Flask that serves HTML —
`app.py:29-31` serves a JSON banner at `/` and nothing else. The frontend is
therefore opened from disk or from a separate static server, while the API lives
on `http://127.0.0.1:5000`. Every frontend call hardcodes that absolute origin:
`dashboard.js:4`, `dashboard.js:35`, `dashboard.js:98`, `dashboard.js:116`,
`dashboard.js:150`, `signup.js:59`, `logWorkout.js:4`, `logWorkout.js:27`,
`logWorkout.js:48`, `logWorkout.js:71`, `profile.js:1`, `profile.js:29`,
`history.js:1`, `exercises.js:1`, `login.html:26`. That means **the frontend and
backend are always cross-origin in practice**, which is why CORS and cookie
config dominate the failure modes in §7.

### 1.2 Request flow

1. Browser loads a static `.html` from disk/static host.
2. The page's single `<script src="js/*.js">` runs at parse time (all scripts sit
   at the end of `<body>` except `history.html:17` and `signup.html:35`, which
   also sit after their markup).
3. The script issues bare `fetch()` calls to `http://127.0.0.1:5000/api/...`
   with `credentials: "include"` where auth is needed
   (`dashboard.js:5`, `profile.js:2`, `history.js:2`, `logWorkout.js:73`,
   `login.html:29`).
4. Flask matches a route in `app.py`, opens a **new** MySQL connection
   (`app.py:20-26`), runs one or two queries, closes cursor and connection, and
   returns `jsonify(...)`.
5. The script writes the result straight into the DOM. No page has a loading
   state, an error state, or a retry.

### 1.3 File responsibilities

| File | Responsibility | Notes |
|---|---|---|
| `app.py:37-48` | `GET /api/muscles` | Public, returns `image_path` nothing consumes |
| `app.py:54-80` | `GET /api/exercises` | Public, optional `?muscle_id=` filter |
| `app.py:86-127` | `POST /api/log-workout` | Session-gated; find-or-create today's workout, insert set |
| `app.py:133-198` | `POST /api/signup` | Validates, hashes, inserts user |
| `app.py:204-229` | `POST /api/login` | Verifies hash, populates session |
| `app.py:235-238` | `POST /api/logout` | `session.clear()` |
| `app.py:244-263` | `GET /api/me` | Session-gated profile read |
| `app.py:269-291` | `GET /api/today-workout` | Session-gated, grouped by exercise name |
| `app.py:297-319` | `GET /api/workout-history` | Session-gated, flat set list |
| `index.html` | Dashboard/landing, auth modal | Only page with a nav bar that links anywhere |
| `login.html` | Login form **and inline login script** (`login.html:22-45`) | The only page with inline JS |
| `signup.html` + `signup.js` | Registration | Client-side validation duplicated from `app.py:148-173` |
| `profile.html` + `profile.js` | Read-only profile + logout | |
| `log-workout.html` + `logWorkout.js` | Muscle → exercise → set entry | |
| `history.html` + `history.js` | Flat workout history | |
| `exercises.html` + `exercises.js` | Exercise library | **Unreachable — no page links to `exercises.html`** (grep across `EzGrind/` returns no `href` to it) |
| `css/style.css` | Dashboard chrome, cards, forms, modal | Loaded by `index.html:7`, `signup.html:6`, `history.html:6` |
| `css/theme.css` | Dark page shell, auth inputs, profile rows | Loaded by `login.html:8`, `profile.html:16`, `log-workout.html:16` |

### 1.4 How sessions actually work today

- Flask's default client-side signed-cookie session. Secret is the literal string
  `"ezgrind_secret_key"` (`app.py:10`).
- On successful login, `app.py:226-227` puts `user_id` and `full_name` into the
  session. Nothing else ever writes to the session.
- Every protected route does the same inline check —
  `if "user_id" not in session` at `app.py:88`, `app.py:246`, `app.py:271`,
  `app.py:299` — and returns 401. There is no decorator; the check is copy-pasted
  four times with two different message strings (`"Unauthorized"` at `app.py:89`
  and `app.py:300`, `"Not logged in"` at `app.py:247` and `app.py:272`).
- Cookie flags: `SESSION_COOKIE_SAMESITE = 'None'` and
  `SESSION_COOKIE_SECURE = False` (`app.py:13-14`). `HTTPONLY` is left at Flask's
  default (`True`). There is no `PERMANENT_SESSION_LIFETIME`, so the cookie is a
  browser-session cookie.
- **Authorisation is correct where it exists**: every user-scoped query filters on
  the session's `user_id` and never on a client-supplied id — `app.py:103`,
  `app.py:112`, `app.py:256`, `app.py:282`, `app.py:312`. `logWorkout.js:64` sends
  a `user_id: 1` field, and the backend ignores it (`app.py:91` reads the session
  instead). There is no IDOR in the current route set.

---

## 2. Existing Features

Status legend — WORKING: verified end to end by reading every hop.
PARTIALLY WORKING: the happy path completes but a visible part of it does not.
BROKEN: the feature cannot complete as written.

| # | Feature | Status | Evidence |
|---|---|---|---|
| 1 | **Signup** | PARTIALLY WORKING | Form `signup.html:12-33` → `signup.js:59-81` → `app.py:133-198`. Insert and hash are correct (`app.py:175`, `app.py:184-192`). Breaks on a blank date of birth (§3 B7) and rejects decimal height/weight (§3 B8). Redirect at `signup.js:78` compares against the emoji literal `"Signup successful 🎉"`, coupling navigation to a display string (`app.py:198`). |
| 2 | **Login (credential check + session)** | PARTIALLY WORKING | `login.html:26-34` → `app.py:204-229`. Hash comparison at `app.py:223` and session write at `app.py:226-227` are correct. |
| 3 | **Login (redirect to dashboard)** | BROKEN | `login.html:39` gates the redirect on `data.user`, but `app.py:229` returns `{"message": "Login successful"}` with **no `user` key**. The condition is never true; the user stays on the login page seeing only the status text from `login.html:37`. |
| 4 | **Logout** | WORKING | `profile.js:28-37` → `app.py:235-238`. `session.clear()` then redirect to `login.html`. Reachable only from the profile page — no logout control exists on `index.html`. |
| 5 | **Dashboard greeting** | WORKING | `dashboard.js:4-32` → `app.py:244-263`. Both the 401 branch (`dashboard.js:8-15`) and the success branch (`dashboard.js:21-24`) are handled. |
| 6 | **Dashboard "Today's Workout" list** | WORKING | `dashboard.js:35-76` → `app.py:269-291`. Empty state at `dashboard.js:53-69` is the only empty state anywhere in the app. |
| 7 | **Logged-in vs logged-out hero CTA** | PARTIALLY WORKING | `dashboard.js:150-163` swaps `startTodayBtn`/`letsGrindBtn` (`index.html:46`, `index.html:48`). Works, but costs a third redundant `/api/me` call and the button carries two conflicting click handlers (§3 B3). |
| 8 | **Auth modal for logged-out users** | PARTIALLY WORKING | Modal markup `index.html:134-147`, styles `style.css:325-342`, shown by `dashboard.js:88-92` via the listener at `dashboard.js:96-109`. It does open, but a second listener on the same button throws first (§3 B3). The modal has no close button and no backdrop-click handler — once open it can only be escaped by navigating. |
| 9 | **Muscle dropdown** | WORKING | `logWorkout.js:4-15` → `app.py:37-48`. |
| 10 | **Exercise dropdown filtered by muscle** | PARTIALLY WORKING | `logWorkout.js:18-42` → `app.py:54-73`. Correct on `change`, but a second unconditional fetch at `logWorkout.js:48-57` pre-fills the same `<select>` with the entire exercise table (§3 B5). |
| 11 | **Log a set** | PARTIALLY WORKING | `logWorkout.js:60-82` → `app.py:86-127`. Find-or-create-workout (`app.py:102-115`) plus set insert (`app.py:117-121`) is correct. Fails when "Time Under Tension" is left blank (§3 B9) and has no 401 handling. |
| 12 | **Workout history** | PARTIALLY WORKING | `history.js:1-30` → `app.py:297-319`. Renders when logged in; blank-screen TypeError when not (§3 B11). |
| 13 | **Profile page** | PARTIALLY WORKING | `profile.js:1-24` → `app.py:244-263`. Renders when logged in; renders `undefined` / `NaN` when not (§3 B10). Page is also unstyled (§4 U1). |
| 14 | **Exercise library page** | BROKEN | `exercises.html` is linked from nowhere in the repo, and `exercises.js:20-23` reads `ex.image_path` and `ex.muscle_name`, neither of which `app.py:63` or `app.py:70` selects. |
| 15 | **Password hashing** | WORKING | `app.py:175` (`generate_password_hash`) and `app.py:223` (`check_password_hash`). |
| 16 | **Duplicate-email rejection** | WORKING (leaks a connection) | `app.py:180-182`. Correct behaviour, but see §5 R2. |

Features the README claims that have no implementation: "track fitness progress
through a … dashboard" — there is no progress/statistics endpoint in `app.py` and
no chart in any page; and "muscle balance" (`index.html:42`, `index.html:104`) has
no backing query.

---

## 3. Existing Bugs

### P0 — blocks core use

**B1 — Login never navigates to the dashboard.**
`login.html:39` — `if (data.user)`. The server response is
`{"message": "Login successful"}` (`app.py:229`); there is no `user` field, so the
redirect at `login.html:41` is dead code.
*User sees:* enters correct credentials, the word "Login successful" appears under
the form, and the page never moves. The session cookie may well have been set, but
nothing tells the user that, and there is no link off `login.html` to anywhere.

**B2 — The repository cannot reproduce a working database. [CORRECTED]**
`EzGrindDB.sql` contains DDL only — there is not a single `INSERT` in the file
(lines 1-79 are `CREATE TABLE` ×5, `ALTER TABLE` ×2, and seven ad-hoc `SELECT`/
`SHOW`/`DESCRIBE` statements). `muscle_groups` and `exercises` are reference data
with no seed.

*Correction:* this was originally written as "a fresh database produces an app
with no exercises", implying the app is dead everywhere. It is not. The
developer's local MySQL **is** populated — `GET /api/muscles` returns real rows
(`{"muscle_id": 1, "muscle_name": "Chest", "image_path": "assets/muscles/chest.png"}`),
verified 2026-07-28 via `Backend/smoke.py`. The seed data exists; it just exists
only in one person's database and in no committed file.

*Who this breaks:* anyone cloning the repo, and the developer themselves the day
the database is lost or rebuilt. They get empty muscle (`logWorkout.js:9`) and
exercise dropdowns, so no workout can be logged, so history and today's-workout
stay permanently empty — every feature downstream of exercise selection is dead.
Still P0, because the working state is unrecoverable from the repository, but the
severity is *reproducibility*, not *the app does not run*.

**B3 — `showAuthModal` is called out of scope.**
`dashboard.js:168` calls `showAuthModal()`, but that function is declared inside
the `DOMContentLoaded` callback at `dashboard.js:88-92` and is not visible at
module scope.
*User sees:* clicking "START TODAY" logs `Uncaught ReferenceError: showAuthModal
is not defined`. Because `dashboard.js:96-109` registers a *second* handler on the
same button that resolves the modal correctly, the modal still opens — so this is
a P0-shaped defect that currently degrades to a console error plus a wasted
`/api/me` round-trip. It becomes user-visible the moment either handler is
touched.

**B4 — `openProfile()` does not exist.**
`index.html:21` — `onclick="openProfile()"`. Grep across `EzGrind/` finds the
identifier only at that one line; no definition anywhere.
*User sees:* clicking the avatar throws `ReferenceError: openProfile is not
defined`. Navigation still happens only because an `<a href="profile.html">` is
nested inside the `<button>` (`index.html:22-24`) — invalid markup doing the
actual work. `dashboard.js:84` looks for `document.getElementById("profileBtn")`,
an id that appears nowhere in `index.html`, so the intended handler block at
`dashboard.js:113-128` is dead code.

### P1 — visible

**B5 — Exercise dropdown is populated twice with different data.**
`logWorkout.js:48-57` fetches *all* exercises and appends them to
`exerciseSelect` on page load, while `logWorkout.js:27-40` replaces the same
select's contents when a muscle is chosen.
*User sees:* on load, the "Exercise" dropdown already lists every exercise in the
database even though "Select Muscle" is showing; choosing a muscle wipes it and
replaces it with the filtered list; choosing the blank muscle option
(`logWorkout.js:22-25`) empties it entirely with no placeholder.

**B6 — `exercises.js` renders fields the API does not return.**
`exercises.js:20-23` reads `ex.image_path`, `ex.muscle_name`. `app.py:63` and
`app.py:70` select only `exercise_id, exercise_name, equipment`.
*User sees:* every card shows a broken-image icon (`<img src="undefined">`) and
the literal text `undefined` where the muscle name should be. (Only reachable by
typing the URL — see B15.)

**B7 — Blank date of birth is sent as an empty string to a `DATE` column.**
`signup.html:17` (`<input type="date" id="dob">`, not `required`) →
`signup.js:7` (`.value` is `""` when unset) → `signup.js:70` sends
`date_of_birth: ""` → `app.py:142` passes it through unvalidated → `app.py:184-192`
inserts `""` into `users.date_of_birth DATE` (`EzGrindDB.sql:55`).
*User sees:* signup fails with a raw Werkzeug HTML traceback (debug is on,
`app.py:323`) instead of a JSON error, or a silent 500 with no message. See §11
for the strict-mode caveat.

**B8 — Decimal height or weight is rejected.**
`app.py:161-164` and `app.py:167-170` call `int(...)` on the submitted value.
`int("175.5")` raises `ValueError`, caught by the bare `except`, returning
`{"message": "Height must be number"}` 400. The column was widened to `FLOAT`
specifically to hold decimals (`EzGrindDB.sql:63-65`), so the backend contradicts
the schema. `signup.html:18-19` uses `<input type="number">` with no `step`, which
defaults to integers-only in the spinner but still permits typed decimals.
*User sees:* "Height must be number" after entering `175.5`, which is a number.

**B9 — Blank "Time Under Tension" is sent as `""`.**
`log-workout.html:34` (`<input type="number" id="tut">`, optional) →
`logWorkout.js:68` sends `""` → `app.py:97` `data.get(...)` returns `""` →
`app.py:117-121` inserts `""` into `workout_sets.time_under_tension INT`
(`EzGrindDB.sql:41`).
*User sees:* leaving the optional field blank fails the whole set insert. See §11.

**B10 — Profile page shows `undefined` and `NaN` when logged out.**
`profile.js:1-4` never inspects `res.status`. On a 401 (`app.py:246-247`) the body
is `{"message": "Not logged in"}`, so `profile.js:7` writes `undefined` into
`#name`, `profile.js:11` builds `new Date(undefined)` → Invalid Date, and
`profile.js:20` writes `NaN` into the Age row. Height/weight render as
`"undefined cm"` / `"undefined kg"` (`profile.js:21-22`).
*User sees:* a fully-rendered profile page full of `undefined` and `NaN` instead
of a redirect to login.

**B11 — History page goes blank when logged out.**
`history.js:4` parses the 401 body (`app.py:300`) as if it were the array. `data`
is an object, so `data.length` is `undefined`, the empty-state branch at
`history.js:10` is skipped, and `history.js:15` throws
`data.forEach is not a function`.
*User sees:* the "Workout History" heading with nothing under it, forever, and no
indication that logging in would help.

**B12 — Unreadable body text in the "1-2-3" steps section.**
`style.css:201` sets `.step-text p { color: #000000; }` while `style.css:134` gives
`.steps` a `linear-gradient(135deg, #000000, #ac9825)` background.
*User sees:* the first step's paragraph is black on black — invisible; the third is
black on dark gold — barely legible. The headings above them are readable
(`style.css:191`), which makes it look like the copy failed to load.

**B13 — Three pages load a stylesheet that does not exist.**
`profile.html:7`, `log-workout.html:7`, `exercises.html:7` all use
`href="style.css"`. The file lives at `Frontend/css/style.css`.
*User sees:* 404 in the network tab. `profile.html` and `log-workout.html` are
partially rescued by a second, correctly-pathed `<link>` to `theme.css` placed
inside `<section>` (`profile.html:16`, `log-workout.html:16`), so they render
dark-but-wrong. `exercises.html` has no fallback link at all and renders as
unstyled black-on-white HTML.

**B14 — Nothing in the app handles a network failure.**
`.catch()` appears exactly once in the whole frontend, at `exercises.js:8`, and it
only writes to the console. The fifteen other `fetch` chains listed in §1.1 have
none.
*User sees:* if the Flask process is not running, every page silently does
nothing — the dashboard greeting stays empty (`index.html:35`), the dropdowns stay
empty, the login form appears to accept the submit and then nothing happens. There
is no message anywhere that says the server is unreachable.

**B15 — The exercise library is unreachable.**
No `href`, `window.location`, or link of any kind to `exercises.html` exists in
the repo (grep over `EzGrind/`).
*User sees:* the feature does not exist unless they guess the URL.

**B16 — `today-workout` merges distinct exercises that share a name.**
`app.py:283` groups by `e.exercise_name`, not `e.exercise_id`. Two rows in
`exercises` with the same name under different muscle groups (nothing prevents
this — see §6 D5) collapse into one line with a summed set count.
*User sees:* "Cable Fly – 6 sets" when they did 3 sets of two different cable flys.

### P2 — cosmetic / latent

**B17 — Dead `user_id` in the log-workout payload.**
`logWorkout.js:64` sends `user_id: 1` with the comment `// demo user`. `app.py:91`
ignores it. Harmless today; actively dangerous the day someone "fixes" the backend
to read it.

**B18 — Signup client-side rules contradict the markup and the server.**
`signup.js:29-32` hard-requires a 10-digit contact number, but `signup.html:16`
does not mark the field `required` and `app.py:157` treats it as optional.
*User sees:* an `alert("Contact number must be 10 digits.")` on a field that looks
optional.

**B19 — Validation is duplicated verbatim in two languages.**
`signup.js:14-56` and `app.py:148-173` implement the same six rules with different
messages and different thresholds (height `>300` client-side at `signup.js:35`,
unbounded server-side). They will drift.

**B20 — Redirect keyed on an emoji display string.**
`signup.js:78` compares against `"Signup successful 🎉"`; `app.py:198` produces it.
Changing the user-facing copy silently breaks the redirect.

**B21 — Duplicate CSS rules within one file.**
`style.css:85-90` and `style.css:181-186` both define `.highlight` with different
padding and radius; `style.css:378-385` and `style.css:405-412` both style
`input, select`; `style.css:388-392` and `style.css:414-418` are byte-identical
focus rules. Last-wins behaviour is accidental, not chosen.

**B22 — `.history-card` means two different things.**
`history.html:11` applies it to the outer container; `history.js:18` applies it to
each row inside that container. `style.css:355-364` styles both.

---

## 4. UI Problems

**U1 — Broken stylesheet links.** `profile.html:7`, `log-workout.html:7`,
`exercises.html:7` (see B13). `exercises.html` ends up with zero CSS.

**U2 — Stylesheets loaded from inside `<body>`.** `login.html:8`,
`profile.html:16`, `log-workout.html:16`. Browsers tolerate it; it causes a
flash of unstyled content and makes the cascade order depend on document order.

**U3 — Malformed documents.**
- `signup.html` has no `<body>` open tag — `</head>` at line 7 is followed
  directly by `<section>` at line 8, and a stray `</body>` appears at line 37.
- `index.html:21-25` nests `<a>` inside `<button>`; interactive content inside
  interactive content is invalid and is what actually performs the navigation
  (B4).
- `history.html:2`, `login.html:2`, `signup.html:2` open `<html>` with no `lang`.
- `login.html`, `signup.html`, `history.html` have no `<meta charset>`, yet all
  three render non-ASCII content (`signup.html:10` `💪`, `history.js:11` `💭`).

**U4 — No viewport meta on any page.** Not present in `index.html:3-12`,
`login.html:3-6`, `signup.html:3-7`, `profile.html:3-8`, `log-workout.html:3-8`,
`exercises.html:3-8`, `history.html:3-7`. The only responsive rule in the codebase
(`style.css:206-216`) therefore never fires on a real phone — the page is rendered
at desktop width and scaled down.

**U5 — Desktop-only layout below 768px.** Even with a viewport tag, only `.step`
is handled (`style.css:207-215`). Unhandled: `.navbar` (`style.css:11-18`, fixed
40px side padding and a 115px logo — `style.css:32-36`), `.hero`
(`style.css:59-66`, `space-between` flex row that never wraps), `.hero-text h1` at
a fixed `4rem` (`style.css:79`), `.cta-btn` at 25px (`style.css:104`),
`.theme-card` at `max-width: 600px` with 40px padding (`style.css:395-402`),
`theme.css:7` `padding: 60px 100px` on `<body>` — 200px of horizontal padding at
any width, which alone breaks 360px.

**U6 — Two conflicting global themes.** `style.css:1-4` sets `Archivo` on `*`;
`theme.css:8` sets `'Segoe UI'` on `body`. `style.css` never sets a `body`
background, `theme.css:9` does. Which font and background a page gets depends
entirely on which of the two files it happens to link — see the table in §1.3.
Pages that link only `style.css` (`signup.html:6`, `history.html:6`) get the
browser default white background.

**U7 — Hardcoded hex everywhere, no tokens.** The gold accent appears as `#ac9825`
(`style.css:12`, `:60`, `:134`, `:272`, `:336`), `#d4af37` (`style.css:284`,
`:309`, `:317`, `:390`, `theme.css:41`, `:52`, `:76`), and `#facc15`
(`theme.css:52`). Three different golds. Backgrounds range over `#000000`,
`#090909`, `#0f0f0f`, `#1a1a1a`, `#111`, `#0e0e0e`. No CSS custom property is
declared anywhere in either file.

**U8 — Missing states.** No loading indicator on any page. No error state on any
page. The only empty state in the app is `dashboard.js:53-61`; `history.js:11` has
a bare `<p>` with no styling; `exercises.html:17-19` and `log-workout.html:23`
have none at all.

**U9 — Accessibility gaps.**
- `log-workout.html:21,24,27,30,33` use `<label>` with no `for` and no wrapping,
  so none of the five labels is programmatically associated with its control.
- `login.html:13-14` and `signup.html:14-29` have no labels at all — placeholder
  text only, which disappears on focus and is not announced reliably.
- `index.html:21` is a `<button>` whose only content is an image with
  `alt="Profile"` — the accessible name is adequate but the control is invalid
  (U3) and has no `aria-label` fallback.
- `index.html:134` — the modal is a plain `<div>`: no `role="dialog"`, no
  `aria-modal`, no focus trap, no `Esc` handler, no close control, and the page
  behind it stays scrollable and focusable.
- Contrast: B12 (black on black). Also `.footer` `#777` on white
  (`style.css:222`) is ~4.4:1 at 13px — under AA for small text.
- `.highlight` (`style.css:85-90`) applies `padding: 8px 18px` to an inline
  element inside a `4rem`/`1.1` line-height heading (`style.css:79-81`), so its
  background box overlaps the line above.
- No `:focus-visible` styling on any button; `style.css:388` and `:414` set
  `outline: none` on inputs and replace it with a border+shadow, but buttons get
  nothing.

**U10 — No favicon** in any page, so every page load takes a 404 on
`/favicon.ico`.

**U11 — No shared navigation.** `profile.html:11-13`, `log-workout.html:11-13` and
`exercises.html:11-13` each hand-roll a `<nav class="navbar"><h2>EzGrind</h2></nav>`
containing no links. `history.html` and `signup.html` and `login.html` have no nav
at all. From any page except `index.html`, the only way back is the browser button.

---

## 5. Backend Problems

**R1 — No error handling of any kind.** `app.py` contains no `try/except` around
any database call and registers no `@app.errorhandler`. Any `mysql.connector`
error, any `KeyError`, any bad payload produces a Werkzeug 500 — and because
`app.py:323` runs `debug=True`, that 500 is an **HTML traceback page**, not JSON.
Every frontend `.then(res => res.json())` (§1.1) then throws a JSON parse error
inside a promise with no `.catch()` (B14), so the failure is invisible twice over.

**R2 — Connection leak on the duplicate-email path.** `app.py:180-182` returns 400
without reaching the `cursor.close()` / `conn.close()` at `app.py:195-196`. Every
attempt to register an already-registered email leaks one MySQL connection until
the process dies. There is no `try/finally` and no context manager anywhere in the
file — every one of the nine routes closes by falling off the end of the happy
path (`app.py:45-46`, `:77-78`, `:124-125`, `:195-196`, `:220-221`, `:260-261`,
`:288-289`, `:316-317`), so any future early return or exception leaks too.

**R3 — Unguarded dictionary access on request bodies.**
`app.py:94-96` (`data["exercise_id"]`, `data["weight"]`, `data["reps"]`),
`app.py:137-139` (`data["full_name"]`, `data["email"]`, `data["password"]`),
`app.py:208-209` (`data["email"]`, `data["password"]`). A missing key is a
`KeyError` → HTML 500. `request.json` itself (`app.py:92`, `:135`, `:206`) raises
415 for a wrong `Content-Type` and 400 for malformed JSON — both HTML.

**R4 — No validation on the write path that matters.** `/api/log-workout`
(`app.py:86-127`) validates nothing: `exercise_id` is not checked for existence or
type, `weight` and `reps` are not range-checked or even confirmed numeric, `tut`
is passed through raw (B9). Negative reps, 10⁶ kg, or an `exercise_id` belonging
to no row will all be attempted against the database. Compare with `/api/signup`
(`app.py:148-173`), which validates six fields — the codebase is internally
inconsistent about whether validation is the server's job.

**R5 — Auth check copy-pasted four times, two messages.** `app.py:88-89`,
`app.py:246-247`, `app.py:271-272`, `app.py:299-300`. Two of them say
`"Unauthorized"` and two say `"Not logged in"`, so a frontend cannot key off the
message. There is no `@login_required` decorator.

**R6 — Connection factory called per request with no pooling.**
`app.py:20-26` builds a fresh TCP connection, authenticates, and selects a
database on every single API call. `mysql.connector.pooling` is available in the
declared dependency (`requirements.txt:3`) and unused.

**R7 — Response shapes are inconsistent in four different ways.**
- Bare array: `app.py:48`, `:80`, `:291`, `:319`.
- Bare object: `app.py:263` — and it is `None` if the row is missing, so the body
  is the literal `null`.
- `{"message": "..."}` for success: `app.py:31`, `:127`, `:198`, `:229`, `:238`.
- `{"message": "..."}` for errors: `app.py:89`, `:149`, `:152`, `:155`, `:158`,
  `:164`, `:170`, `:173`, `:182`, `:224`, `:247`, `:272`, `:300`.

Success and failure are therefore indistinguishable by shape; the client must
inspect the status code, which `profile.js`, `history.js`, `logWorkout.js` and
`login.html` do not do (B10, B11). No response carries a machine-readable error
code.

**R8 — Success messages carry emoji as protocol.** `app.py:127` `💪`,
`app.py:198` `🎉`, `app.py:31` `🚀`. `signup.js:78` string-matches one of them
(B20).

**R9 — No route organisation.** Nine routes, four auth checks, one connection
factory and all business logic in a single 323-line module with comment-banner
"sections" (`app.py:34-36`, `:51-53`, `:83-85`, `:130-132`, `:201-203`, `:232-234`,
`:241-243`, `:266-268`, `:294-296`) standing in for blueprints.

**R10 — The `/` route is not under `/api`.** `app.py:29-31` returns JSON from the
site root, which is where a static index would have to live if the backend ever
serves the frontend.

**R11 — Find-or-create is not atomic.** `app.py:102-115` does `SELECT` then
`INSERT` on `workouts` with no transaction boundary and no unique constraint to
fall back on (§6 D2). Two concurrent set-logs from the same user on the same day
can create two workout rows.

**R12 — Unpinned dependencies.** `requirements.txt:1-4` names four packages with
no version specifiers. `werkzeug` is listed explicitly even though Flask pins it
transitively, so the two can be resolved to an incompatible pair.

---

## 6. Database Problems

**D1 — The file is not a migration, it is a scratchpad.** `EzGrindDB.sql` mixes
DDL (`:4-44`), exploratory `SELECT`/`SHOW`/`DESCRIBE` (`:47-50`, `:60`, `:67`,
`:70-78`), and two after-the-fact `ALTER`s (`:53-58`, `:63-65`) whose effects
should simply be in the `CREATE TABLE` above. `CREATE DATABASE ezgrind_db;` at
`:1` has no `IF NOT EXISTS`, so re-running the file errors on line 1. There is no
version tracking, no down path, and no numbered-file convention.

**D2 — No unique constraint on one-workout-per-user-per-day.** `workouts`
(`EzGrindDB.sql:27-33`) has no `UNIQUE (user_id, workout_date)`, which is exactly
the invariant `app.py:102-115` assumes and cannot enforce (R11).

**D3 — Missing indexes on the columns actually filtered.**
- `workouts.workout_date` is unindexed (`EzGrindDB.sql:30`) yet appears in the
  `WHERE` of `app.py:103` and `app.py:282` and the `ORDER BY` of `app.py:311`.
  The InnoDB FK on `user_id` (`:32`) gives a single-column index only, so both
  hot queries filter on an indexed `user_id` and then scan.
- `exercises.muscle_id` is covered by its FK index (`:24`), which is why
  `app.py:65` is fine.
- `workout_sets` has FK indexes on `workout_id` and `exercise_id` (`:42-43`);
  no additional index is needed at current scale.

**D4 — No `ON DELETE` / `ON UPDATE` on any foreign key.** `EzGrindDB.sql:24`,
`:32`, `:42`, `:43` all default to `RESTRICT`. Deleting a user is impossible
without manually cascading, and there is no account-deletion path in `app.py` at
all — which matters for a schema that stores date of birth, height, weight and
phone number (`:53-58`).

**D5 — No uniqueness or check constraints on reference data.**
`muscle_groups.muscle_name` (`:14`) and `exercises.exercise_name` (`:20`) are not
unique, which is what makes B16 possible. `users.fitness_goal VARCHAR(20)` (`:58`)
accepts any string; the four values the UI offers are enumerated only in
`signup.html:23-26`.

**D6 — Nullability contradicts the feature.** `workout_sets.weight` and
`workout_sets.reps` (`:39-40`) are nullable, but a set with no reps is not a set,
and `history.js:23` renders `null kg × null reps` for one. `app.py:117-121` never
supplies a default.

**D7 — No ordering or timestamp on sets.** `workout_sets` (`:35-44`) has no
`created_at` and no explicit set-order column, so `app.py:305-312` can only
`ORDER BY w.workout_date DESC` — sets within a day come back in whatever order the
storage engine returns, and "set 1 vs set 4" cannot be reconstructed. This is a
modelling gap against the app's core claim of "log your exercises, sets, reps"
(`index.html:88-89`).

**D8 — Columns that exist and are never used. [CORRECTED]**
`exercises.description TEXT` (`:23`) is selected by no query in `app.py`.
`muscle_groups.image_path` (`:15`) is selected at `app.py:42` and consumed by
nothing (`logWorkout.js:9-14` uses only `muscle_id` and `muscle_name`) — while
`exercises.js:20` tries to read an `image_path` that lives on the wrong table
entirely (B6).

*Correction:* this originally ended "the eleven PNGs in `Frontend/assets/muscles/`
are referenced from nowhere in the repo." Literally true but misleading. They are
referenced — by `muscle_groups.image_path` **data**, not by code:
`GET /api/muscles` returns `assets/muscles/chest.png` and siblings (verified
2026-07-28). So the images, the column, and the paths were all wired up
deliberately; the only missing piece is a frontend that renders them. That makes
the asset directory intended-but-unrendered rather than dead weight, and it is
evidence toward Q4.

**D9 — Type drift between schema and code.** `height_cm`/`weight_kg` are `FLOAT`
after `:63-65`, but `app.py:162` and `app.py:168` coerce to `int` (B8).
`contact_number VARCHAR(15)` (`:54`) vs a hard 10-digit regex at `app.py:157`.

**D10 — No engine, charset or collation specified** on any `CREATE TABLE`
(`:4`, `:12`, `:18`, `:27`, `:35`). The result depends on the server's defaults,
so `utf8mb4` for names is not guaranteed.

**D11 — Nothing models what the dashboard advertises.** "Muscle balance"
(`index.html:42`, `:104`) and "weekly training" (`index.html:104`) have no
supporting table, view, or aggregate; there is also no `user_body_metrics` history
to make "follow your progress" mean anything beyond a single mutable weight column
on `users`.

---

## 7. Security Problems

**S1 — Database credentials hardcoded in source.** `app.py:22-25` — host, user
`root`, password `1234`, database. Committed to git, and the account is the MySQL
superuser rather than a scoped application user.

**S2 — Session secret hardcoded and guessable.** `app.py:10` —
`"ezgrind_secret_key"`. Anyone with the repo can forge a signed session cookie for
any `user_id` and read or write any user's data. This is the single most severe
issue in the codebase, and it neutralises the otherwise-correct authorisation
described in §1.4.

**S3 — `SameSite=None` with `Secure=False`.** `app.py:13-14`. Setting
`SameSite=None` is an explicit declaration that the cookie should be sent on
cross-site requests, while `Secure=False` means it travels in cleartext. See §11
for what current browsers do with that combination — the outcome is either "the
session cookie is dropped entirely" or "the session cookie is attached to every
cross-site request", and both are bad in different ways.

**S4 — CORS allows every origin with credentials.** `app.py:17` —
`CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})`,
applied to `/*` rather than `/api/*`. Combined with cookie auth this is the
classic credentialed-wildcard configuration. See §11 for what flask-cors emits.

**S5 — No CSRF protection on any state-changing route.** `POST /api/log-workout`
(`app.py:86`), `POST /api/logout` (`app.py:235`), `POST /api/signup`
(`app.py:133`), `POST /api/login` (`app.py:204`) accept cookie-authenticated
requests with no token, no origin check, and no `SameSite=Lax` fallback (S3
explicitly opts out of the SameSite defence).

**S6 — No rate limiting anywhere.** `POST /api/login` (`app.py:204-229`) can be
called without limit; failures return a distinguishable 401 (`app.py:224`).
Signup (`app.py:133`) can be used to enumerate registered emails, since
`app.py:182` returns `"Email already exists"` — an unauthenticated oracle over the
user table.

**S7 — `debug=True` in the entrypoint.** `app.py:323`. If this is ever reachable
off-localhost it is remote code execution via the Werkzeug console, and it leaks
full stack traces and source context on every unhandled exception (R1). There is
no host/port/env gating.

**S8 — Password policy is length-only.** `app.py:154-155` requires ≥6 characters
and nothing else. No maximum length, so a multi-megabyte password will be hashed
with scrypt and can be used as a cheap DoS.

**S9 — Login response distinguishes nothing, but signup does.** `app.py:224`
correctly returns one generic `"Invalid credentials"` for both unknown-email and
wrong-password — good. `app.py:182` then gives the same information away for free
(S6).

**S10 — `innerHTML` with server data.** `history.js:20-25` interpolates
`item.workout_date`, `item.exercise_name`, `item.weight`, `item.reps` into
`innerHTML`; `exercises.js:19-24` does the same with `ex.exercise_name`,
`ex.equipment`, `ex.image_path`. Today those values come only from the
admin-seeded `exercises` table, so there is no live XSS. It is a stored-XSS sink
the moment any user-supplied string reaches those columns — for example a
custom-exercise feature. By contrast `dashboard.js:23` (`innerText`) and
`profile.js:7-23` (`textContent`) are safe, so the codebase is inconsistent rather
than uniformly wrong.

**S11 — No transport security assumptions documented.** Everything is `http://`
(all fifteen fetch call sites, §1.1), so session cookies, passwords
(`login.html:31-32`, `signup.js:67`) and personal data cross the wire in
cleartext.

**S12 — What is *not* broken, verified.** No SQL injection: every query uses
parameterised placeholders — `app.py:42`, `:62-67`, `:69-73`, `:102-105`,
`:111-114`, `:117-121`, `:180`, `:184-192`, `:214-217`, `:252-256`, `:277-284`,
`:305-312`. No IDOR: every user-scoped query derives the id from `session`, never
from the request (`app.py:91`, `:256`, `:282`, `:312`); the client-supplied
`user_id` at `logWorkout.js:64` is ignored. Passwords are hashed with Werkzeug's
default (scrypt) and never logged or returned — `app.py:215` selects
`password_hash` but `app.py:229` returns only a message, and `app.py:253` omits it
entirely.

---

## 8. Performance Problems

**P1 — The dashboard calls `/api/me` twice on load and a third time on click.**
`dashboard.js:4` and `dashboard.js:150` both fire at parse time; `dashboard.js:98`
fires again on "START TODAY" and `dashboard.js:116` on the (dead) profile handler.
Each is a full round-trip that opens its own MySQL connection (R6). Three of the
four exist only because the same answer — "is the user logged in?" — is never
cached.

**P2 — The log-workout page fetches the entire exercise table it does not need.**
`logWorkout.js:48` requests every exercise unfiltered, on top of the muscle list
at `logWorkout.js:4`, then throws the result away the moment a muscle is selected
(B5).

**P3 — Unindexed date filtering on the two hottest queries.** `app.py:103`
(`WHERE user_id=%s AND workout_date=CURDATE()`, run on every single set logged),
`app.py:282` (same predicate, run on every dashboard load) and `app.py:311`
(`ORDER BY w.workout_date DESC`) all rely on a composite index that does not exist
(D3).

**P4 — Unbounded history query.** `app.py:305-312` has no `LIMIT` and no
pagination, and `history.js:15-28` renders one DOM node per set with no
virtualisation. A user with a year of training pulls every set they have ever
logged into one response and one synchronous render loop.

**P5 — A new MySQL TCP connection + auth handshake per request.** `app.py:20-26`,
called at `app.py:39`, `:58`, `:99`, `:177`, `:211`, `:249`, `:274`, `:302`.

**P6 — 1.4 MB of unoptimised PNG on the landing page.** `index.html` loads
`step2.png` (360 KB), `step3.png` (246 KB), `phone.png` (208 KB), `DB.png`
(359 KB — a decorative dumbbell icon rendered at 42px, `style.css:150`),
`logo.png` (93 KB), `profile.png` (20 KB). No `width`/`height` attributes on any
`<img>` (`index.html:18`, `:23`, `:53`, `:74`, `:82`, `:97`, `:112`), so every
image causes a reflow as it arrives — layout shift on the highest-traffic page.
No `loading="lazy"` on the three below-the-fold step images. No modern format.

**P7 — 700 KB of assets shipped and never requested.**
`Frontend/assets/muscles/*.png` — eleven files, 46-78 KB each, referenced by no
HTML, CSS or JS (D8).

**P8 — Blocking render-path resources.** The Google Fonts stylesheet at
`index.html:10` is render-blocking with no `preconnect` and no `display=swap`
fallback strategy beyond the query param, and it loads *after* `style.css` whose
`*` selector at `style.css:3` already declares `Archivo`. Pages linking
`theme.css` never load the font at all yet `theme.css:8` asks for `'Segoe UI'`,
so typography differs page to page (U6).

**P9 — Layout thrash from repeated style writes.** `dashboard.js:29`, `:51`,
`:90`, `:156-161` each set `.style.display` on elements one at a time in separate
task contexts, after separate network responses — so the dashboard visibly
reflows two or three times after first paint as each `fetch` lands. The CTA
swap at `dashboard.js:156-161` is the worst: the button starts visible
(`index.html:46`) and is hidden after a round-trip, so logged-in users see the
wrong button flash.

---

## 9. Refactoring Plan

Target structure. One line of justification each; nothing here adds a feature.

```
EzGrind/
  Backend/
    app.py                    # app factory + blueprint registration only; no routes
    config.py                 # reads env vars, one place that knows secrets exist
    db.py                     # pooled connection + context manager that always closes
    errors.py                 # register_error_handlers(): every 4xx/5xx becomes JSON
    auth.py                   # @login_required, the check now written four times
    validators.py             # the six signup rules, so JS and Python can't drift alone
    routes/
      __init__.py
      auth_routes.py          # /api/signup, /api/login, /api/logout
      user_routes.py          # /api/me
      catalog_routes.py       # /api/muscles, /api/exercises  (public reference data)
      workout_routes.py       # /api/log-workout, /api/today-workout, /api/workout-history
    .env.example              # documents required config without committing values
    requirements.txt          # pinned

  Database/
    migrations/
      001_initial_schema.sql  # the CREATE TABLEs with the two ALTERs already folded in
      002_constraints.sql     # unique(user_id,workout_date), NOT NULLs, ON DELETE rules
      003_indexes.sql         # workouts(user_id, workout_date), separated so it can be timed
      004_seed_reference.sql  # muscle_groups + exercises seed — without it the app is dead
    README.md                 # the run order, since there is no migration runner

  Frontend/
    index.html  login.html  signup.html  profile.html
    log-workout.html  history.html  exercises.html
    css/
      tokens.css              # the variables in CLAUDE.md; every hex lives here or nowhere
      base.css                # reset, typography, body shell — loaded by every page
      components.css          # navbar, card, button, form, modal, table
      pages.css               # the genuinely page-specific bits that survive the above
    js/
      api.js                  # one fetch wrapper: base URL, credentials, JSON, 401, .catch
      auth.js                 # requireLogin() / redirectIfLoggedIn() guards
      dom.js                  # el(), setText(), renderEmpty(), renderError() helpers
      pages/
        dashboard.js  login.js  signup.js  profile.js  log-workout.js  history.js  exercises.js
    assets/                   # unreferenced muscle PNGs deleted or wired up, images compressed
  docs/
    AUDIT.md                  # this file
CLAUDE.md                     # standing rules, repo root
```

Why each module exists:

- `config.py` — S1 and S2 exist because there is no place for configuration to
  live other than the source file.
- `db.py` — kills R2 and R6 at once: a context manager cannot leak, a pool cannot
  re-handshake.
- `errors.py` — R1 and the API contract both require that no HTML ever reaches a
  `res.json()` call.
- `auth.py` — one decorator replaces the four copies at `app.py:88/246/271/299`
  and unifies the two message strings (R5).
- `validators.py` — B19: one source for the rules, imported by the routes,
  mirrored deliberately (not accidentally) in `signup.js`.
- `routes/*` — R9: nine routes grouped by resource, so auth changes touch one
  file.
- `migrations/00N_*.sql` — D1: the current file cannot be re-run and cannot be
  reasoned about; `004` is what makes B2 fixable.
- `css/tokens.css` — U7: three golds and six blacks collapse to two variables.
- `css/base.css` + `components.css` — U1, U6, U11: every page links the same two
  files in the same order, so "which stylesheet did this page get" stops being a
  question.
- `js/api.js` — B14 and R7: one place that owns the base URL (fifteen hardcoded
  copies today), attaches credentials, parses JSON, routes 401 to login, and has
  the `.catch()`.
- `js/auth.js` — B10 and B11 are both "this page has no idea it needs a session".
- `js/dom.js` — U8: empty/loading/error states only get written once if writing
  them is one call.
- `js/pages/*` — one file per page, same as today; the split is what lets each one
  shrink to page logic.

---

## 10. Implementation Order

Every phase ends with the app running. Within a phase, order is not significant
unless stated; across phases it is.

### Phase 0 — Make it possible to run at all
*Nothing else can be verified until the app has data and a reproducible setup.*

1. `Database/migrations/001_initial_schema.sql` — the five `CREATE TABLE`s with
   the `ALTER`s from `EzGrindDB.sql:53-65` folded in and the ad-hoc `SELECT`s
   (`:47-50`, `:60`, `:67`, `:70-78`) dropped. No constraint changes yet.
2. `004_seed_reference.sql` — seed `muscle_groups` and `exercises` (B2).
3. `Database/README.md` — run order.
4. Pin `requirements.txt` (R12).

**Before/after:** must precede everything. Phases 1-6 cannot be tested against an
empty `exercises` table — the log-workout, today-workout and history paths all
begin with picking an exercise. Nothing in this phase touches `app.py`, so the
running app is unchanged.

### Phase 1 — Secrets and debug
*Smallest possible diff, highest severity, zero behaviour change.*

5. `config.py` + `.env.example`; move `app.py:10` (secret), `app.py:22-25`
   (credentials) and the `debug` flag at `app.py:323` behind environment
   variables with safe defaults (S1, S2, S7).
6. Narrow CORS from `/*` to `/api/*` and from `origins: "*"` to an explicit
   allow-list read from config (`app.py:17`) (S4).
7. Set `SESSION_COOKIE_SAMESITE = 'Lax'` and `SESSION_COOKIE_HTTPONLY = True`
   explicitly (`app.py:13-14`), which also buys the CSRF defence in S5.

**Before/after:** must precede any deployment and any public exposure. Must come
*after* Phase 0 only so that there is a working app to confirm the config change
did not break login. **Must come before Phase 2**, because changing the session
secret invalidates existing sessions and it is better to do that once, now, than
after users exist. §11 Q3 must be answered before step 7 — the SameSite change
interacts with how the frontend is served.

### Phase 2 — Backend error contract
*Everything downstream assumes 4xx/5xx is JSON.*

8. `errors.py` — `@app.errorhandler` for 400/401/404/405/415/500 returning
   `{"error": {"code", "message"}}` (R1, and the contract in CLAUDE.md).
9. `db.py` — pooled connection context manager; convert all eight call sites
   (`app.py:39, 58, 99, 177, 211, 249, 274, 302`) (R2, R6).
10. `auth.py` — `@login_required`; replace the four inline checks
    (`app.py:88, 246, 271, 299`) (R5).
11. Convert every existing error response to the new envelope
    (the thirteen sites listed in R7).

**Before/after:** must come before Phase 3, because the frontend's shared `api.js`
is written against this envelope — writing it first would mean writing it twice.
Must come before Phase 4, because guarded input parsing needs somewhere to send
its 400s. Frontend still works throughout: success responses are unchanged in this
phase, and no current frontend code reads error bodies except `login.html:37` and
`signup.js:77`, which are rewritten in Phase 3.

### Phase 3 — Frontend plumbing and the P0 fixes
*The app becomes usable by a human for the first time.*

12. `js/api.js` — base URL, `credentials: "include"`, JSON parse, 401 → login,
    `.catch()` → visible error (B14, P1's precondition).
13. `js/auth.js` — page guards; apply to `profile.js` (B10) and `history.js`
    (B11).
14. Fix the login redirect: `login.html:39` keys on `res.ok`, not `data.user`
    (B1). Move the inline script to `js/pages/login.js`.
15. Fix `dashboard.js` — hoist `showAuthModal` out of the `DOMContentLoaded`
    closure (B3, `dashboard.js:88/168`), delete the duplicate `/api/me` calls at
    `:150` and the dead `profileBtn` block at `:113-128` (P1), collapse the
    remaining three fetches to one.
16. Fix `index.html:21-25` — remove `onclick="openProfile()"`, replace the
    `<button><a>` with a plain `<a class="profile-btn">` (B4, U3).
17. Fix `logWorkout.js` — delete the unconditional all-exercises fetch at
    `:48-57` (B5, P2) and the dead `user_id` at `:64` (B17).
18. Fix `exercises.js:20-23` against the actual response shape, or extend
    `app.py:62-73` to select the fields it needs — decide, then do one (B6).

**Before/after:** depends on Phase 2 for the 401 shape that `api.js` keys on.
Must come before Phase 5, because the CSS rewrite will move markup and it is
cheaper to fix behaviour on stable markup first. Steps 14-18 are independent of
each other and can land in any order.

### Phase 4 — Validation and the write path
*Now that errors are JSON and the frontend can display them.*

19. `validators.py` — extract `app.py:148-173`; add the missing rules for
    `/api/log-workout` (R4).
20. Guard every `data[...]` access (`app.py:94-96, 137-139, 208-209`) (R3).
21. Normalise empty strings to `NULL` for `date_of_birth` (B7) and
    `time_under_tension` (B9).
22. Accept decimals for height/weight, matching the `FLOAT` columns (B8, D9).
23. Reconcile `signup.js:14-56` with `validators.py` — same thresholds, same
    messages (B18, B19); drop the emoji string-match at `signup.js:78` in favour
    of the status code (B20).

**Before/after:** must follow Phase 2 (needs the error envelope) and Phase 3
(needs a frontend that surfaces 400s). Must precede Phase 6, because the unique
constraint added there will start returning integrity errors that only validated,
guarded routes can translate into clean 409/400 responses.

### Phase 5 — CSS and markup
*Purely presentational; no JS or API changes.*

24. `css/tokens.css` with the variables from CLAUDE.md; replace the three golds
    and six blacks (U7).
25. `base.css` + `components.css`; every page links the same two files in the same
    order — fixes the broken paths at `profile.html:7`, `log-workout.html:7`,
    `exercises.html:7` (B13/U1) and the in-body links at `login.html:8`,
    `profile.html:16`, `log-workout.html:16` (U2).
26. Fix `.step-text p` contrast (`style.css:201`) (B12); delete the duplicate
    rules at `style.css:181-186`, `:405-418` (B21).
27. Add `<meta name="viewport">` and `<meta charset>` and `lang` to all seven
    pages; fix `signup.html`'s missing `<body>` (U3, U4).
28. Responsive pass to 360px — navbar, hero, `theme.css:7` body padding,
    `.theme-card` (U5).
29. Labels with `for` on `log-workout.html:21-33` and `login.html`/`signup.html`;
    modal `role="dialog"` + `Esc` + close button + focus trap on
    `index.html:134-147`; focus-visible styles (U9).
30. Shared nav partial across pages; link `exercises.html` from it (B15, U11).

**Before/after:** independent of Phases 6-7; can run in parallel with Phase 4 if
two people are working. Must follow Phase 3, since step 16 changes the profile
button's markup and step 15 changes which elements the dashboard toggles.

### Phase 6 — Schema hardening
*Constraints last, because they reject data the app used to accept.*

31. `002_constraints.sql` — `UNIQUE (user_id, workout_date)` on `workouts` (D2,
    R11), `NOT NULL` on `workout_sets.weight`/`reps` (D6), `ON DELETE` rules
    (D4), unique names on reference tables (D5), `utf8mb4` (D10).
32. `003_indexes.sql` — `workouts(user_id, workout_date)` (D3, P3).
33. Make `app.py:102-115` rely on the new unique constraint
    (`INSERT ... ON DUPLICATE KEY` or catch the integrity error) (R11).
34. Add a set-ordering column to `workout_sets` and order history by it (D7).
35. Fix the `GROUP BY` at `app.py:283` to group by `exercise_id` (B16).

**Before/after:** must be last among the correctness phases. Adding
`UNIQUE (user_id, workout_date)` will fail outright if duplicate rows already
exist, so it needs a de-duplication step against real data; and it changes
`/api/log-workout`'s failure modes, which only Phase 2's error handling and Phase
4's validation can present cleanly. Step 33 must land in the same change as
step 31 — the constraint without the upsert turns a silent duplicate into a 500.

### Phase 7 — Performance
*Measurable only once the app is correct.*

36. Compress/resize the six landing-page PNGs; add explicit `width`/`height` and
    `loading="lazy"` (P6). Delete or wire up `assets/muscles/*` (P7, D8).
37. `preconnect` for the font, or self-host it and drop the third-party request
    (P8).
38. Add `LIMIT` + pagination to `/api/workout-history` (`app.py:305-312`) and to
    `history.js` (P4).
39. Collapse the dashboard's remaining reflows into a single post-fetch render
    (P9).

**Before/after:** last. Step 38 changes a response shape and must not land before
Phase 3's `api.js` exists to consume it.

### Deliberately not in any phase
Rate limiting (S6), account deletion (D4's user-facing half), HTTPS (S11), and
password-policy changes beyond length (S8) are real gaps, but every one of them is
new behaviour rather than a defect in existing behaviour, and this document does
not propose features.

---

## 11. Unverified — needs a running instance

Everything above was established by reading source. The following are strong
suspicions that depend on runtime behaviour I did not execute. They are listed
separately because each could change severity once tested.

**V1 — The session cookie may be rejected by the browser outright.
[CORRECTED — resolved in Phase 1]**
`app.py:13-14` set `SameSite=None` with `Secure=False`. Current Chrome and
Firefox reject `SameSite=None` cookies that are not also `Secure`, so the
suspicion was that no session ever persisted and every protected route 401'd
forever.

*Outcome:* the emitted header was never captured on the pre-Phase-1 code, so the
original suspicion is neither confirmed nor refuted and now cannot be — the
configuration it described no longer exists. Phase 1 replaced it, and the cookie
the app emits today is verified (`Backend/smoke.py`, 2026-07-28):

- development — `HttpOnly; Path=/; SameSite=Lax`, no `Secure`, 7-day expiry
- production — `Secure; HttpOnly; Path=/; SameSite=None`, 7-day expiry

The illegal pairing is now unreachable from any `FLASK_ENV` value, asserted in
`Backend/check_config.py`. **Live constraint replacing it:** `SameSite=Lax` is
only sent same-site, and the frontend hardcodes `http://127.0.0.1:5000`, so in
development the frontend must be opened from `http://127.0.0.1:5500` — not
`localhost:5500`, not `file://`. Q3 still matters, for that reason rather than
this one.

**V2 — What flask-cors actually emits for a credentialed wildcard.**
`app.py:17` requests `origins: "*"` together with `supports_credentials=True`. A
literal `Access-Control-Allow-Origin: *` is ignored by browsers when credentials
are involved, which would make the CORS config *fail closed*. flask-cors is
documented to reflect the request's `Origin` instead in this case, which would
make it *fail wide open* — any website could read a logged-in user's profile and
history. The package is not vendored in this tree (no `Backend/lib`), so I could
not read its source. **Test:** `curl -i -H "Origin: https://evil.example"
http://127.0.0.1:5000/api/me` and read the `Access-Control-Allow-Origin` header.
S4's severity hinges entirely on this.

**V3 — Whether B7 and B9 fail loudly or silently.**
Inserting `""` into a `DATE` or `INT` column raises error 1292/1366 under MySQL's
default `STRICT_TRANS_TABLES`, but silently coerces to `0000-00-00` / `0` if
strict mode is off. Either way it is a defect; the difference is "500 error page"
versus "corrupt row the user never learns about". The second is worse. **Test:**
`SELECT @@sql_mode;` then submit the signup form with a blank date of birth.

**V4 — Whether the duplicate `startTodayBtn` handlers fire in the order I
assumed.** `dashboard.js:166-170` registers at parse time and
`dashboard.js:96-109` registers on `DOMContentLoaded`, so I read the ReferenceError
as firing first and the working modal second (B3). If the script tag's position
(`index.html:131`, before the modal markup at `:134`) changes that timing,
`document.getElementById("authModal")` at `dashboard.js:82` could resolve to
`null` and the modal would never open at all — promoting B3 to a hard P0.
**Test:** click "START TODAY" logged out and watch both the console and the
modal.

**V5 — Actual render of the unstyled pages.** B13 says `exercises.html` gets no
CSS at all. The rendered result — unstyled black-on-white — is inferred from the
absence of a working `<link>`, not observed. **Test:** open the page.

**V6 — Whether `/api/me` can return `null`.** `app.py:258-263` returns
`jsonify(user)` with no `None` check, so a session referencing a deleted user
serialises to the literal `null`. There is no delete-user path in the code today
(D4), so this may be unreachable in practice. **Test:** delete a row from `users`
while holding its session cookie.

---

## 12. Open Questions

**Q1 — How is the frontend meant to be served?** Nothing in the repo serves it:
`app.py` has no `static_folder` configuration and no catch-all route, and there is
no dev-server config, `package.json`, or documented command. The answer decides
whether the app is same-origin (making S3, S4 and S5 largely moot and the fifteen
hardcoded `http://127.0.0.1:5000` URLs replaceable with relative paths) or
genuinely cross-origin (making all three critical and the refactor different).
I did not assume either.

**Q2 — Should Flask serve the frontend in the target structure?** Follows from Q1.
It would collapse the CORS and cookie problems to nothing, but changes the "static
files" framing in the brief. The structure in §9 assumes the current split.

**Q3 — Which origin does the browser actually load pages from — `file://`,
`localhost:PORT`, or `127.0.0.1:PORT`?** This determines V1's outcome and whether
`SameSite=Lax` (Phase 1, step 7) is sufficient or would break login.

**Q4 — Is `exercises.html` intended to ship?** It is unreachable (B15) and reads
fields the API does not return (B6). Fixing it means either extending
`/api/exercises` to join `muscle_groups` and return `muscle_name` + `image_path`,
or rewriting the card to the current shape. Since D8's correction shows the
`muscle_groups` rows already carry working `assets/muscles/*.png` paths, the
first option now looks like the original intent rather than speculative work —
the data is there and only the join and the render are missing. I still need you
to confirm before Phase 3 step 18, because the second option means deleting
eleven committed images.

**Q5 — Is the "muscle balance" / progress language on the dashboard
(`index.html:42`, `:104`) a description of intended future work, or copy for a
feature someone believes exists?** It has no backing endpoint or table (D11).
I have not proposed anything for it, per the no-new-features rule, but it changes
whether D11 is a modelling gap to fix or simply marketing copy to leave alone.

**Q6 — Should `date_of_birth`, `contact_number`, `height_cm` and `weight_kg` be
optional?** `app.py:141-144` treats all four as optional, `signup.html:16-19`
marks none of them `required`, but `signup.js:29-44` hard-requires contact, height
and weight (B18). Three different answers in three files. Phase 4 step 23 needs
the real one.

**Q7 — Is one workout row per user per day the intended model?**
`app.py:102-115` enforces it in code; the schema does not (D2). Two gym sessions
in one day currently merge into a single workout. Confirm before adding the unique
constraint in Phase 6, because the constraint makes that decision permanent.
