/* ============================================================
   api.js
   The only file that knows where the backend lives and what its
   envelope looks like. No other script may call fetch() directly.
   Loaded first on every page; exposes window.api and window.ApiError.
   ============================================================ */

(function () {
    "use strict";

    /* Relative, so it follows whatever origin and scheme the page was served
       from. An absolute http://127.0.0.1 base broke three ways at once: wrong
       host anywhere but this machine, blocked as mixed content on an HTTPS
       page, and cross-origin enough to need CORS and SameSite=None. */
    const API_BASE = "/api";

    /* Pages an anonymous visitor is allowed to sit on. A 401 here is
       an answer ("not signed in"), not a failure, so it must not bounce
       them to login. Everywhere else, a 401 means they took a wrong turn. */
    const PUBLIC_PAGES = new Set([
        "",
        "index.html",
        "login.html",
        "signup.html",
        "exercises.html",
        // Reached from an email, often on a device that has never signed in.
        // A 401 here must never bounce someone away from the link they came for.
        "forgot-password.html",
        "reset-password.html"
    ]);

    /* Worth retrying: the request might succeed unchanged a moment later.
       A validation failure is not on this list - retrying it fails again, and a
       Retry button that cannot work is worse than no button. */
    const RETRYABLE_STATUSES = new Set([0, 429, 500, 502, 503, 504]);

    class ApiError extends Error {
        constructor(status, code, message, field, details) {
            super(message);
            this.name = "ApiError";
            this.status = status;
            this.code = code;
            this.retryable = RETRYABLE_STATUSES.has(status);
            /* Names the request field at fault, when the server blames one.
               Lets a form attach the message to the input that caused it
               instead of guessing from the message text. */
            this.field = field || null;
            /* Every rule that failed, when one message is not enough. A
               password rejected on three counts arrives with all three, so the
               user is not made to rediscover them one submission at a time.
               Empty array on every other error, so callers can always iterate. */
            this.details = Array.isArray(details) ? details : [];
        }
    }

    function currentPage() {
        return window.location.pathname.split("/").pop() || "index.html";
    }

    function isPublicPage() {
        return PUBLIC_PAGES.has(currentPage());
    }

    async function request(path, options) {
        const { method = "GET", body, redirectOn401 = true } = options || {};
        let response;

        try {
            response = await fetch(API_BASE + path, {
                method: method,
                credentials: "include",
                headers: body === undefined
                    ? undefined
                    : { "Content-Type": "application/json" },
                body: body === undefined ? undefined : JSON.stringify(body)
            });
        } catch (networkFailure) {
            // A dead backend is indistinguishable from a CORS rejection here;
            // both leave the user with nothing, so both get one clear message.
            throw new ApiError(
                0,
                "network_error",
                "Can't reach the server — is the backend running?"
            );
        }

        let payload = {};
        try {
            payload = await response.json();
        } catch (notJson) {
            payload = {};
        }

        if (!response.ok) {
            const detail = payload.error || {};

            if (response.status === 401 && redirectOn401 && !isPublicPage()) {
                window.location.replace("login.html");
            }

            throw new ApiError(
                response.status,
                detail.code || "http_error",
                detail.message || "Something went wrong.",
                detail.field,
                detail.details
            );
        }

        return payload;
    }

    /* Resolved once per page load and shared by every caller, so the
       dashboard and the nav shell cost one /api/me between them. */
    let sessionRequest = null;

    const api = {
        ApiError: ApiError,

        get: function (path) {
            return request(path);
        },

        post: function (path, body) {
            return request(path, { method: "POST", body: body });
        },

        patch: function (path, body) {
            return request(path, { method: "PATCH", body: body });
        },

        /* DELETE carries a body here because account deletion is
           password-confirmed, and a password does not belong in a URL. */
        del: function (path, body) {
            return request(path, { method: "DELETE", body: body });
        },

        /** Resolves to the signed-in user, or null. Never redirects. */
        session: function () {
            if (!sessionRequest) {
                sessionRequest = request("/me", { redirectOn401: false })
                    .then(function (payload) { return payload.data; })
                    .catch(function (error) {
                        if (error.status === 401) return null;
                        throw error;
                    });
            }
            return sessionRequest;
        },

        /** For pages that make no sense signed out. Redirects, then resolves. */
        requireSession: async function () {
            const user = await api.session();
            if (!user) {
                window.location.replace("login.html");
            }
            return user;
        },

        /** Call after login or logout so the next session() re-fetches. */
        clearSession: function () {
            sessionRequest = null;
        }
    };

    window.api = api;
    window.ApiError = ApiError;
})();
