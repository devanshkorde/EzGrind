# EzGrind Architecture

Why the code is arranged the way it is. For *what* each endpoint does, see
[`API.md`](API.md); for the schema, see
[`../EzGrind/Database/README.md`](../EzGrind/Database/README.md).

---

## The shape of it

Two halves that share nothing but the JSON contract.

```
Browser  ──HTTP──▶  Live Server :5500  ──▶  static files (HTML, CSS, JS)
   │
   └──── fetch(credentials: include) ────▶  Flask :5000  ──▶  PostgreSQL (Neon)
```

The frontend is served as plain files. Flask serves **no HTML at all** — it is a
JSON API and nothing else. That separation is why the CORS and cookie
configuration matters so much, and it is the source of the one setup trap
documented in the README.

---

## Request lifecycle

A signed-in user logging a set:

```
1.  logWorkout.js          collects the form, validates client-side for speed
2.  api.js                 the only file that calls fetch()
                           attaches credentials, serialises, parses the envelope
3.  Flask routing          matches POST /api/log-workout
4.  auth.login_required    reads session["user_id"], raises ApiError(401) if absent
5.  validators             require_weight / require_reps / optional_text
                           raise ApiError(400, …, field) on anything malformed
6.  workout_routes         calls the repository, serialises the result
7.  workout_repo.log_set   ONE transaction:
                             upsert today's workout  (relies on the unique key)
                             compute the next set_order
                             insert the set
                             upsert the personal record
8.  db.get_cursor          commits on clean exit, rolls back on any exception,
                           returns the connection to the pool in `finally`
9.  errors.py              any ApiError or unhandled exception becomes JSON
10. api.js                 resolves {data, message} or throws a typed ApiError
11. logWorkout.js          confirms the optimistic row, or rolls it back
```

Every failure at any step lands in `errors.py` and comes back as
`{"error": {...}}`. There is no path that produces HTML.

---

## Backend layers

Four layers, each with one job. The rule that keeps them honest: **no SQL above
`repositories/`, and no HTTP below `routes/`.**

| Layer | Files | Responsibility | Never does |
|---|---|---|---|
| **Composition** | `app.py` | Build the app, wire extensions, register blueprints | Contain a route or a query |
| **HTTP** | `routes/*` | Parse, validate, call a repository, serialise | Write SQL |
| **Data** | `repositories/*` | Every SQL statement in the application | Read a session, raise 4xx, know status codes |
| **Cross-cutting** | `config`, `db`, `errors`, `auth`, `validators` | Configuration, pooling, the error contract, identity, field rules | — |

Repositories return plain dicts and lists. That means they work from a script or
a migration, not only from inside a request — which is exactly why `smoke.py` can
test the streak arithmetic directly, with no HTTP involved.

### Why an application factory

`create_app()` builds and returns the app rather than configuring a module-level
global. It keeps `app.py` to registration only, and it means a test can build a
second instance with different configuration — which `smoke.py` does, rebuilding
the app under both `FLASK_ENV` values to check the session cookie flags.

### Why a connection pool with context managers

The original code opened a fresh connection per request and expected callers to
close it. They couldn't, reliably: an early `return` on the duplicate-email path
leaked one connection per rejected signup.

`db.get_cursor()` is a context manager that commits on clean exit, rolls back on
exception, and closes in `finally`. **There is no way to get a connection without
one**, so the leak is structurally impossible rather than merely fixed.

It also gives transactions for free: everything inside a single `with` block
shares one. `log_set` uses this to make the workout, the set and the personal
record atomic.

### Why validation is split in two

`validators.py` has two layers that look similar and are not:

- `require_*` / `optional_*` — *is this field present and the right kind of thing*
- `validate_*` — *is this value acceptable to the domain*

Extraction failures and domain failures produce the same `ApiError` shape but
answer different questions, and mixing them produces functions that do both
badly. Both carry a `field`, so a form can attach any message to the right input.

The frontend repeats these rules for instant feedback. **The server copy is
authoritative** — the client's can be bypassed with a terminal.

---

## Security model

### Identity

`session["user_id"]` is the only source of identity in the application. It is set
by `login_user()` and read by `current_user_id()`, both in `auth.py`.

**No endpoint accepts a user id from a client** — not in a path, not in a query
string, not in a body. There is no parameter to tamper with, which is a stronger
guarantee than validating one.

### Scoping

Every query touching user data filters on `user_id` in its `WHERE`. Set-level
queries reach it by joining through `workouts`.

Ownership checks live **in the `WHERE` clause of the statement that acts**, not in
a separate lookup:

```sql
DELETE ws FROM workout_sets ws
JOIN workouts w ON w.workout_id = ws.workout_id
WHERE ws.set_id = %s AND w.user_id = %s
```

There is no window between checking and acting, and no code path where a caller
forgets to check.

A row that isn't yours answers **404, never 403**. A 403 confirms the id exists,
which turns the endpoint into a way to enumerate other people's data.

### SQL

Every value reaches Postgres as a `%s` parameter. Several queries build their
SQL with f-strings — those interpolate **only whitelisted fragments**: a column
list from a module constant, a sort order from a lookup dict, a `JOIN` clause
chosen by a boolean, a date-bucket expression chosen by a validated enum. No
request value is ever formatted into a statement.

### Output

Nothing in the frontend uses `innerHTML`. Every rendered value goes through
`textContent` or `createElement`, so an exercise name or a display name cannot
carry markup into the page.

---

## Frontend layers

No framework, no build step. Structure comes from load order and one rule per
file.

### CSS: five files, always in this order

```
tokens.css      custom properties only — the only file with a literal colour
base.css        reset, typography, bare elements
components.css  buttons, cards, inputs, dialogs, toasts, charts
layout.css      containers, grids, page shells, responsive
pages.css       what genuinely belongs to one page
```

Load order *is* the cascade. A component can rely on base, a page can rely on a
component, and nothing reaches backwards. `check_frontend.py` fails the build if a
page links them out of order or omits one.

### JavaScript: one job per file

```
api.js       the only file permitted to call fetch()
ui.js        toasts, dialogs, skeletons, empty states, error states, offline
charts.js    inline SVG — one lineChart, with presets per series
shell.js     nav, footer and skip link, injected into every page
<page>.js    one per page, loaded last
```

`api.js` being the only caller of `fetch` is enforced by `check_frontend.py`. It
means the base URL, credentials, the response envelope, the 401 redirect and the
network-failure message exist in exactly one place. When the response shape
changed in Phase 2, one file changed.

`api.session()` caches `/api/me` for the page's lifetime, so the nav shell and the
page script share one request rather than each making their own.

---

## Why these trade-offs

**No framework.** The app is a handful of forms and lists. A framework would add a
build step, a dependency tree and a compile-to-debug loop to solve problems this
size doesn't have. The cost is manual DOM construction, which is verbose but
obvious.

**No build step means no bundling or minification.** Accepted deliberately. The
consequence is that cache-busting has to be handled at deploy time rather than by
content hashing.

**Session cookies rather than tokens.** `HttpOnly` cookies aren't readable by
JavaScript, so an XSS bug can't exfiltrate the session. The cost is CSRF exposure,
mitigated by `SameSite=Lax` in development; a production deployment on `None` +
`Secure` needs real CSRF tokens.

**Statistics computed in SQL, assembled in Python.** Aggregates are grouped by the
database; streaks and run-lengths are computed in Python from a small list of
distinct dates. Gaps-and-islands in SQL is clever and unreadable; a loop over a
few hundred dates is neither.

**Migrations applied by hand.** No Alembic, no runner. Numbered, idempotent,
forward-only files. At this size a runner is a dependency and a state table to
get wrong; the cost is remembering to run them, which the README covers.

---

## Verification

Four self-checks, no framework:

| Command | Checks |
|---|---|
| `python smoke.py [--write]` | The whole API contract: auth, scoping, validation, pagination, cross-user isolation |
| `python check_config.py` | Configuration refuses to start without secrets; the cookie matrix |
| `python check_frontend.py` | Markup structure, CSS layering, no hex outside tokens, no `fetch` outside `api.js`, no ungated `:hover`, every `vh` has a `dvh` |
| `node check_stats.js` | Date and formatting logic against the shipped source |

They run against the real files rather than copies, so they fail when the code
they describe changes shape.
