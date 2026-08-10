"""Application factory: build the app, wire the extensions, register blueprints.

Nothing else belongs in this file. Routes live in routes/, SQL in repositories/,
configuration in config.py. If this module grows a query or a request handler,
it is in the wrong place.
"""

from pathlib import Path

from flask import Flask, send_from_directory
from flask_cors import CORS
from werkzeug.routing import PathConverter

import cli
import config

# Flask serves the frontend itself, so the app is ONE origin. That removes
# three problems at once rather than fixing each: no hardcoded API host, no
# mixed content on HTTPS, and no cross-site cookie for SameSite to worry about.
FRONTEND = Path(__file__).resolve().parents[1] / "Frontend"


class StaticPath(PathConverter):
    """Any path EXCEPT one under /api.

    The exclusion is done in the routing regex rather than with an early return
    in the view, so Werkzeug never even considers the static rule for an API
    path. Matching it and then aborting would turn "GET on a POST-only route"
    from a 405 into a 404 - a real regression, because the frontend's error
    handling distinguishes them.
    """

    regex = r"(?!api(?:/|$))[^/].*?"
from auth import limiter
from errors import register_error_handlers
from routes.auth_routes import bp as auth_bp
from routes.exercise_routes import bp as exercise_bp
from routes.health_routes import bp as health_bp
from routes.profile_routes import bp as profile_bp
from routes.stats_routes import bp as stats_bp
from routes.weight_routes import bp as weight_bp
from routes.workout_routes import bp as workout_bp
from services import email_service

API_BLUEPRINTS = (auth_bp, profile_bp, workout_bp, exercise_bp, stats_bp, weight_bp)


def create_app():
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY

    app.config.update(
        SESSION_COOKIE_HTTPONLY=config.SESSION_COOKIE_HTTPONLY,
        SESSION_COOKIE_SAMESITE=config.SESSION_COOKIE_SAMESITE,
        SESSION_COOKIE_SECURE=config.SESSION_COOKIE_SECURE,
        PERMANENT_SESSION_LIFETIME=config.PERMANENT_SESSION_LIFETIME,
    )

    # Credentialed requests cannot use a wildcard origin - browsers reject the
    # combination outright, so the allow-list is what makes cookies work at all.
    CORS(
        app,
        supports_credentials=True,
        resources={r"/api/*": {"origins": config.ALLOWED_ORIGINS}},
    )

    limiter.init_app(app)
    register_error_handlers(app)

    for blueprint in API_BLUEPRINTS:
        app.register_blueprint(blueprint, url_prefix="/api")
    app.register_blueprint(health_bp)

    app.url_map.converters["static_path"] = StaticPath

    @app.get("/")
    def index():
        return send_from_directory(FRONTEND, "index.html")

    @app.get("/<static_path:filename>")
    def frontend(filename):
        """Serve the frontend. The converter keeps /api out of this entirely.

        In production put nginx in front of this - it serves static files far
        better than Flask does. This exists so development and production have
        the same single-origin shape, which is what stopped the API base URL
        having to be hardcoded.
        """
        return send_from_directory(FRONTEND, filename)

    cli.register(app)

    # Warn at boot rather than on the first signup. A missing API key should be
    # discovered while starting the server, not by a user who never got their
    # welcome email. Warns only: email being misconfigured is not a reason for
    # the workout log to be down.
    email_service.warn_if_unconfigured()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=config.DEBUG)
