"""Queries against the reference tables: muscle_groups and exercises."""

import re

from db import get_cursor

# muscle_name and image_path live on muscle_groups, but every exercise card
# renders them. Joining here beats making the client fetch both tables and
# stitch them together.
_EXERCISE_FIELDS = """
    e.exercise_id, e.exercise_name, e.equipment, e.description,
    e.exercise_type, e.difficulty_level, e.rating,
    m.muscle_id, m.muscle_name, m.image_path
"""

PAGE_DEFAULT = 24
PAGE_MAX = 100

# Each sort names the ORDER BY and the two columns that carry the cursor. Both
# pairs are a total order, which is what makes keyset paging safe:
# (exercise_name, muscle_id) is unique per uq_exercises_name_muscle, and
# muscle_name maps one-to-one onto muscle_id so the reverse pair is unique too.
#
# Each has an index built to match it exactly - idx_exercises_name_muscle and
# idx_exercises_muscle_name - because the keyset comparison is only a seek if
# the leading column of the index is the leading column of the ORDER BY.
#
# Whitelist, not interpolation: the sort key reaches SQL as a fixed column list,
# so it can never come straight from a query string.
_SORT_SPECS = {
    "name": {
        "order": "e.exercise_name, e.muscle_id",
        "columns": ("e.exercise_name", "e.muscle_id"),
        "keys": ("exercise_name", "muscle_id"),
    },
    # Ordered by muscle_id, not muscle_name. The ids are curated in training
    # order (Chest, Lats, Upper Back, ... Core), which is a more useful
    # grouping than alphabetical - and it is the indexed column, so sorting by
    # the name instead would mean a sort node over the whole catalogue.
    "muscle": {
        "order": "e.muscle_id, e.exercise_name",
        "columns": ("e.muscle_id", "e.exercise_name"),
        "keys": ("muscle_id", "exercise_name"),
    },
}


def _keyset_clause(columns, after, params):
    """"Everything after this row", written so the planner can seek to it.

    Spelled out as `a > x OR (a = x AND b > y)` rather than the row comparison
    `(a, b) > (x, y)`. Both mean the same thing; the expanded form is the one
    that reliably becomes an index range scan. Measured on MySQL at 2,924 rows,
    paging to the far end, it was the only shape flat with depth:

        LIMIT/OFFSET          23.2 ms   full scan + filesort
        (a, b) > (x, y)        9.5 ms   index scan from the front
        a > x OR (a = x AND)   2.0 ms   seek

    Those numbers are MySQL's and are kept as the reason this shape exists, not
    as a claim about Postgres. scripts/check_plans.py re-measures on the real
    database and asserts the seek is still a seek.

    SAFE ONLY BECAUSE exercises.exercise_name IS COLLATE "C". The `>` here has
    to agree with the collation of the index behind the ORDER BY, or the seek
    lands in the wrong place and Load-more silently skips or repeats rows.
    Pinning the column removes the chance of disagreement.
    """
    first, second = columns
    params.extend([after[0], after[0], after[1]])
    return f"({first} > %s OR ({first} = %s AND {second} > %s))"


def _escape_like(text):
    """Neutralise LIKE wildcards so a search for "50%" means those characters.

    Postgres uses backslash as the default LIKE/ILIKE escape, same as MySQL, so
    the doubling below means the same thing to both.
    """
    return (text.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_"))


def _search_terms(query):
    """User text -> the substrings every match must contain.

    Split on anything that is not a word character, so "bench pr" becomes
    ["bench", "pr"] and a name must contain both to match. That is what makes
    type-ahead work: two partial words find "Bench Press" without either being
    typed in full.

    MySQL needed a whole boolean-mode expression here (`+bench* +pr*`), plus a
    rule discarding tokens under three characters because InnoDB's tokeniser
    ignored them and a required term that can never match returns nothing.
    Trigrams have no tokeniser and no minimum, so both rules are gone.

    Returns [] when the input has no word characters at all - a lone "%" or
    "-". The caller then matches the whole escaped string instead, so searching
    for "%" looks for a literal percent sign and finds nothing, rather than
    dropping the filter and returning all 2,900 rows.
    """
    return re.findall(r"[A-Za-z0-9]+", query)


def list_muscles():
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT muscle_id, muscle_name, image_path FROM muscle_groups"
            " ORDER BY muscle_id"
        )
        return cursor.fetchall()


def _distinct(column):
    """The values actually in use, for a filter control.

    Derived from the data rather than a hardcoded list, so a filter cannot
    drift out of step with the catalogue.
    """
    with get_cursor() as cursor:
        cursor.execute(f"""
            SELECT DISTINCT {column} AS value
            FROM exercises
            WHERE {column} IS NOT NULL AND {column} <> ''
            ORDER BY {column}
        """)
        return [row["value"] for row in cursor.fetchall()]


def distinct_equipment():
    return _distinct("equipment")


def distinct_difficulties():
    return _distinct("difficulty_level")


def distinct_types():
    return _distinct("exercise_type")


def filter_options():
    """Everything the filter bar needs, in one round trip instead of four."""
    return {
        "muscles": list_muscles(),
        "equipment": distinct_equipment(),
        "difficulties": distinct_difficulties(),
        "types": distinct_types(),
    }


def _build_filters(muscle_ids, query, equipment, difficulty, exercise_type):
    """The WHERE fragments and their parameters, in matching order."""
    where, params = [], []

    if muscle_ids:
        placeholders = ", ".join(["%s"] * len(muscle_ids))
        where.append(f"e.muscle_id IN ({placeholders})")
        params.extend(muscle_ids)

    if query:
        # ILIKE, not LIKE. MySQL's collation made LIKE case-insensitive for
        # free; Postgres does not, and a plain LIKE here would simply stop
        # matching for anyone who types in lowercase - no error, just an empty
        # picker. ILIKE is served by idx_exercises_name_trgm because pg_trgm
        # lowercases the trigrams it extracts.
        #
        # Infix rather than anchored, which the trigram index makes affordable:
        # "squat" now finds "Barbell Squat". The old anchored fallback could
        # not, and that was the single most annoying thing about the picker.
        for term in _search_terms(query) or [query]:
            where.append("e.exercise_name ILIKE %s")
            params.append("%" + _escape_like(term) + "%")

    for column, value in (("e.equipment", equipment),
                          ("e.difficulty_level", difficulty),
                          ("e.exercise_type", exercise_type)):
        if value:
            where.append(f"{column} = %s")
            params.append(value)

    return where, params


def list_exercises(muscle_ids=None, query=None, equipment=None, difficulty=None,
                   exercise_type=None, sort="name", limit=PAGE_DEFAULT,
                   after=None):
    """One page of the catalogue, plus the cursor for the next one.

    Keyset paging, not OFFSET. `LIMIT 24 OFFSET 2400` has to build and discard
    the 2,400 rows being skipped whichever database runs it - on MySQL that
    measured as a full scan plus filesort at 17.6ms. Asking for "the rows after
    this one" instead keeps every page on the same index range scan as page 1,
    at a cost that does not grow with depth.

    `after` is the (name, muscle_id) pair from the last row of the previous
    page - whatever the caller was handed as `next`. Returns (rows, next).
    """
    spec = _SORT_SPECS.get(sort) or _SORT_SPECS["name"]
    where, params = _build_filters(
        muscle_ids, query, equipment, difficulty, exercise_type
    )

    if after:
        where.append(_keyset_clause(spec["columns"], after, params))

    clause = ("WHERE " + " AND ".join(where)) if where else ""

    # One extra row answers "is there another page" without a second query.
    params.append(limit + 1)

    with get_cursor() as cursor:
        cursor.execute(f"""
            SELECT {_EXERCISE_FIELDS}
            FROM exercises e
            JOIN muscle_groups m ON m.muscle_id = e.muscle_id
            {clause}
            ORDER BY {spec['order']}
            LIMIT %s
        """, params)
        rows = cursor.fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = (
        [rows[-1][spec["keys"][0]], rows[-1][spec["keys"][1]]]
        if has_more and rows else None
    )
    return rows, next_cursor


def count_exercises(muscle_ids=None, query=None, equipment=None,
                    difficulty=None, exercise_type=None):
    """Total matches, for the "N exercises" line above the grid.

    Separate from list_exercises because it is only worth running on the first
    page - "Load more" does not need the total recomputed on every append.
    """
    where, params = _build_filters(
        muscle_ids, query, equipment, difficulty, exercise_type
    )
    clause = ("WHERE " + " AND ".join(where)) if where else ""

    with get_cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) AS total FROM exercises e {clause}",
                       params)
        return cursor.fetchone()["total"]


def find_detail(exercise_id):
    """One exercise with its muscle group, or None."""
    with get_cursor() as cursor:
        cursor.execute(f"""
            SELECT {_EXERCISE_FIELDS}
            FROM exercises e
            JOIN muscle_groups m ON m.muscle_id = e.muscle_id
            WHERE e.exercise_id = %s
        """, (exercise_id,))
        return cursor.fetchone()
