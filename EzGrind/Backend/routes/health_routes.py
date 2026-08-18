"""Liveness endpoints.

Separate from the feature blueprints because these are the only routes that
must keep answering when the database is unreachable - that is the condition
they exist to report.
"""

from flask import Blueprint, current_app, jsonify

import db
from errors import error_response

bp = Blueprint("health", __name__)


@bp.get("/api/health")
def health():
    try:
        db.ping()
    except Exception:
        current_app.logger.exception("Health check could not reach the database")
        # 503 rather than 200-with-a-flag, so an uptime monitor notices without
        # being taught to read the body.
        return error_response(503, "database_unavailable", "Database is unreachable.")

    return jsonify({"data": {"status": "ok", "database": "connected"}})
