"""Database access: one pooled connection per process, handed out per request.

Two responsibilities, both about resources rather than data. First, reuse
connections - the previous code paid a TCP connect and auth handshake on every
single API call, and against a hosted Postgres that also means a TLS handshake.
Second, guarantee release: callers cannot be trusted to close across early
returns or exceptions, so the only way to get a connection is a context manager
that closes in a finally block.

No SQL lives here. Repositories own the queries.
"""

import threading
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool as pg_pool
from psycopg2.extras import RealDictCursor

import config

_pool = None
_pool_lock = threading.Lock()

# "This particular socket is dead", as opposed to "that query was wrong".
# Neon scales its compute to zero after a few minutes idle and drops everything
# it was holding, so a pooled connection that worked five minutes ago is
# routinely one of these on its next use. That is normal operation on a
# serverless database, not an error worth surfacing.
_DEAD_CONNECTION = (psycopg2.OperationalError, psycopg2.InterfaceError)


def _get_pool():
    """Built on first use, not at import.

    Creating the pool eagerly would make importing this module fail whenever
    the database is unreachable, which would take the whole app with it -
    including /api/health, the one endpoint whose job is to report that the
    database is down.

    minconn=1 rather than the full pool size: opening five connections at boot
    would wake Neon's compute just to hold sockets nobody has asked for yet.
    """
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = pg_pool.ThreadedConnectionPool(
                1,
                config.DB_POOL_SIZE,
                config.DATABASE_URL,
                connect_timeout=10,
                # Without keepalives a connection idling behind a NAT or a load
                # balancer is silently dropped and nobody finds out until the
                # next write blocks for the full TCP timeout.
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=3,
                application_name="ezgrind",
            )
    return _pool


def _healthy_connection():
    """A pooled connection that has been proven to still answer.

    ThreadedConnectionPool hands back whatever it is holding without checking
    it. Against Neon that is not good enough: when the compute resumes from
    zero, every connection cached before the pause is dead, and the first
    request after an idle period would raise OperationalError from inside a
    route rather than paying a one-off reconnect.

    So: take one, prove it, and if it is dead discard it with close=True - the
    pool then forgets it instead of filing a corpse back on the shelf - and
    take another. getconn() opens a fresh socket when the pool is empty, which
    is what makes this a reconnect rather than a failure.

    ONE retry, not a loop. Two dead connections in a row means the database is
    genuinely down, and that belongs in /api/health as a 503, not in a spin.

    ponytail: pings on every checkout, so each request pays one extra round
    trip. Upgrade path if that ever shows up in a latency graph is to stamp
    each connection with its last-used time and skip the ping below ~60s idle.
    """
    pool = _get_pool()

    for attempt in (1, 2):
        conn = pool.getconn()
        try:
            if conn.closed:
                raise psycopg2.InterfaceError("connection was already closed")
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
            # The ping opened a transaction. Leaving it open would make the
            # caller's first statement run inside a transaction that started
            # before their work did.
            conn.rollback()
            return conn
        except _DEAD_CONNECTION:
            pool.putconn(conn, close=True)
            if attempt == 2:
                raise


@contextmanager
def get_connection():
    conn = _healthy_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        # A connection that died mid-transaction cannot be rolled back, and
        # attempting it raises a second exception that would mask the first -
        # so the caller would see "connection closed" instead of the error
        # that actually broke their request.
        if not conn.closed:
            try:
                conn.rollback()
            except _DEAD_CONNECTION:
                pass
        raise
    finally:
        # Returns the connection to the pool; it does not close the socket.
        # putconn discards it instead when the transaction status says the
        # server connection was lost.
        _get_pool().putconn(conn)


@contextmanager
def get_cursor(dictionary=True):
    """Same signature it had under MySQL, so no caller changed.

    dictionary=True yields RealDictCursor rows, which are dicts and support
    row["column"] exactly as mysql-connector's dictionary cursor did.
    dictionary=False yields tuples, for the callers that index by position.
    """
    with get_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor if dictionary else None)
        try:
            yield cursor
        finally:
            cursor.close()


def ping():
    """Cheapest round-trip that proves the database answers. Raises if not."""
    with get_cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchall()
