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
| **Exercise library** | ~2,900 exercises across 16 muscle groups, searchable and filterable, each opening a detail panel with your own numbers on that lift. |
| **Profile** | Age, height, weight and BMI with a scale, inline editing, password change, and account deletion behind a typed confirmation. |
| **Bodyweight** | Log daily, chart it over 1M/3M/6M/1Y/All, with change over 30 days coloured by whether it moves toward your stated goal. |

---

## Tech stack

**Frontend** — HTML5, CSS with custom properties, vanilla ES2020. No framework,
no bundler, no dependencies. Charts are hand-written inline SVG.

**Backend** — Python 3.10, Flask 3, PostgreSQL 16 via `psycopg2` with a threaded
connection pool. Session-cookie auth, scrypt password hashing, per-route rate
limiting. Gunicorn in production.

**Database** — PostgreSQL 16, hosted on [Neon](https://neon.tech). Numbered,
forward-only migrations applied by hand. Substring search over the exercise
catalogue uses a `pg_trgm` GIN index.

**Email** — [Resend](https://resend.com), with a console backend for local work.

---

## Repository layout

```
EzGrind/
├─ Backend/
│  ├─ app.py                  application factory; exposes module-level `app`
│  ├─ config.py               environment; refuses to boot without secrets
│  ├─ db.py                   connection pool, Neon-aware
│  ├─ repositories/           all SQL lives here
│  ├─ routes/                 blueprints, one per subject
│  ├─ services/               email
│  ├─ scripts/                operational tools (import, plans, migration)
│  └─ tests/                  runnable self-checks
├─ Database/
│  ├─ migrations/             001_schema.sql, 002_search.sql
│  ├─ migrations_mysql_archive/  the pre-Postgres history
│  ├─ seeds/                  16 muscle groups, 48 curated exercises
│  ├─ data/                   megaGymDataset.csv
│  └─ queries/scratch.sql     ad-hoc queries, never applied automatically
└─ Frontend/                  served by Flask; no build step
```

---

# LOCAL SETUP

### 1. Prerequisites

- **Python 3.10** (see `.python-version`)
- A **PostgreSQL 16** database — a free [Neon](https://neon.tech) project is what
  this is developed against; any Postgres 16 works
- **psql**, for applying migrations

### 2. Clone and create the virtualenv

```bash
git clone https://github.com/devanshkorde/EzGrind.git
cd EzGrind/EzGrind/Backend

python3 -m venv venv
source venv/bin/activate          # Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
```

Open `.env`, paste that value into `SECRET_KEY`, and set `DATABASE_URL` to your
Neon connection string (**Connection Details → psycopg2**). The app refuses to
start without both — a default secret key is worse than a crash, because the
crash gets noticed.

### 4. Create the schema

```bash
cd ../Database
psql "$DATABASE_URL" -f migrations/001_schema.sql
psql "$DATABASE_URL" -f migrations/002_search.sql
psql "$DATABASE_URL" -f seeds/muscle_groups_and_exercises.sql
```

Migrations are applied **in order** and are forward-only. The seed is **not
optional** — without it the muscle and exercise dropdowns are empty, no workout
can be logged, and the exercise import has no muscle groups to map onto.

### 5. Import the exercise catalogue

```bash
cd ../Backend
python scripts/import_exercises.py             # dry run — writes nothing
python scripts/import_exercises.py --write     # ~2,900 exercises
```

Dry run is the default. Re-running is harmless: it keys on
`(lower(exercise_name), muscle_id)`, existing rows win, and the CSV may only
fill blanks. Roughly half the imported rows have no description — that is the
data, not a bug, and the UI says so explicitly.

### 6. Run it

```bash
cd ../..          # repository root
./run.sh          # Windows: .\run.ps1
```

Then open **http://127.0.0.1:5000**.

> **Not Live Server, and not port 5500.** Flask serves the frontend itself, so
> the whole app is one origin. That is what lets the frontend call `/api`
> relatively and what makes the `SameSite=Lax` session cookie work. Opening the
> HTML from a different port will appear to log you in and then 401 every
> request.

### Running the tests

```bash
cd EzGrind/Backend
python tests/check_config.py           # config matrix, no database needed
python tests/smoke.py                  # API contract, read-only
python tests/smoke.py --write          # + signup and log-a-set
python tests/check_resend.py           # email paths, sends nothing
python tests/check_password_reset.py   # reset flow and password policy
python scripts/check_plans.py          # EXPLAIN every query, assert indexes

cd ../Frontend
python tests/check_frontend.py         # HTML/CSS invariants
node tests/check_stats.js              # dashboard date/name formatting
```

---

# DEPLOYING TO RENDER

Create a **Web Service** pointed at this repository, branch **`main`**.

### Build command

```
pip install -r EzGrind/Backend/requirements.txt
```

### Start command

```
gunicorn --chdir EzGrind/Backend app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60
```

`app.py` exposes a module-level `app`, so `app:app` resolves directly.
`--chdir` puts `EzGrind/Backend` on `sys.path` so `import config` and friends
work. `$PORT` is supplied by Render — never hardcode 5000; `app.run()` is
guarded by `__main__` and gunicorn never reaches it.

### Python version

`.python-version` at the repository root pins **3.10.11**. Without it Render
picks its own default, which drifts upward over time and will eventually not be
the interpreter you developed against.

### Environment variables

| Variable | Value |
|---|---|
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"`. **Use a different one than local.** Rotating it signs everyone out; nothing else breaks. |
| `DATABASE_URL` | Neon connection string. `sslmode=require` is appended automatically if absent. |
| `FLASK_ENV` | `production` — turns off debug and sets `Secure` on the session cookie. |
| `APP_BASE_URL` | **Your production `https://` URL.** See the warning below. |
| `EMAIL_BACKEND` | `resend` |
| `RESEND_API_KEY` | From the Resend dashboard. Required when `EMAIL_BACKEND=resend`; the app refuses to boot without it. |
| `MAIL_FROM_ADDRESS` | An address on a **verified domain**. See the warning below. |
| `MAIL_FROM_NAME` | `EzGrind` |
| `ALLOWED_ORIGINS` | Your production URL. Unused while the app is single-origin, but keep it correct. |
| `DB_POOL_SIZE` | `5`. This is **per gunicorn worker** — 2 workers × 5 = 10 connections against Neon's limit. |

> ### ⚠️ `APP_BASE_URL` must be the production HTTPS URL
> Emails cannot use relative links, so every password-reset and welcome link is
> built from this one value. If it still says `http://127.0.0.1:5000`, every
> link you send is dead on arrival — and the send still reports success, so
> nothing will tell you.

> ### ⚠️ `MAIL_FROM_ADDRESS` must be a verified domain
> `onboarding@resend.dev` is Resend's sandbox sender. It delivers **only** to
> the address that owns the Resend account and rejects every other recipient
> with a 403. Signups and resets appear to succeed while nobody receives
> anything, because an email failure deliberately never fails the request that
> triggered it. Verify a domain at <https://resend.com/domains> first. The app
> logs a warning at boot if you launch with the sandbox sender.

### Migrations on Render

There is no migration runner and no release phase configured. Apply schema
changes yourself against the production `DATABASE_URL` **before** deploying the
code that needs them, exactly as in local setup step 4.

---

## Troubleshooting

**First request after a pause takes several seconds.**
Neon's free tier scales compute to zero when idle. The first query pays a resume
penalty. `db.py` pings each pooled connection before handing it out and
reconnects if it is dead, so this costs latency, not an error.

**First request after 15 minutes takes ~50 seconds.**
Different problem, same symptom. Render's free tier spins a service down after
15 minutes of no traffic, and the next request has to boot the container. Not
fixable on the free plan; a paid instance or an external uptime pinger avoids it.

**`sslmode` errors, or connections mysteriously refused.**
Neon requires TLS. `config.py` appends `sslmode=require` if your `DATABASE_URL`
omits it — libpq's default is `prefer`, which silently *downgrades* to plaintext
rather than failing, so this is forced rather than trusted.

**`pip install psycopg2-binary` fails on Windows.**
Only on MSYS2/mingw64 Python, whose platform tag is `mingw_x86_64` while every
PyPI wheel is `win_amd64` — so pip falls through to a source build that fails.
Either use a python.org CPython, or install MSYS2's prebuilt package and copy it
into the venv. Full instructions are in the comment in `requirements.txt`. This
never affects Render, which is Linux.

**Login succeeds, then every request 401s.**
You are opening the frontend from a different origin than the API — typically
Live Server on `:5500`. Use `http://127.0.0.1:5000`.

**The exercise library is empty.**
The seed or the import has not been run. See local setup steps 4 and 5.

**`ON CONFLICT` errors during the exercise import.**
The seed has not been applied, so the muscle groups the CSV maps onto do not
exist. Run the seed first.

---

## Licence

MIT — see [LICENSE](LICENSE). The exercise dataset in `Database/data/` is
third-party and carries its own terms.
