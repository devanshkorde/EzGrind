# EzGrind Database

MySQL 8.0. Schema name `ezgrind_db`, everything InnoDB / `utf8mb4_0900_ai_ci`.

There is no migration runner. Files are applied by hand, in filename order, and
every one of them is written to be safe to re-run.

```
Database/
├─ migrations/
│  ├─ 001_baseline.sql               current schema, as it already exists
│  ├─ 002_constraints_and_indexes.sql constraints, ordering, type fixes
│  ├─ 003_new_tables.sql             weight_logs, personal_records
│  └─ 004_set_comments.sql           workout_sets.comments
├─ seeds/
│  └─ muscle_groups_and_exercises.sql 12 muscle groups, 48 exercises
├─ queries/
│  └─ scratch.sql                    ad-hoc queries, never applied automatically
└─ EzGrindDB.sql                     obsolete, kept as a pointer
```

---

## Create the database from scratch

```bash
cd EzGrind/Database

mysql -u root -p < migrations/001_baseline.sql
mysql -u root -p ezgrind_db < migrations/002_constraints_and_indexes.sql
mysql -u root -p ezgrind_db < migrations/003_new_tables.sql
mysql -u root -p ezgrind_db < migrations/004_set_comments.sql
mysql -u root -p ezgrind_db < seeds/muscle_groups_and_exercises.sql
```

`001` creates the database itself, so it is the only file that does not name
`ezgrind_db` on the command line.

Without the seed file the muscle and exercise dropdowns are empty, no workout
can be logged, and every feature downstream of exercise selection is dead. It is
not optional for a fresh install.

## Apply migrations to an existing database

**Back up first. Always.**

```bash
mysqldump -u root -p --single-transaction ezgrind_db > backup_before_002.sql
```

Then run the files you have not applied yet, in order. Each is idempotent, so
running one twice changes nothing:

```bash
mysql -u root -p ezgrind_db < migrations/002_constraints_and_indexes.sql
mysql -u root -p ezgrind_db < migrations/003_new_tables.sql
mysql -u root -p ezgrind_db < migrations/004_set_comments.sql
```

### Ordering rules

- **Numbers only go up.** Never edit a migration that has been applied
  anywhere; write a new one.
- **`002` must be applied before the backend that depends on it.**
  `Backend/repositories/workout_repo.py` uses `INSERT … ON DUPLICATE KEY UPDATE`
  against `uq_workouts_user_date`, and writes `workout_sets.set_order`. Run the
  migration first, then restart the backend. Backwards, every logged set creates
  a duplicate workout row instead of reusing the day's.
- **`002` will fail if duplicate `(user_id, workout_date)` rows exist.** Check
  before running:
  ```sql
  SELECT user_id, workout_date, COUNT(*) FROM workouts
  GROUP BY user_id, workout_date HAVING COUNT(*) > 1;
  ```
  Zero rows means it is safe.

### Why the guard blocks look like that

MySQL supports `IF NOT EXISTS` on `CREATE TABLE`, but **not** on `ADD COLUMN`,
`CREATE INDEX` or `ADD CONSTRAINT` — that is MariaDB. So `002` checks
`information_schema` and prepares either the real statement or `DO 0`. Verbose,
but it keeps the file re-runnable without leaving a stored procedure behind.

---

## Entity relationships

```
users ──1:N──> workouts ──1:N──> workout_sets ──N:1──> exercises ──N:1──> muscle_groups
  │                                                         ^
  ├──1:N──> weight_logs                                     │
  └──1:N──> personal_records ───────────N:1─────────────────┘
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

---

## Tables

### `users`
One row per account. Created at signup and never deleted by the application.
`user_id` is the surrogate key everything else hangs off. `full_name` is the
display name shown in the dashboard greeting. `email` is the login identifier
and carries a UNIQUE constraint, which is what makes duplicate-signup detection
possible. `password_hash` stores a Werkzeug scrypt hash — never a password, and
never returned by any endpoint. `created_at` stamps registration. The remaining
five columns are optional profile data collected at signup: `contact_number`
(free text, validated as ten digits by the application rather than the schema),
`date_of_birth` (the profile page derives age from it), `height_cm` and
`weight_kg` (both `FLOAT`, though the API currently accepts whole numbers only),
and `fitness_goal` (one of `gain`, `lose`, `maintain`, `muscle`, enforced only
by the signup form's `<select>` — the column itself accepts any short string).

### `muscle_groups`
Reference data, twelve rows, one per muscle image in
`Frontend/assets/muscles/`. `muscle_id` is the key exercises hang off.
`muscle_name` is the display label and is UNIQUE as of `002`, which is what lets
the seed file be re-run safely. `image_path` is a path relative to the
`Frontend/` directory, e.g. `assets/muscles/chest.png`, so it can be dropped
straight into an `<img src>`.

### `exercises`
Reference data, the movement catalogue. `exercise_id` is what a logged set
points at. `exercise_name` is the display label, UNIQUE per `muscle_id` as of
`002` so the same name can exist under two muscle groups but not twice under
one. `muscle_id` is the owning muscle group and drives the filtered dropdown on
the log-workout page. `equipment` is a short free-text label (`Barbell`,
`Dumbbell`, `Cable`, `Machine`, `Bodyweight`) shown on exercise cards.
`description` is prose explaining how the movement is performed.

### `workouts`
One row per user per training day — a container, holding no training data of its
own. `workout_id` is the parent key for sets. `user_id` is the owner, and every
application query filters on it so one account can never read another's
training. `workout_date` is the calendar day, always set to `CURDATE()` by the
application. As of `002` the pair `(user_id, workout_date)` is UNIQUE, which is
the constraint the log-a-set path had always assumed but never enforced.
`created_at` records when the day's first set was logged.

### `workout_sets`
One row per set performed — the actual training data. `set_id` is the surrogate
key. `workout_id` is the parent day; deleting that day deletes these rows.
`exercise_id` is the movement performed. `weight` is `DECIMAL(6,2)` as of `002`,
in kilograms, nullable for bodyweight movements. `reps` is
`SMALLINT UNSIGNED` as of `002` with a `CHECK (reps > 0)` — previously an `INT`
that accepted negative numbers and values in the billions.
`time_under_tension` is optional seconds under load — **no longer written**: the
input was removed from the form in `004`, but the column and its history stay,
because 21 of the 22 rows existing at that point held real values. `comments` was
added in `004`: an optional free-text note per set, capped at 500 characters and
validated at that length by the API. `created_at` was added in
`002` and backfilled from the parent workout, so historical rows carry a
plausible time rather than the migration's timestamp. `set_order` was also added
in `002`, backfilled by `set_id` within each workout; it is what makes "set 1
versus set 4" answerable, since row order in storage is an implementation
detail and not a promise.

### `weight_logs`
Bodyweight over time. Not yet read or written by any code — groundwork.
`users.weight_kg` holds only the current value and is overwritten on each
change, so it cannot answer whether someone is trending up or down, which is the
entire point of a weight goal. `log_id` is the key, `user_id` the owner,
`logged_on` the calendar day of the reading, and `weight_kg` the value in
kilograms. `created_at` records when it was entered, which may differ from the
day it describes. `(user_id, logged_on)` is UNIQUE, so a second entry on the
same day corrects the first rather than stacking — a morning of nervous
re-weighing cannot skew a trend line.

### `personal_records`
Best effort per user per exercise. Not yet read or written by any code —
groundwork. **This is a derived cache, not a source of truth.** It must always
be rebuildable from `workout_sets`; the rebuild statement lives in
`queries/scratch.sql` and is the actual definition of what belongs here. If the
table ever disagrees with the sets, the sets win. `pr_id` is the key,
`user_id` and `exercise_id` the pair it is unique on. `best_weight` and
`best_reps` record the effort itself, `estimated_1rm` the Epley projection
(`weight × (1 + reps ÷ 30)`) stored rather than computed so that changing the
formula later does not silently rewrite history. `achieved_on` is the date of
the qualifying set, tie-broken toward the earliest. `updated_at` maintains
itself.

---

## `EzGrindDB.sql`

Obsolete. It was a scratchpad that mixed table definitions, exploratory
`SELECT`s and later `ALTER` fixes into one file, so running it top to bottom
produced tables that were then patched by statements further down. Its
definitions are superseded by `migrations/001_baseline.sql`; its queries moved
to `queries/scratch.sql`. The original content remains in git history.
