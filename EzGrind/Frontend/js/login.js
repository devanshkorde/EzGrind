/* Login page. */

(function () {
    "use strict";

    /* Signup hands the address over here rather than putting it in the URL,
       where it would sit in history and in any shared link. */
    const HANDOFF_KEY = "ezgrind:signup-email";

    /* Server field names are snake_case; input ids are camelCase. */
    const FIELD_TO_INPUT = {
        email: "email",
        password: "password"
    };

    const form = document.getElementById("loginForm");
    const submitButton = document.getElementById("loginBtn");

    function prefillEmail() {
        const handedOver = sessionStorage.getItem(HANDOFF_KEY);
        if (!handedOver) return;

        sessionStorage.removeItem(HANDOFF_KEY);
        document.getElementById("email").value = handedOver;
        document.getElementById("password").focus();
    }

    function showFailure(error) {
        const inputId = FIELD_TO_INPUT[error.field];

        if (inputId) {
            window.ui.setFieldError(inputId, error.message);
            window.ui.focusFirstError(form);
            return;
        }

        // No field named, or one this form does not own: show it at form level.
        document.getElementById("formError").textContent = error.message;
        window.ui.showToast(error.message, "error");
    }

    async function submit(event) {
        event.preventDefault();
        window.ui.clearFieldErrors(form);
        window.ui.setLoading(submitButton, true);

        try {
            await window.api.post("/login", {
                email: document.getElementById("email").value.trim(),
                password: document.getElementById("password").value
            });

            // The cached "signed out" answer from page load is now stale.
            window.api.clearSession();
            window.location.href = "index.html";
        } catch (error) {
            showFailure(error);
            window.ui.setLoading(submitButton, false);
        }
    }

    window.ui.wirePasswordToggle("passwordToggle", "password");
    prefillEmail();
    form.addEventListener("submit", submit);
})();
