/* ============================================================
   ui.js
   Shared feedback primitives: toasts, button loading states,
   empty states and a confirm dialog.

   Exists to kill alert() and confirm(), which block the whole
   page, cannot be styled, and say "127.0.0.1:5500 says" above
   every message. Exposes window.ui.
   ============================================================ */

(function () {
    "use strict";

    const TOAST_DURATION = 4000;

    function toastRegion() {
        let region = document.querySelector(".toast-region");
        if (!region) {
            region = document.createElement("div");
            region.className = "toast-region";
            /* polite, not assertive: a save confirmation should not
               interrupt whatever a screen reader is mid-sentence on. */
            region.setAttribute("role", "status");
            region.setAttribute("aria-live", "polite");
            document.body.appendChild(region);
        }
        return region;
    }

    function dismiss(toast) {
        if (!toast.isConnected) return;
        toast.classList.add("is-leaving");
        toast.addEventListener("animationend", function () {
            toast.remove();
        }, { once: true });
    }

    /**
     * @param {string} message
     * @param {"success"|"error"|"warning"|"info"} type
     */
    function showToast(message, type) {
        const toast = document.createElement("div");
        toast.className = "toast toast--" + (type || "info");

        const text = document.createElement("span");
        text.className = "toast__message";
        text.textContent = message;

        const close = document.createElement("button");
        close.className = "toast__close";
        close.type = "button";
        close.setAttribute("aria-label", "Dismiss notification");
        close.textContent = "×";
        close.addEventListener("click", function () { dismiss(toast); });

        toast.appendChild(text);
        toast.appendChild(close);
        toastRegion().appendChild(toast);

        window.setTimeout(function () { dismiss(toast); }, TOAST_DURATION);
        return toast;
    }

    /**
     * Toggles a button's spinner. The label keeps its box, so the
     * button cannot change width mid-request.
     */
    function setLoading(element, isLoading) {
        if (!element) return;
        element.classList.toggle("is-loading", Boolean(isLoading));
        if ("disabled" in element) {
            element.disabled = Boolean(isLoading);
        }
        element.setAttribute("aria-busy", isLoading ? "true" : "false");
    }

    /**
     * Placeholder lines shaped like the content that will replace them, so
     * nothing shifts when the real data lands.
     *
     * aria-hidden because a screen reader announcing a row of empty boxes is
     * noise; the real content is announced when it arrives.
     *
     * @param {Element} container
     * @param {{rows?: number, parts?: string[], card?: boolean}} [options]
     */
    function renderSkeleton(container, options) {
        if (!container) return;

        const config = options || {};
        const rows = config.rows || 3;
        const parts = config.parts || ["title", "text"];

        container.replaceChildren();

        for (let index = 0; index < rows; index++) {
            const row = document.createElement("div");
            row.className = "skeleton-row" + (config.card ? " card" : "");
            row.setAttribute("aria-hidden", "true");

            parts.forEach(function (part) {
                const line = document.createElement("span");
                line.className = "skeleton skeleton--" + part;
                row.appendChild(line);
            });

            container.appendChild(row);
        }
    }

    /**
     * Replaces a container's contents with an error state.
     *
     * Shows Retry only when the error is actually transient - api.js decides
     * that, not this function. Never renders a status code or an exception
     * string: error.message is already human, either written by us or mapped
     * from the status on the server.
     *
     * @param {Element} container
     * @param {{message: string, status?: number, retryable?: boolean}} error
     * @param {Function} [onRetry]
     */
    function renderErrorState(container, error, onRetry) {
        if (!container) return;

        const offline = error && error.status === 0;

        return renderEmptyState(container, {
            icon: offline ? "📡" : "⚠️",
            title: offline ? "Can't reach the server" : "Something went wrong",
            body: (error && error.message) || "Please try again.",
            actionLabel: (error && error.retryable && onRetry) ? "Try again" : null,
            onAction: onRetry,
            tone: "error"
        });
    }

    /**
     * Replaces a container's contents with an empty state.
     * @param {Element} container
     * @param {{icon?:string,title:string,body?:string,actionLabel?:string,onAction?:Function,tone?:string}} options
     */
    function renderEmptyState(container, options) {
        if (!container) return;
        const config = options || {};
        container.replaceChildren();

        const wrap = document.createElement("div");
        wrap.className = "empty-state" +
                         (config.tone ? " empty-state--" + config.tone : "");

        if (config.icon) {
            const icon = document.createElement("div");
            icon.className = "empty-state__icon";
            icon.setAttribute("aria-hidden", "true");
            icon.textContent = config.icon;
            wrap.appendChild(icon);
        }

        const title = document.createElement("p");
        title.className = "empty-state__title";
        title.textContent = config.title || "";
        wrap.appendChild(title);

        if (config.body) {
            const body = document.createElement("p");
            body.className = "empty-state__body";
            body.textContent = config.body;
            wrap.appendChild(body);
        }

        if (config.actionLabel) {
            const action = document.createElement("button");
            action.type = "button";
            action.className = "btn btn--secondary empty-state__action";
            action.textContent = config.actionLabel;
            if (config.onAction) {
                action.addEventListener("click", config.onAction);
            }
            wrap.appendChild(action);
        }

        container.appendChild(wrap);
        return wrap;
    }

    /* --- Dialogs -------------------------------------------------
       Built on native <dialog> + showModal(), which gives focus trapping,
       Escape-to-close and focus restoration for free. The hand-rolled version
       this replaced had no real trap: Tab walked straight out of it into the
       page behind. */

    /**
     * Shows `panel` in a modal dialog. Resolves the returnValue on close.
     * @param {Element} panel
     * @param {{onClose?: Function, label?: string}} [options]
     * @returns {HTMLDialogElement}
     */
    function openDialog(panel, options) {
        const config = options || {};

        const dialog = document.createElement("dialog");
        dialog.className = "dialog";
        if (config.label) dialog.setAttribute("aria-label", config.label);
        dialog.appendChild(panel);
        document.body.appendChild(dialog);

        dialog.addEventListener("close", function () {
            dialog.remove();
            if (config.onClose) config.onClose(dialog.returnValue);
        });

        // The backdrop is the dialog element itself, so a click landing on the
        // dialog rather than the panel happened outside the panel.
        dialog.addEventListener("click", function (event) {
            if (event.target === dialog) dialog.close("dismiss");
        });

        dialog.showModal();
        return dialog;
    }

    /**
     * Styled replacement for window.confirm.
     * @returns {Promise<boolean>}
     */
    function confirmDialog(options) {
        const config = options || {};

        return new Promise(function (resolve) {
            const panel = document.createElement("div");
            panel.className = "modal__panel";

            const title = document.createElement("h2");
            title.className = "modal__title";
            title.textContent = config.title || "Are you sure?";
            panel.appendChild(title);

            if (config.body) {
                const body = document.createElement("p");
                body.className = "modal__body";
                body.textContent = config.body;
                panel.appendChild(body);
            }

            const actions = document.createElement("div");
            actions.className = "modal__actions";

            const cancel = document.createElement("button");
            cancel.type = "button";
            cancel.className = "btn btn--ghost";
            cancel.textContent = config.cancelLabel || "Cancel";

            const confirm = document.createElement("button");
            confirm.type = "button";
            confirm.className = "btn " + (config.danger ? "btn--danger" : "btn--primary");
            confirm.textContent = config.confirmLabel || "Confirm";

            actions.appendChild(cancel);
            actions.appendChild(confirm);
            panel.appendChild(actions);

            // Escape and backdrop both close with a value that is not
            // "confirm", so anything other than the explicit button is a no.
            const dialog = openDialog(panel, {
                label: title.textContent,
                onClose: function (value) { resolve(value === "confirm"); }
            });

            cancel.addEventListener("click", function () { dialog.close("cancel"); });
            confirm.addEventListener("click", function () { dialog.close("confirm"); });
            confirm.focus();
        });
    }

    /* --- Forms ---------------------------------------------------
       Convention: an input with id "email" has its error slot at
       "emailError". Keeps the wiring implicit instead of asking every
       caller to pass both ids. */

    function setFieldError(inputId, message) {
        const input = document.getElementById(inputId);
        const slot = document.getElementById(inputId + "Error");

        if (slot) slot.textContent = message || "";
        if (!input) return;

        if (message) {
            input.setAttribute("aria-invalid", "true");
        } else {
            input.removeAttribute("aria-invalid");
        }
    }

    function clearFieldErrors(form) {
        if (!form) return;
        form.querySelectorAll(".form-error").forEach(function (slot) {
            slot.textContent = "";
        });
        form.querySelectorAll("[aria-invalid]").forEach(function (input) {
            input.removeAttribute("aria-invalid");
        });
    }

    /** Moves focus to the first invalid input so keyboard users are not stranded. */
    function focusFirstError(form) {
        const first = form && form.querySelector("[aria-invalid='true']");
        if (first) first.focus();
    }

    /* --- Password strength --------------------------------------
       Guidance, not a gate: the server's minimum length is the only
       enforced rule. Shared by signup and the profile's password form so
       the same password never scores differently in two places. */

    const STRENGTH_LABELS = [
        "Too short",
        "Weak — add length or variety",
        "Fair",
        "Good",
        "Strong"
    ];

    function scorePassword(value, minLength) {
        if (value.length < minLength) return 0;

        let score = 1;
        if (value.length >= 12) score++;
        if (/[a-z]/.test(value) && /[A-Z]/.test(value)) score++;
        if (/\d/.test(value) && /[^A-Za-z0-9]/.test(value)) score++;
        return Math.min(score, 4);
    }

    /**
     * Convention: an input with id "password" drives "passwordStrength" and
     * "passwordStrengthLabel".
     */
    function wireStrengthMeter(inputId, minLength) {
        const input = document.getElementById(inputId);
        const meter = document.getElementById(inputId + "Strength");
        const label = document.getElementById(inputId + "StrengthLabel");
        if (!input || !meter || !label) return;

        const floor = minLength || 6;

        input.addEventListener("input", function () {
            if (!input.value) {
                meter.hidden = true;
                return;
            }
            const score = scorePassword(input.value, floor);
            meter.hidden = false;
            meter.dataset.score = String(score);
            label.textContent = STRENGTH_LABELS[score];
        });
    }

    /* --- Password requirements ----------------------------------

       A live checklist under the field, updating as the user types. Grey
       dot when unmet, gold check when met.

       MIRRORS Backend/validators.py. That copy is authoritative - anything
       here can be bypassed with a terminal, and the server re-checks every
       rule regardless. This exists so nobody submits a form to discover a
       rule they could have been shown while typing.

       Kept in sync by hand, which is a real cost; the payoff is that the
       page needs no round trip to tell the user where they stand. The
       backend returns the same rule names in error.details, so a mismatch
       shows up as two different phrasings of the same rule rather than a
       silent divergence. */

    const PASSWORD_MIN_LENGTH = 8;
    const PASSWORD_SPECIALS = "!@#$%^&*()-_=+[]{};:,.<>?/~`|\\'\" ";

    const PASSWORD_RULES = [
        {
            id: "length",
            label: "At least " + PASSWORD_MIN_LENGTH + " characters",
            test: function (value) { return value.length >= PASSWORD_MIN_LENGTH; }
        },
        {
            id: "upper",
            label: "One uppercase letter",
            test: function (value) { return /[A-Z]/.test(value); }
        },
        {
            id: "digit",
            label: "One number",
            test: function (value) { return /\d/.test(value); }
        },
        {
            id: "special",
            label: "One special character",
            test: function (value) {
                return value.split("").some(function (character) {
                    return PASSWORD_SPECIALS.indexOf(character) !== -1;
                });
            }
        }
    ];

    function passwordRulesPassed(value) {
        return PASSWORD_RULES.every(function (rule) { return rule.test(value || ""); });
    }

    function buildRequirementList(container) {
        const list = document.createElement("ul");
        list.className = "requirements";

        PASSWORD_RULES.forEach(function (rule) {
            const item = document.createElement("li");
            item.className = "requirements__item";
            item.dataset.rule = rule.id;

            const mark = document.createElement("span");
            mark.className = "requirements__mark";
            // The tick is decorative - "met"/"not met" is announced through
            // aria-label on the item, so a screen reader is not read a bullet.
            mark.setAttribute("aria-hidden", "true");
            mark.textContent = "✓";

            const text = document.createElement("span");
            text.textContent = rule.label;

            item.appendChild(mark);
            item.appendChild(text);
            list.appendChild(item);
        });

        container.appendChild(list);
        return list;
    }

    /**
     * Renders the checklist under `inputId` and keeps it live.
     *
     * Pass `submitId` to have the button disabled until every rule passes, and
     * `matchId` for a confirm-password field that must also agree.
     *
     * Returns a function reporting whether everything currently passes, so a
     * caller can re-check after changing a field programmatically.
     */
    function wirePasswordRequirements(inputId, options) {
        const settings = options || {};
        const input = document.getElementById(inputId);
        const host = document.getElementById(inputId + "Requirements");
        if (!input || !host) return function () { return false; };

        const list = buildRequirementList(host);
        const submit = settings.submitId
            ? document.getElementById(settings.submitId) : null;
        const match = settings.matchId
            ? document.getElementById(settings.matchId) : null;
        const matchNote = settings.matchId
            ? document.getElementById(settings.matchId + "Error") : null;

        function evaluate() {
            const value = input.value || "";

            PASSWORD_RULES.forEach(function (rule) {
                const item = list.querySelector('[data-rule="' + rule.id + '"]');
                const met = rule.test(value);
                item.classList.toggle("is-met", met);
                item.setAttribute("aria-label",
                    rule.label + (met ? ": met" : ": not met yet"));
            });

            let ok = passwordRulesPassed(value);

            if (match) {
                const confirmed = match.value || "";
                // Silent until they have actually typed something: warning
                // "does not match" against an empty box is just noise.
                const mismatch = confirmed.length > 0 && confirmed !== value;
                if (matchNote) {
                    matchNote.textContent = mismatch ? "Passwords do not match." : "";
                }
                if (confirmed !== value) ok = false;
            }

            if (submit) submit.disabled = !ok;
            return ok;
        }

        input.addEventListener("input", evaluate);
        if (match) match.addEventListener("input", evaluate);
        evaluate();
        return evaluate;
    }

    function wirePasswordToggle(toggleId, inputId) {
        const toggle = document.getElementById(toggleId);
        const input = document.getElementById(inputId);
        if (!toggle || !input) return;

        toggle.addEventListener("click", function () {
            const wasRevealed = input.type === "text";
            input.type = wasRevealed ? "password" : "text";
            toggle.textContent = wasRevealed ? "Show" : "Hide";
            toggle.setAttribute("aria-pressed", String(!wasRevealed));
            input.focus();
        });
    }

    /* --- Offline ------------------------------------------------
       A persistent banner, not a toast: being offline is a state that
       lasts, and a message that auto-dismisses after 4 seconds would
       claim the problem went away. */

    function offlineBanner() {
        let banner = document.querySelector(".offline-banner");
        if (!banner) {
            banner = document.createElement("div");
            banner.className = "offline-banner";
            banner.setAttribute("role", "status");
            banner.setAttribute("aria-live", "polite");
            banner.textContent =
                "You're offline. Anything you log now won't be saved until you reconnect.";
            document.body.appendChild(banner);
        }
        return banner;
    }

    function syncOnlineState(announceReturn) {
        const online = navigator.onLine;
        offlineBanner().hidden = online;
        // The padding keeps the fixed banner from covering the nav.
        document.documentElement.classList.toggle("is-offline", !online);

        if (online && announceReturn) {
            showToast("Back online.", "success");
        }
    }

    /* [data-reload] reloads the page. Exists so the error pages need no inline
       script of their own - every page already loads this file. */
    function installReloadButtons() {
        document.querySelectorAll("[data-reload]").forEach(function (trigger) {
            trigger.addEventListener("click", function () {
                window.location.reload();
            });
        });
    }

    function installConnectivityWatch() {
        window.addEventListener("offline", function () { syncOnlineState(false); });
        window.addEventListener("online", function () { syncOnlineState(true); });
        if (!navigator.onLine) syncOnlineState(false);
    }

    /* A rejected promise with no handler used to reach the console and nowhere
       else, which is the definition of a silent failure. This fires only when
       nothing else caught it, so it cannot double-report a handled error.
       Deliberately does not preventDefault: developers keep the console trace. */
    function installRejectionHandler() {
        window.addEventListener("unhandledrejection", function (event) {
            const reason = event.reason;
            const message = (reason && reason.message) ||
                            "Something went wrong. Please try again.";
            showToast(message, "error");
        });
    }

    function install() {
        installConnectivityWatch();
        installReloadButtons();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", install);
    } else {
        install();
    }
    installRejectionHandler();

    window.ui = {
        showToast: showToast,
        setLoading: setLoading,
        renderSkeleton: renderSkeleton,
        renderErrorState: renderErrorState,
        renderEmptyState: renderEmptyState,
        confirmDialog: confirmDialog,
        openDialog: openDialog,
        setFieldError: setFieldError,
        clearFieldErrors: clearFieldErrors,
        focusFirstError: focusFirstError,
        wirePasswordToggle: wirePasswordToggle,
        wirePasswordRequirements: wirePasswordRequirements,
        passwordRulesPassed: passwordRulesPassed,
        wireStrengthMeter: wireStrengthMeter
    };
})();
