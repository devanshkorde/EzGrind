/* Signup page. */

(function () {
    "use strict";

    const NAME_PATTERN = /^[A-Za-z ]+$/;
    const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    const PHONE_PATTERN = /^[0-9]{10}$/;
    // Drives the strength meter only. The pass/fail rules live in ui.js so
    // signup, reset and change-password cannot drift apart.
    const MIN_PASSWORD_LENGTH = 8;

    const HANDOFF_KEY = "ezgrind:signup-email";
    const REDIRECT_DELAY = 1200;

    /* Server field names are snake_case; input ids are camelCase. */
    const FIELD_TO_INPUT = {
        full_name: "fullName",
        email: "email",
        password: "password",
        contact_number: "contact",
        date_of_birth: "dob",
        height_cm: "height",
        weight_kg: "weight",
        fitness_goal: "fitnessGoal"
    };

    const form = document.getElementById("signupForm");
    const submitButton = document.getElementById("signupBtn");

    function valueOf(id) {
        return document.getElementById(id).value.trim();
    }

    function collect() {
        return {
            full_name: valueOf("fullName"),
            email: valueOf("email"),
            password: document.getElementById("password").value,
            contact_number: valueOf("contact"),
            date_of_birth: valueOf("dob"),
            height_cm: valueOf("height"),
            weight_kg: valueOf("weight"),
            fitness_goal: valueOf("fitnessGoal")
        };
    }

    /* Mirrors Backend/validators.py. The server copy is authoritative - this
       one runs so the user is not waiting on a round-trip to learn they typed
       a letter into the phone box. Returns every problem, not just the first,
       so the form does not reveal its objections one at a time. */
    function clientProblems(fields) {
        const problems = {};
        const height = Number(fields.height_cm);
        const weight = Number(fields.weight_kg);

        if (!NAME_PATTERN.test(fields.full_name)) {
            problems.fullName = "Name should contain only letters and spaces.";
        }
        if (!EMAIL_PATTERN.test(fields.email)) {
            problems.email = "Enter a valid email address.";
        }
        // The live checklist under the field is the real feedback; this only
        // catches a submit that got past it, and defers to ui.js so the rules
        // are defined in exactly one place on the frontend.
        if (!window.ui.passwordRulesPassed(fields.password)) {
            problems.password = "Password does not meet the requirements below.";
        }
        if (!PHONE_PATTERN.test(fields.contact_number)) {
            problems.contact = "Contact number must be 10 digits.";
        }
        if (!(height > 0 && height <= 300)) {
            problems.height = "Enter a height between 1 and 300 cm.";
        }
        if (!(weight > 0 && weight <= 500)) {
            problems.weight = "Enter a weight between 1 and 500 kg.";
        }
        if (!fields.fitness_goal) {
            problems.fitnessGoal = "Select a fitness goal.";
        }
        return problems;
    }

    function showProblems(problems) {
        Object.keys(problems).forEach(function (inputId) {
            window.ui.setFieldError(inputId, problems[inputId]);
        });
        window.ui.focusFirstError(form);
    }

    function showFailure(error) {
        const inputId = FIELD_TO_INPUT[error.field];

        if (inputId) {
            window.ui.setFieldError(inputId, error.message);
            window.ui.focusFirstError(form);
            window.ui.showToast("Check the highlighted field.", "warning");
            return;
        }

        document.getElementById("formError").textContent = error.message;
        window.ui.showToast(error.message, "error");
    }

    async function submit(event) {
        event.preventDefault();
        window.ui.clearFieldErrors(form);

        const fields = collect();
        const problems = clientProblems(fields);

        if (Object.keys(problems).length > 0) {
            showProblems(problems);
            window.ui.showToast("Some details need fixing.", "warning");
            return;
        }

        window.ui.setLoading(submitButton, true);

        try {
            await window.api.post("/signup", fields);

            window.ui.showToast("Account created. Taking you to log in…", "success");
            sessionStorage.setItem(HANDOFF_KEY, fields.email);

            // Button stays disabled through the delay, so the window between
            // success and navigation is not a second-submit opportunity.
            window.setTimeout(function () {
                window.location.href = "login.html";
            }, REDIRECT_DELAY);
        } catch (error) {
            showFailure(error);
            window.ui.setLoading(submitButton, false);
        }
    }

    window.ui.wirePasswordToggle("passwordToggle", "password");
    window.ui.wireStrengthMeter("password", MIN_PASSWORD_LENGTH);
    // No submitId here: this form has nine other fields, and disabling the
    // button on the password alone would leave someone unable to submit with
    // no visible reason why.
    window.ui.wirePasswordRequirements("password");
    form.addEventListener("submit", submit);
})();
