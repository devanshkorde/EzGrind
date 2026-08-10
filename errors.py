"""The API's error contract: every failure is JSON shaped
{"error": {"code": "...", "message": "..."}}.

Werkzeug's HTML error pages break every `fetch().then(res => res.json())` in the
frontend twice over - the parse throws, and the throw lands in a promise with no
.catch(). Nothing routed through this module may ever return HTML.

Field validation lives in validators.py; this module only defines the failure
type and serialises it.
"""

from flask import jsonify, request
from werkzeug.exceptions import HTTPException


class ApiError(Exception):
    """Raise from anywhere in a request to produce a contract-shaped failure.

    `field` names the request field at fault, when one is to blame. It lets a
    form attach the message to the input that caused it instead of guessing
    from the message text.
    """

    def __init__(self, status, code, message, field=None, details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.field = field
        self.details = details


def error_response(status, code, message, field=None, details=None):
    error = {"code": code, "message": message}
    # Omitted rather than null when absent, so responses that blame no
    # particular field keep exactly the shape they had before.
    if field:
        error["field"] = field
    # A list of every rule that failed, for cases where one message is not
    # enough - a password rejected on three counts should say all three rather
    # than making the user rediscover them one submission at a time. Absent on
    # every other error, so nothing that reads this contract has to change.
    if details:
        error["details"] = list(details)
    return jsonify({"error": error}), status


_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    415: "unsupported_media_type",
    429: "rate_limited",
}

# Human copy for the statuses Werkzeug raises itself. Its descriptions are
# written for developers - "The method is not allowed for the requested URL" -
# and Flask-Limiter's 429 description is the raw rule, "10 per 1 minute".
# Replaced here rather than in the browser so every client gets it, and no
# future client has to repeat the same patch.
#
# Errors we raise ourselves travel as ApiError and keep their own wording; only
# framework-raised HTTPExceptions land here.
_HTTP_MESSAGES = {
    400: "That request wasn't valid.",
    401: "Please sign in to continue.",
    # Unreachable today: every ownership failure in this app answers 404 so the
    # endpoint cannot be used to discover which ids exist.
    403: "You don't have access to that.",
    404: "We couldn't find that.",
    405: "That action isn't allowed here.",
    415: "That request format isn't supported.",
    429: "Too many attempts. Wait a minute, then try again.",
}
_HTTP_FALLBACK = "Something went wrong with that request."


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(exc):
        return error_response(exc.status, exc.code, exc.message, exc.field,
                              exc.details)

    @app.errorhandler(HTTPException)
    def handle_http_error(exc):
        # exc.description is deliberately discarded: it is framework text, and
        # it is what used to leak "If you entered the URL manually please check
        # your spelling" into the UI.
        return error_response(
            exc.code,
            _HTTP_CODES.get(exc.code, "http_error"),
            _HTTP_MESSAGES.get(exc.code, _HTTP_FALLBACK),
        )

    @app.errorhandler(Exception)
    def handle_unexpected(exc):
        # Full detail to the server log, nothing to the client: exception text
        # leaks queries, file paths and connection strings.
        app.logger.exception("Unhandled exception on %s %s", request.method, request.path)
        return error_response(500, "internal_error", "An unexpected error occurred.")
