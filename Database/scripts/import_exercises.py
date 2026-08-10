"""Import the megaGym exercise dataset into ezgrind_db.exercises.

    python import_exercises.py "D:\\megaGymDataset.csv" --dry-run
    python import_exercises.py "D:\\megaGymDataset.csv"

Safe to run twice. Everything is keyed on uq_exercises_name_muscle
(exercise_name, muscle_id), added by migration 002, so a second run updates in
place rather than duplicating. No exercise_id is ever reassigned - workout_sets
rows keep pointing at the exercises they were logged against.

CONFLICT POLICY
    Where a row already exists, the stored value wins and the CSV may only fill
    a blank. The 24 hand-written rows are the only curated content in the
    catalogue; 2,900 imported rows do not get to overrule them. In practice
    that protects the description on "Hanging Leg Raises" (absent from the CSV)
    and the equipment on "Standing Calf Raise" (Machine here, "Body Only"
    there).

REQUIRES migration 005 to have been applied.
"""

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Backend"))

from db import get_cursor  # noqa: E402

BATCH_SIZE = 500
RATING_CEILING = 9.99          # DECIMAL(3,2) cannot hold 10.00
NAME_MAX = 100                 # exercise_name VARCHAR(100)

# Source BodyPart -> muscle_groups.muscle_id.
# Middle Back and Traps both land in 3 ("Upper Back"), confirmed deliberate.
# 13-16 are created by migration 005.
BODYPART_TO_MUSCLE = {
    "Abdominals": 12, "Quadriceps": 7, "Shoulders": 11, "Chest": 1,
    "Biceps": 5, "Triceps": 6, "Lats": 2, "Hamstrings": 8,
    "Middle Back": 3, "Lower Back": 4, "Glutes": 9, "Calves": 10,
    "Traps": 3, "Forearms": 13, "Abductors": 14, "Adductors": 15, "Neck": 16,
}

# The source labels differ from the ones the existing 24 rows use. Left
# unmapped, the equipment filter would fragment into near-duplicate options.
# "None" is a literal string in this dataset, not a null - 32 rows carry it.
EQUIPMENT_MAP = {
    "Body Only": "Bodyweight",
    "Kettlebells": "Kettlebell",
    "E-Z Curl Bar": "EZ Bar",
    "Bands": "Resistance Band",
    "Foam Roll": "Foam Roller",
    "Exercise Ball": "Stability Ball",
    "Medicine Ball": "Medicine Ball",
    "Other": "Other",
    "None": "Other",
    "": "Other",
}

# Lowercased inside a title, capitalised when they lead it.
MINOR_WORDS = {"a", "an", "and", "as", "at", "for", "in", "of", "on", "or",
               "the", "to", "with", "vs"}


# ============================================================
# CLEANING
# ============================================================

def title_case(raw):
    """Consistent casing that leaves acronyms alone.

    The source mixes "Crunch" with "FYR Banded Plank Jack" and "dumbbell
    step-up". A blanket .title() would turn FYR into Fyr and EZ into Ez, so any
    run of two or more capitals is passed through untouched. Hyphenated words
    are cased part by part, giving "Step-Up" rather than "Step-up".
    """
    text = re.sub(r"\s+", " ", raw.strip())
    if not text:
        return ""

    words = []
    for index, word in enumerate(text.split(" ")):
        parts = []
        for part in word.split("-"):
            if not part:
                parts.append(part)
            elif part.isupper() and len(part) >= 2:
                parts.append(part)
            elif index > 0 and part.lower() in MINOR_WORDS:
                parts.append(part.lower())
            else:
                parts.append(part[:1].upper() + part[1:].lower())
        words.append("-".join(parts))

    first = words[0]
    if not (first.isupper() and len(first) >= 2):
        words[0] = first[:1].upper() + first[1:]
    return " ".join(words)


def clean_text(value):
    """Trimmed and whitespace-collapsed, or None. Never an empty string."""
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value.strip())
    return text or None


def clean_rating(value):
    """0 to 9.99, or None. No invented values."""
    text = (value or "").strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return round(min(max(number, 0.0), RATING_CEILING), 2)


def read_rows(csv_path):
    """Parse the CSV, drop the junk columns, clean and map every field.

    The index column has an empty-string header (pandas renders it as
    "Unnamed: 0"); RatingDesc is 70% empty and carries nothing the rating does
    not. Both are dropped by simply never being read.
    """
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        raw_rows = list(csv.DictReader(handle))

    prepared, skipped = [], collections.Counter()

    for raw in raw_rows:
        name = title_case(raw.get("Title") or "")
        body_part = (raw.get("BodyPart") or "").strip()

        if not name:
            skipped["blank title"] += 1
            continue
        if len(name) > NAME_MAX:
            skipped[f"name longer than {NAME_MAX} chars"] += 1
            continue
        if body_part not in BODYPART_TO_MUSCLE:
            skipped[f"unmapped BodyPart: {body_part!r}"] += 1
            continue

        equipment_raw = (raw.get("Equipment") or "").strip()

        prepared.append({
            "exercise_name": name,
            "muscle_id": BODYPART_TO_MUSCLE[body_part],
            "equipment": EQUIPMENT_MAP.get(equipment_raw, equipment_raw),
            "description": clean_text(raw.get("Desc")),
            "exercise_type": clean_text(raw.get("Type")),
            "difficulty_level": clean_text(raw.get("Level")),
            "rating": clean_rating(raw.get("Rating")),
        })

    return raw_rows, prepared, skipped


def deduplicate(rows, skipped):
    """One row per (name, muscle_id), compared case-insensitively.

    Case-insensitively because the column collation is utf8mb4_0900_ai_ci:
    "Arnold press" and "Arnold Press" are the same key to MySQL, and a
    case-sensitive dedup would leave a pair that aborts the batch.

    Keyed on the MAPPED muscle_id rather than on BodyPart, because Middle Back
    and Traps both resolve to 3 - deduping on BodyPart would let two rows
    through that collide on the unique index.

    A row carrying a description beats one without.
    """
    best = {}
    for row in rows:
        key = (row["exercise_name"].lower(), row["muscle_id"])
        held = best.get(key)
        if held is None:
            best[key] = row
        else:
            skipped["duplicate name within the CSV"] += 1
            if held["description"] is None and row["description"] is not None:
                best[key] = row
    return list(best.values())


# ============================================================
# DATABASE
# ============================================================

INSERT_SQL = """
    INSERT INTO exercises
        (exercise_name, muscle_id, equipment, description,
         exercise_type, difficulty_level, rating)
    VALUES {placeholders} AS new
    ON DUPLICATE KEY UPDATE
        equipment        = COALESCE(exercises.equipment,        new.equipment),
        description      = COALESCE(exercises.description,      new.description),
        exercise_type    = COALESCE(exercises.exercise_type,    new.exercise_type),
        difficulty_level = COALESCE(exercises.difficulty_level, new.difficulty_level),
        rating           = COALESCE(exercises.rating,           new.rating)
"""

COLUMNS = ("exercise_name", "muscle_id", "equipment", "description",
           "exercise_type", "difficulty_level", "rating")


def existing_keys():
    with get_cursor() as cursor:
        cursor.execute("SELECT exercise_name, muscle_id FROM exercises")
        return {(r["exercise_name"].lower(), r["muscle_id"])
                for r in cursor.fetchall()}


def require_migration():
    """Fail early and clearly rather than mid-batch on an unknown column."""
    with get_cursor() as cursor:
        cursor.execute("SHOW COLUMNS FROM exercises")
        columns = {row["Field"] for row in cursor.fetchall()}

    missing = {"exercise_type", "difficulty_level", "rating"} - columns
    if missing:
        sys.exit(
            f"exercises is missing {', '.join(sorted(missing))}.\n"
            f"Apply migration 005 first:\n"
            f"  mysql -u root -p ezgrind_db < ../migrations/005_exercise_metadata.sql"
        )


def write_rows(rows):
    """All batches share one transaction, so a failure leaves nothing behind."""
    with get_cursor(dictionary=False) as cursor:
        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start:start + BATCH_SIZE]
            placeholders = ", ".join(["(%s, %s, %s, %s, %s, %s, %s)"] * len(batch))
            params = [row[column] for row in batch for column in COLUMNS]
            cursor.execute(INSERT_SQL.format(placeholders=placeholders), params)
            print(f"    batch {start // BATCH_SIZE + 1}: {len(batch)} rows")


def group_counts():
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT m.muscle_id, m.muscle_name, COUNT(e.exercise_id) AS total
            FROM muscle_groups m
            LEFT JOIN exercises e ON e.muscle_id = m.muscle_id
            GROUP BY m.muscle_id, m.muscle_name
            ORDER BY m.muscle_id
        """)
        return cursor.fetchall()


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Import exercises from a CSV.")
    parser.add_argument("csv_path", help="path to megaGymDataset.csv")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would happen and write nothing")
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        sys.exit(f"no such file: {csv_path}")

    require_migration()

    raw_rows, prepared, skipped = read_rows(csv_path)
    rows = deduplicate(prepared, skipped)

    known = existing_keys()
    to_update = [r for r in rows if (r["exercise_name"].lower(), r["muscle_id"]) in known]
    to_insert = [r for r in rows if (r["exercise_name"].lower(), r["muscle_id"]) not in known]

    print(f"\n{'DRY RUN - nothing will be written' if args.dry_run else 'IMPORT'}")
    print("=" * 62)
    print(f"  rows read from CSV            {len(raw_rows):>6}")
    for reason, count in sorted(skipped.items()):
        print(f"  skipped: {reason:<22} {count:>6}")
    print(f"  unique (name, muscle) keys    {len(rows):>6}")
    print(f"  would insert                  {len(to_insert):>6}")
    print(f"  would update in place         {len(to_update):>6}")

    print("\n  equipment values after normalisation:")
    for value, count in sorted(collections.Counter(
            r["equipment"] for r in rows).items()):
        print(f"    {value:<18} {count:>6}")

    if to_update:
        print("\n  updating in place (stored values are preserved, blanks filled):")
        for row in sorted(to_update, key=lambda r: r["exercise_name"]):
            print(f"    {row['exercise_name']}")

    if args.dry_run:
        print("\n  nothing written. Re-run without --dry-run to apply.")
        return

    print(f"\n  writing in batches of {BATCH_SIZE}:")
    write_rows(rows)

    print("\n  final count per muscle group:")
    total = 0
    for group in group_counts():
        total += group["total"]
        print(f"    {group['muscle_id']:>3}  {group['muscle_name']:<14} {group['total']:>6}")
    print(f"    {'':>3}  {'TOTAL':<14} {total:>6}")


if __name__ == "__main__":
    main()
