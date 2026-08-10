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

# InnoDB ignores full-text tokens shorter than innodb_ft_min_token_size, whose
# default is 3. A two-character search would silently match nothing, so it goes
# down the LIKE path instead.
_MIN_FT_TOKEN = 3

PAGE_DEFAULT = 24
PAGE_MAX = 100

# Each sort names the ORDER BY and the two columns that carry the cursor. Both
# pairs are a total order, which is what makes keyset paging safe: "name" is the
# UNIQUE index uq_exercises_name_muscle, and muscle_name maps one-to-one onto
# muscle_id, so (muscle_name, exercise_name) is unique too.
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
    # grouping than alphabetical - and it is the column that carries an index,
    # so sorting by the name instead cost a temporary table and a filesort.
    "muscle": {
        "order": "e.muscle_id, e.exercise_name",
        "columns": ("e.muscle_id", "e.exercise_name"),
        "keys": ("muscle_id", "exercise_name"),
    },
}


def _keyset_clause(columns, after, params):
    """"Everything after this row", written so MySQL can seek to it.

    Spelled out as `a > x OR (a = x AND b > y)` rather than the row comparison
    `(a, b) > (x, y)`, which reads better and means the same thing but is not
    optimised the same way. Measured on this table at 2,924 rows, paging to the
    far end:

        LIMIT/OFFSET          23.2 ms   type=ALL    (full scan + filesort)
        (a, b) > (x, y)        9.5 ms   type=index  (scans from the front)
        a > x OR (a = x AND)   2.0 ms   type=range  (seeks)

    Only the third is flat with depth - the first two still walk every row
    being skipped, they just walk it differently. The seek is what makes
    "Load more" cost the same on page 120 as on page 1.
    """
    first, second = columns
    params.extend([after[0], after[0], after[1]])
    return f"({first} > %s OR ({first} = %s AND {second} > %s))"


def _escape_like(text):
    """Neutralise LIKE wildcards so a search for "50%" means those characters."""
    return (text.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_"))


def _boolean_terms(query):
    """User text -> a safe IN BOOLEAN MODE expression, or "" to use LIKE.

    Only word characters survive. The boolean parser treats +-><()~*"@ as
    operators, so passing raw input through would let a stray "(" raise a
    syntax error from inside the search box - and would hand the user a query
    language nobody asked for.

    Tokens become required prefixes (`+bench* +pr*`), which is what makes
    type-ahead work: "bench pr" finds "Bench Press". Tokens below the minimum
    length are dropped rather than required, since InnoDB would ignore them and
    a required term that can never match returns nothing at all.
    """
    tokens = [word for word in re.findall(r"[A-Za-z0-9]+", query)
              if len(word) >= _MIN_FT_TOKEN]
    return " ".join("+" + token + "*" for token in tokens)


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
        terms = _boolean_terms(query)
        if terms:
            where.append("MATCH(e.exercise_name) AGAINST (%s IN BOOLEAN MODE)")
            params.append(terms)
        else:
            # Too short to tokenise. Anchored rather than %infix%, so it stays a
            # range scan on the name index instead of reading all 2,900 rows.
            where.append("e.exercise_name LIKE %s")
            params.append(_escape_like(query) + "%")

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

    Keyset paging, not OFFSET. At 2,924 rows `LIMIT 24 OFFSET 2400` makes MySQL
    abandon the index and full-scan with a filesort (measured: type=ALL, 17.6ms)
    because it must build and discard the 2,400 rows being skipped. Asking for
    "the rows after this one" instead keeps every page on the same index range
    scan as page 1, at a cost that does not grow with depth.

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
