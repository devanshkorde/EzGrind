# EzGrind Database

PostgreSQL 16, hosted on [Neon](https://neon.tech). One connection string,
`DATABASE_URL`, in `Backend/.env`.

There is no migration runner. Files are applied by hand, in filename order, and
numbering is forward-only.

```
Database/
├─ migrations/
│  ├─ 001_schema.sql                  every table, constraint and index
│  └─ 002_search.sql                  pg_trgm + the GIN index on exercise_name
├─ migrations_mysql_archive/
│  └─ 001-008                         the MySQL originals, kept as history
├─ seeds/
│  └─ muscle_groups_and_exercises.sql 16 muscle groups, 48 exercises
├─ scripts/
│  ├─ import_exercises.py             the ~2,900 row megaGym import
│  └─ make_placeholder.py             generates assets/muscles/placeholder.png
├─ queries/
│  └─ scratch.sql                     ad-hoc queries, never applied automatically
└─ EzGrindDB.sql                      obsolete, kept as a pointer
```

---

## Create the database from scratch

```bash
cd EzGrind/Database

psql "$DATABASE_URL" -f migrations/001_schema.sql
psql "$DATABASE_URL" -f migrations/002_search.sql
psql "$DATABASE_URL" -f seeds/muscle_groups_and_exercises.sql
```

Neon creates the database itself, so unlike the old MySQL `001` nothing here
issues `CREATE DATABASE`.

Without the seed file the muscle and exercise dropdowns are empty, no workout
can be logged, and every feature downstream of exercise selection is dead. It is
not optional for a fresh install.

Then optionally load the full catalogue:

```bash
cd scripts
python import_exercises.py "D:\megaGymDataset.csv" --dry-run
python import_exercises.py "D:\megaGymDataset.csv"
```

## Migrating from the old MySQL database

```bash
cd EzGrind/Backend
pip install mysql-connector-python==8.4.0   # only for this script

python scripts/migrate_mysql_to_postgres.py --dry-run
python scripts/migrate_mysql_to_postgres.py
```

Preserves every primary key, runs parents before children, lowercases emails,
and ends by resetting all eight identity sequences. **Skip the seed file** if
you do this — `muscle_groups` and `exercises` come across with their existing
ids.

## Checking the query plans

```bash
cd EzGrind/Backend
python scripts/check_plans.py
```

Runs `EXPLAIN` over every query the application issues and reports which index
each one used. Postgres plans differently from MySQL, and an index that is
merely present is not an index that is used.

### Ordering rules

- **Numbers only go up.** Never edit a migration that has been applied
  anywhere; write a new one. The next free number is `003`.
- **`002` must be applied before the backend starts.** `exercise_repo` searches
  with `ILIKE '%term%'`; without the trigram index that is a sequential scan of
  the whole catalogue on every keystroke. It returns the right answer, just
  slowly, so nothing will fail loudly to tell you.

### Why the migrations are not a translation of the MySQL ones

The MySQL sequence migrated a database that already existed: `002` added
constraints to live tables, `005` added columns before a bulk import, `008`
widened a column `007` had got wrong. Neon starts empty. Replaying that as
Postgres would build the final shape through five ALTERs that never needed to
happen here. `001_schema.sql` is that final shape, stated once.

The originals are in `migrations_mysql_archive/`, unchanged. They are the
history of how the schema got here, and the reference for anyone reading a
comment that mentions "migration 004".

---

## What changed in the move from MySQL

The parts that behave differently, rather than the parts that were merely
retyped:

| | MySQL | PostgreSQL |
|---|---|---|
| **String comparison** | `utf8mb4_0900_ai_ci` — case-insensitive everywhere, for free | Exact. `users.email`, `muscle_groups.muscle_name` and `exercises(exercise_name, muscle_id)` are UNIQUE on `lower(...)`, and `validate_email` lowercases on the way in |
| **Search** | `FULLTEXT` + `MATCH … AGAINST`, word-based, dead below 3 characters | `pg_trgm` GIN + `ILIKE '%term%'`, substring-based, correct at every length |
| **Name ordering** | Collation-defined | `exercise_name` is `COLLATE "C"`, so keyset paging cannot disagree with its index |
| **Integer division** | `5 / 30` = `0.1667` | `5 / 30` = `0`. Every Epley divides by `30.0` |
| **Foreign key indexes** | InnoDB creates one automatically | It does not. Six are declared explicitly in `001` |
| **Timestamps** | `DATETIME`, naive, whole seconds unless told otherwise | `TIMESTAMPTZ`, microseconds by default. Session invalidation depends on the zone |
| **Upsert** | `ON DUPLICATE KEY UPDATE`, evaluated left to right | `ON CONFLICT … DO UPDATE … WHERE`, whole row at once |
| **New row id** | `cursor.lastrowid` | `RETURNING` |
| **Explicit ids** | `AUTO_INCREMENT` self-corrects | Identity sequences do not. `setval` after any explicit-id insert |

---

## Entity relationships

```
users ──1:N──> workouts ──1:N──> workout_sets ──N:1──> exercises ──N:1──> muscle_groups
  │                                                         ^
  ├──1:N──> weight_logs                                     │
  ├──1:N──> personal_records ───────────N:1─────────────────┘
  └──1:N──> password_reset_tokens
```

| Relationship | Delete rule | Reasoning |
|---|---|---|
| `workouts` → `users` | RESTRICT | A user with training history cannot be deleted without a deliberate decision. |
| `workout_sets` → `workouts` | **CASCADE** | A set with no parent workout has no date and no owner. It is garbage, not data. |
| `workout_sets` → `exercises` | RESTRICT | Deleting a catalogue entry that history points at should fail loudly. |
| `exercises` → `muscle_groups` | RESTRICT | Deleting a muscle group must not silently erase the exercise catalogue. |
| `weight_logs` → `users` | **CASCADE** | A weight reading with no owner is meaningless. |
| `personal_records` → `users` | **CASCADE** | Same; and the table is a rebuildable cache regardless. |
| `personal_records` → `exercises` | RESTRICT | A PR referencing a deleted exercise should require a human. |
| `password_reset_tokens` → `users` | **CASCADE** | A deleted account's pending tokens are worthless and must not outlive it. |

---

## Tables

### `users`
One row per account. `user_id` is the surrogate key everything else hangs off.
`full_name` is the display name shown in the dashboard greeting. `email` is the
login identifier and is UNIQUE **on `lower(email)`** — under MySQL's collation
the case-insensitivity was free, and losing it silently would let one person
register twice and then fail to log in. `password_hash` stores a Werkzeug
scrypt hash — never a password, and never returned by any endpoint.
`created_at` stamps registration. `password_changed_at` is `TIMESTAMPTZ` and
nullable; setting it ends every session opened before that moment, which is how
"sign out my other devices" works with cookie-based auth. The zone matters:
`auth._session_is_current` compares it against a UTC epoch float, so a naive
timestamp would be wrong by the offset between the web process and the
database. The remaining five columns are optional profile data collected at
signup: `contact_number` (validated as ten digits by the application),
`date_of_birth`, `height_cm` and `weight_kg` (both `REAL`), and `fitness_goal`
(one of `gain`, `lose`, `maintain`, `muscle`, enforced by `validators.py` —
the column accepts any short string).

### `muscle_groups`
Reference data, sixteen rows. `muscle_id` is the key exercises hang off, and
the ids are curated in training order (Chest, Lats, Upper Back … Core) rather
than alphabetically, which is why the catalogue sorts by id. `muscle_name` is
the display label, UNIQUE on `lower(muscle_name)`. `image_path` is relative to
`Frontend/`, e.g. `assets/muscles/chest.png`. Groups 13-16 (Forearms,
Abductors, Adductors, Neck) arrived with the exercise import and share a
generated placeholder.

### `exercises`
Reference data, the movement catalogue. `exercise_id` is what a logged set
points at. `exercise_name` is `COLLATE "C"` — byte ordering — so that the
keyset cursor, the `ORDER BY` and the index behind them cannot disagree; that
disagreement is invisible, and shows up as exercises missing from "Load more"
rather than as an error. UNIQUE on `(lower(exercise_name), muscle_id)`, so the
same name can exist under two muscle groups but not twice under one, and the
importer's case-insensitive dedup matches what is enforced. `muscle_id` is the
owning group. `equipment`, `exercise_type`, `difficulty_level` and `rating` are
imported metadata, all nullable because the source has gaps in every one of
them and a blank is not the same claim as a zero. `description` is prose.

### `workouts`
One row per user per training day — a container, holding no training data of
its own. `(user_id, workout_date)` is UNIQUE, which is what `log_set` upserts
against. `workout_date` is set from the **application's** `date.today()`, not
`CURRENT_DATE`: the streak logic in `stats_repo` uses Python's clock, and once
the database is a different machine in a different zone the two would disagree
and break streaks.

### `workout_sets`
One row per set performed — the actual training data. `weight` is
`NUMERIC(6,2)` in kilograms, nullable for bodyweight movements. `reps` is
`SMALLINT` with `CHECK (reps > 0)`. `time_under_tension` is **no longer
written**: the input was removed from the form, but the column and its history
stay. `comments` is an optional note per set, capped at 500 characters.
`set_order` makes "set 1 versus set 4" answerable, since row order in storage
is an implementation detail and not a promise. One index,
`(workout_id, set_order)`, serves the foreign key, the join, the ordering and
the next-set-number lookup.

### `weight_logs`
Bodyweight over time. `users.weight_kg` holds only the current value and is
overwritten, so it cannot answer whether someone is trending up or down.
`(user_id, logged_on)` is UNIQUE, so a second entry on the same day corrects
the first rather than stacking — a morning of nervous re-weighing cannot skew a
trend line.

### `personal_records`
Best effort per user per exercise. **A derived cache, not a source of truth.**
It must always be rebuildable from `workout_sets`; the rebuild statement in
`queries/scratch.sql` is the actual definition of what belongs here. If the
table ever disagrees with the sets, the sets win. `estimated_1rm` is the Epley
projection, `weight × (1 + reps ÷ 30)`, stored rather than computed so changing
the formula later does not silently rewrite history — and divided by `30.0`,
because `reps` is `SMALLINT` and integer division would floor every set under
30 reps to a 1RM equal to its own weight. `achieved_on` is tie-broken toward
the earliest date, so a PR keeps the day it was first set. `updated_at` is set
explicitly by the two writers in `workout_repo`; Postgres has no
`ON UPDATE CURRENT_TIMESTAMP`, and a trigger for a column nothing reads back
was not worth it.

### `password_reset_tokens`
`token_hash` is the hex SHA-256 of the token that was emailed — the raw token
is never stored, so a dump of this table yields nothing that can be put in a
URL. Unsalted deliberately: the input is 256 bits from `secrets`, so there is
no dictionary to precompute against, and a per-row salt would destroy the
indexed lookup that makes redemption a single seek. Not UNIQUE on `token_hash`:
a collision is impossible in practice, and the constraint would turn that
impossibility into a 500 on a password reset. `expires_at` and `used_at` are
`TIMESTAMPTZ` and compared against `datetime.now(timezone.utc)`.

---

## `EzGrindDB.sql`

Obsolete. It was a MySQL scratchpad that mixed table definitions, exploratory
`SELECT`s and later `ALTER` fixes into one file, so running it top to bottom
produced tables that were then patched by statements further down. Superseded
by `migrations/001_schema.sql`; its queries moved to `queries/scratch.sql`. The
original content remains in git history.
