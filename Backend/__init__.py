"""Data access. Every SQL statement in the application lives under this package.

Repositories return plain dicts, lists and None. They raise no ApiError, read no
session, and know nothing about status codes - so they stay usable from a
script, a migration or a test, not just from a request.
"""
