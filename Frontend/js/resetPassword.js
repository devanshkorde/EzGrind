/* Reset password - validate the link on load, then set a new password.

   Public page, reached from an email. The token is read from the query string
   and checked BEFORE the form is shown, so somebody holding a dead link finds
   out immediately rather than after choosing a password and typing it twice.
*/

(function () {
    "use strict";

    const DEAD_COPY = {
        expired: {
            icon: "⏳",
            title: "That link has expired",
            body: "Reset links last 20 minutes. Request a new one and it'll " +
                  "arrive in a moment."
        },
        used: {
            icon: "✓",
            title: "That link has already been used",
            body: "Each link works once. If you've already reset your " +
                  "password, just log in — otherwise request a new link."
        },
        invalid: {
            icon: "✕",
            title: "That link isn't valid",
            body: "It may have been cut short by your email app. Copy the " +
                  "whole address from the email, or request a new link."
        }
    };

    const el = {};
    let token = null;

    function cache() {
        ["resetChecking", "resetDead", "resetDeadTitle", "resetDeadBody",
         "resetForm", "resetPasswordForm", "resetDone", "new_password",
         "confirm_password", "formError", "resetBtn"].forEach(function (id) {
            el[id] = document.getElementById(id);
        });
    }

    function show(which) {
        ["resetChecking", "resetDead", "resetForm", "resetDone"]
            .forEach(function (id) { el[id].hidden = id !== which; });
    }

    function showDead(status) {
        const copy = DEAD_COPY[status] || DEAD_COPY.invalid;
        el.resetDead.querySelector(".empty-state__icon").textContent = copy.icon;
        el.resetDeadTitle.textContent = copy.title;
        el.resetDeadBody.textContent = copy.body;
        document.title = "EzGrind | " + copy.title;
        show("resetDead");
    }

    /* Checked on load, not on submit. This is the whole reason the validate
       endpoint exists - and it does not consume the token, so a valid link
       survives being looked at. */
    async function validateToken() {
        token = new URLSearchParams(window.location.search).get("token");

        if (!token) {
            showDead("invalid");
            return;
        }

        try {
            const payload = await window.api.get(
                "/reset-password/validate?token=" + encodeURIComponent(token));

            if (payload.data.valid) {
                show("resetForm");
                el.new_password.focus();
            } else {
                showDead(payload.data.status);
            }
        } catch (error) {
            // A network or rate-limit failure is not the same as a dead link,
            // so it must not be reported as one.
            el.resetDeadTitle.textContent = "Could not check that link";
            el.resetDeadBody.textContent = error.message;
            el.resetDead.querySelector(".empty-state__icon").textContent = "⚠";
            show("resetDead");
        }
    }

    async function submit(event) {
        event.preventDefault();
        window.ui.clearFieldErrors(el.resetPasswordForm);
        el.formError.textContent = "";

        if (el.new_password.value !== el.confirm_password.value) {
            window.ui.setFieldError("confirm_password", "Passwords do not match.");
            return;
        }

        window.ui.setLoading(el.resetBtn, true);
        try {
            await window.api.post("/reset-password", {
                token: token,
                new_password: el.new_password.value
            });
            show("resetDone");
            document.title = "EzGrind | Password updated";
        } catch (error) {
            // The server returns every failed rule at once in error.details.
            // Showing them as a list beats one line the user has to re-earn.
            if (error.details && error.details.length) {
                el.formError.textContent =
                    error.message + " " + error.details.join(". ") + ".";
            } else {
                el.formError.textContent = error.message;
            }

            // A token that died between page load and submit - the 20 minutes
            // ran out while they were typing. Swap to the dead state rather
            // than leaving them retrying a form that cannot succeed.
            if (error.code && error.code.indexOf("token_") === 0) {
                showDead(error.code.replace("token_", ""));
            }
        } finally {
            window.ui.setLoading(el.resetBtn, false);
        }
    }

    function init() {
        cache();

        window.ui.wirePasswordToggle("new_passwordToggle", "new_password");
        window.ui.wirePasswordToggle("confirm_passwordToggle", "confirm_password");
        window.ui.wirePasswordRequirements("new_password", {
            submitId: "resetBtn",
            matchId: "confirm_password"
        });

        el.resetPasswordForm.addEventListener("submit", submit);
        validateToken();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
