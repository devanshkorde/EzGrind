# EzGrind

A workout tracker for people who lift. Log sets in a few taps, watch the volume
and the streak accumulate, and see your personal records move.

Built deliberately without a frontend framework or a build step: HTML, CSS and
vanilla JavaScript on the client, Flask and PostgreSQL on the server. Nothing is
transpiled, bundled or installed on the frontend — the files you edit are the
files the browser runs.

---

## What it does

| | |
|---|---|
| **Log a workout** | Pick a muscle group from a visual grid, pick an exercise, enter weight and reps with large touch targets. Weight and reps prefill from your last set of that exercise. Sets accumulate in a live session panel with a running total and elapsed time. |
| **History** | Sessions grouped by day, each expanding to a table of exercises and sets with estimated 1RM. Filter by date range, muscle group or exercise; filters live in the URL so a view is shareable. Volume-over-time chart. |
| **Dashboard** | Streak with a 7-day dot row, workouts this week, total volume, sets per workout, bodyweight with goal-aware trend, today's session, recent workouts, muscle distribution, and personal records. |
| **Exercise library** | 48 exercises across 12 muscle groups, searchable and filterable, each opening a detail panel with your own numbers on that lift. |
| **Profile** | Age, height, weight and BMI with a scale, inline editing, password change, and account deletion behind a typed confirmation. |
| **Bodyweight** | Log daily, chart it over 1M/3M/6M/1Y/All, with change over 30 days coloured by whether it moves toward your stated goal. |

---

## Screenshots

> Not yet captured. Run the app locally (below) and the pages worth grabbing are
> `index.html` signed in, `log-workout.html` mid-session, and `history.html` with
> a few sessions logged.

---

## Tech stack

**Frontend** — HTML5, CSS with custom properties, vanilla ES2020. No framework,
no bundler, no dependencies. Charts are hand-written inline SVG.

**Backend** — Python 3.10, Flask 3, PostgreSQL 16 via `psycopg2` with a threaded
connection pool. Session-cookie auth, scrypt password hashing, per-route rate
limiting.

**Database** — PostgreSQL 16, hosted on [Neon](https://neon.tech). Schema
managed by numbered, forward-only migration files applied by hand. Substring
search over the exercise catalogue uses a `pg_trgm` GIN index.

---

## Local setup

### 1. Prerequisites

- Python 3.10+
- A PostgreSQL 16 database. A free [Neon](https://neon.tech) project is what
  this is developed against; any Postgres 16 works, local or hosted.
- `psql`, for applying the schema
- A static file server for the frontend (VS Code's **Live Server** extension is
  what this was developed against)

### 2. Create the database

Set `DATABASE_URL` to your connection string first — Neon shows it under
**Connection Details → psycopg2**.

```bash
cd EzGrind/Database

psql "$DATABASE_URL" -f migrations/001_schema.sql
psql "$DATABASE_URL" -f migrations/002_search.sql
psql "$DATABASE_URL" -f seeds/muscle_groups_and_exercises.sql
```

**The seed is not optional** — without it the muscle and exercise dropdowns are
empty and no workout can be logged. It also resets the identity sequences past
the ids it writes, which is what stops the first exercise you add colliding
with `Bench Press`.

Full details, including the ER diagram and a description of every column, are in
[`EzGrind/Database/README.md`](EzGrind/Database/README.md).

### 3. Configure the backend

```bash
cd EzGrind/Backend

python -m venv venv
.\venv\Scripts\activate          # Windows (python.org)
# .\venv\bin\activate            # Windows (msys2/MinGW builds use bin\)
# source venv/bin/activate       # macOS / Linux

pip install -r requirements.txt

cp .env.example .env             # copy .env.example on Windows
python -c "import secrets; print(secrets.token_hex(32))"
```

Open `.env` and set `SECRET_KEY` to the generated value and `DATABASE_URL` to
your connection string. **The app refuses to start if either is missing** — a
default secret key is worse than a crash, because the crash gets noticed.
`sslmode=require` is appended to the URL automatically if you leave it off;
libpq's default would quietly downgrade to plaintext instead of failing.

### Migrating existing MySQL data

If you have data in the old MySQL database, copy it across with:

```bash
cd EzGrind/Backend
pip install mysql-connector-python==8.4.0   # only needed for this one script

python scripts/migrate_mysql_to_postgres.py --dry-run
python scripts/migrate_mysql_to_postgres.py
```

It preserves every primary key, so `workout_sets` keeps pointing at the right
workouts and exercises, and it resets all eight identity sequences afterwards.
Skip the seed file in that case — the reference tables come across too.

### 4. Run both halves

```bash
# from the repository root
.\run.ps1
```

Or manually:

```bash
cd EzGrind/Backend && python app.py     # http://127.0.0.1:5000
```

Then serve `EzGrind/Frontend` with Live Server and open
**`http://127.0.0.1:5500`**.

> **Use `127.0.0.1`, not `localhost`.** See troubleshooting below — this is the
> single most common way to get a login that appears to succeed and then doesn't.

### 5. Verify

```bash
cd EzGrind/Backend
python smoke.py            # API contract, read-only
python check_config.py     # configuration guards

cd ../Frontend
python check_frontend.py   # markup, CSS and JS invariants
node check_stats.js        # date and formatting logic
```

`smoke.py --write` additionally exercises signup, logging sets and deletion. It
creates two throwaway accounts and removes them again at the end.

---

## Project structure

```
EzGrind/
├─ Backend/
│  ├─ app.py                  application factory and blueprint registration
│  ├─ config.py               environment loading; refuses to start without secrets
│  ├─ db.py                   connection pool and context managers
│  ├─ errors.py               ApiError and the JSON error contract
│  ├─ auth.py                 @login_required, session helpers, rate limiter
│  ├─ validators.py           request field extraction and domain rules
│  ├─ routes/                 HTTP layer — parse, validate, call a repo, serialise
│  ├─ repositories/           every SQL statement in the application
│  ├─ smoke.py                end-to-end API checks
│  └─ check_config.py         configuration self-check
│
├─ Database/
│  ├─ migrations/             numbered, idempotent, forward-only
│  ├─ seeds/                  reference data
│  └─ queries/scratch.sql     ad-hoc queries and the PR rebuild statement
│
└─ Frontend/
   ├─ *.html                  nine pages, no templating
   ├─ css/                    tokens → base → components → layout → pages
   ├─ js/
   │  ├─ api.js               the only file that calls fetch()
   │  ├─ ui.js                toasts, dialogs, skeletons, empty and error states
   │  ├─ charts.js            inline SVG charts
   │  ├─ components/shell.js  nav, footer and skip link, injected everywhere
   │  └─ *.js                 one script per page
   ├─ check_frontend.py       static checks over markup, CSS and JS
   └─ check_stats.js          logic checks against the shipped dashboard source
```

The reasoning behind this layout is in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Every endpoint is documented in
[`docs/API.md`](docs/API.md).

---

## Troubleshooting

### Login seems to work, but you're still signed out

**Almost always the hostname.** Open the frontend at `http://127.0.0.1:5500`, not
`http://localhost:5500`.

Cookies ignore ports but not hostnames, so `localhost:5500` → `127.0.0.1:5000` is
a *cross-site* request. In development the session cookie is `SameSite=Lax`, which
browsers refuse to send cross-site. The login succeeds, the cookie is set, and
then never comes back — so every subsequent request is anonymous.

Check it in DevTools → Application → Cookies. If there's a `session` cookie but
requests are still 401ing, this is why.

### `Access to fetch … has been blocked by CORS policy`

The origin you're browsing from isn't in `ALLOWED_ORIGINS`. Add it to `.env`:

```
ALLOWED_ORIGINS=http://localhost:5500,http://127.0.0.1:5500
```

Then **restart the backend** — `.env` is read once at import, and Flask's reloader
watches `.py` files, not `.env`.

Note that a wildcard origin is not an option: browsers reject `*` on credentialed
requests, which is exactly what a session cookie makes this.

### `ConfigError: SECRET_KEY is not set`

Working as designed. Copy `.env.example` to `.env` and fill in `SECRET_KEY` and
`DB_PASSWORD`. There are no fallback defaults for either.

### `Can't reach the server — is the backend running?`

The Flask process isn't up, or it crashed. Check the terminal running `app.py`.

### Opening the frontend from `file://`

Won't work. The `file://` origin is `null`, which can't be allow-listed for
credentialed requests. Serve it over HTTP.

### Logging a set returns 500

A migration hasn't been applied. `workout_sets` needs `set_order` and `comments`,
which arrive in `002` and `004`. Verify with:

```sql
SHOW COLUMNS FROM workout_sets;
```

### Everything looks unstyled after an update

Cached CSS. Hard-refresh with **Ctrl+Shift+R**.

---

## Licence

Not yet chosen.
