"""HTTP layer. Route modules parse the request, validate, call a repository and
serialise the result. No SQL below this package boundary.

Success bodies follow one shape:
    collection -> {"data": [...]}
    object     -> {"data": {...}}
    mutation   -> {"data": {...}, "message": "..."}
"""
