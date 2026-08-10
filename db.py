"""Database access: one pooled connection per process, handed out per request.

Two responsibilities, both about resources rather than data. First, reuse
connections - the previous code paid a TCP connect and auth handshake on every
single API call. Second, guarantee release: callers cannot be trusted to close
across early returns or exceptions, so the only way to get a connection is a
context manager that closes in a finally block.

No SQL lives here. Repositories own the queries.
"""

import threading
from contextlib import contextmanager

from mysql.connector import pooling

import config

_pool = None
_pool_lock = threading.Lock()


def _get_pool():
    """Built on first use, not at import.

    Creating the pool eagerly would make importing this module fail whenever
    MySQL is down, which would take the whole app with it - including
    /api/health, the one endpoint whose job is to report that the database is
    down.
    """
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = pooling.MySQLConnectionPool(
                pool_name="ezgrind",
                pool_size=config.DB_POOL_SIZE,
                pool_reset_session=True,
                **config.DB_CONFIG,
            )
    return _pool


@contextmanager
def get_connection():
    conn = _get_pool().get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        # Returns the connection to the pool; it does not close the socket.
        conn.close()


@contextmanager
def get_cursor(dictionary=True):
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=dictionary)
        try:
            yield cursor
        finally:
            cursor.close()


def ping():
    """Cheapest round-trip that proves the database answers. Raises if not."""
    with get_cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchall()
