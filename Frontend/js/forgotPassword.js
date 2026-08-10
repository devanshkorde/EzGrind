/* Forgot password - request a reset link.

   Public page. The one thing this file must not do is reveal whether an
   account exists: the server returns an identical message either way, and the
   confirmation state below repeats that wording verbatim rather than
   paraphrasing it into "check your inbox".
*/

(function () {
    "use strict";

    const el = {};

    function cache() {
        ["forgotForm", "email", "emailError", "formError", "forgotBtn",
         "forgotSent", "forgotRetry"].forEach(function (id) {
            el[id] = document.getElementById(id);
        });
    }

    function showSent() {
        el.forgotForm.hidden = true;
        el.forgotSent.hidden = false;
        // Focus moves to the confirmation so a screen reader announces the
        // outcome instead of leaving the user on a form that vanished.
        el.forgotSent.setAttribute("tabindex", "-1");
        el.forgotSent.focus();
    }

    function showForm() {
        el.forgotSent.hidden = true;
        el.forgotForm.hidden = false;
        el.email.value = "";
        el.email.focus();
    }

    async function submit(event) {
        event.preventDefault();
        window.ui.clearFieldErrors(el.forgotForm);
        el.formError.textContent = "";

        const email = el.email.value.trim();
        if (!email) {
            window.ui.setFieldError("email", "Enter your email address.");
            return;
        }

        window.ui.setLoading(el.forgotBtn, true);
        try {
            await window.api.post("/forgot-password", { email: email });
            // Success and "no such account" are the same response by design,
            // so there is nothing here to branch on.
            showSent();
        } catch (error) {
            // A 429 or a malformed address is worth showing. Neither says
            // anything about whether the account exists.
            el.formError.textContent = error.message;
            if (error.field) window.ui.setFieldError(error.field, error.message);
        } finally {
            window.ui.setLoading(el.forgotBtn, false);
        }
    }

    function init() {
        cache();
        el.forgotForm.addEventListener("submit", submit);
        el.forgotRetry.addEventListener("click", showForm);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
