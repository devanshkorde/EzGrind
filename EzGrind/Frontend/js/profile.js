/* Profile - read, inline edit, password change, account deletion.

   Private page: api.requireSession() bounces anonymous visitors, which is what
   the old version failed to do (it wrote "undefined" into the DOM after logout).

   Null handling is the theme of this file. Every field on this page is nullable
   except full_name and created_at, so nothing renders a value it does not have:
   a missing measurement becomes an invitation to add it, and an element that
   cannot be computed is removed rather than shown as zero.
*/

(function () {
    "use strict";

    // Strength meter only. The pass/fail rules live in ui.js.
    const MIN_PASSWORD_LENGTH = 8;

    const EDITABLE = ["full_name", "contact_number", "date_of_birth",
                      "height_cm", "weight_kg", "fitness_goal"];

    const GOAL_LABELS = {
        gain: "Gain Weight",
        lose: "Lose Weight",
        maintain: "Maintain Weight",
        muscle: "Build Muscle"
    };

    // BMI is unbounded in theory; the scale shows the range people land in.
    const SCALE_MIN = 15;
    const SCALE_MAX = 40;
    const SCALE_BANDS = [
        { upto: 18.5, label: "Underweight", tone: "warning" },
        { upto: 25, label: "Normal", tone: "success" },
        { upto: 30, label: "Overweight", tone: "warning" },
        { upto: SCALE_MAX, label: "Obese", tone: "danger" }
    ];

    /* Values as loaded, so Cancel can restore them without a refetch. */
    let snapshot = null;

    const el = {};

    function cache() {
        [
            "profileName", "profileSince", "profileGoal", "statGrid",
            "bmiScaleCard", "bmiScale", "detailsView", "detailsForm",
            "editBtn", "saveBtn", "cancelBtn", "passwordForm", "passwordBtn",
            "logoutBtn", "deleteBtn", "weightRanges", "weightChart"
        ].forEach(function (id) { el[id] = document.getElementById(id); });
    }

    // ============================================================
    // FORMATTING
    // ============================================================

    /** Server sends dates as midnight GMT; read UTC parts so the day holds. */
    function isoDay(value) {
        if (!value) return null;
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return null;
        return [
            date.getUTCFullYear(),
            String(date.getUTCMonth() + 1).padStart(2, "0"),
            String(date.getUTCDate()).padStart(2, "0")
        ].join("-");
    }

    function formatMonthYear(value) {
        if (!value) return null;
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return null;
        return new Intl.DateTimeFormat(undefined, {
            month: "long", year: "numeric", timeZone: "UTC"
        }).format(date);
    }

    function formatDay(value) {
        const day = isoDay(value);
        if (!day) return null;
        return new Intl.DateTimeFormat(undefined, {
            day: "numeric", month: "short", year: "numeric"
        }).format(new Date(day + "T00:00:00"));
    }

    // ============================================================
    // HEADER
    // ============================================================

    function renderHeader(user) {
        el.profileName.textContent = user.full_name || "Your profile";

        const since = formatMonthYear(user.created_at);
        // Removed outright rather than shown as "Member since —".
        el.profileSince.hidden = !since;
        if (since) el.profileSince.textContent = "Member since " + since;

        el.profileGoal.replaceChildren();
        const badge = document.createElement("button");
        badge.type = "button";
        badge.className = "badge" + (user.fitness_goal ? " badge--gold" : "");
        badge.textContent = user.fitness_goal
            ? (GOAL_LABELS[user.fitness_goal] || user.fitness_goal)
            : "No goal set";
        badge.addEventListener("click", enterEditMode);
        el.profileGoal.appendChild(badge);
    }

    // ============================================================
    // STATS STRIP
    // ============================================================

    /** A stat card, or a prompt to supply what it needs. */
    function statCard(config) {
        const card = document.createElement("div");
        card.className = "stat-card";

        const label = document.createElement("p");
        label.className = "stat-card__label";
        label.textContent = config.label;
        card.appendChild(label);

        if (config.value === null || config.value === undefined) {
            const prompt = document.createElement("button");
            prompt.type = "button";
            prompt.className = "stat-card__prompt";
            prompt.textContent = config.prompt;
            prompt.addEventListener("click", enterEditMode);
            card.appendChild(prompt);
            return card;
        }

        const value = document.createElement("p");
        value.className = "stat-card__value";
        value.textContent = config.value;
        card.appendChild(value);

        const meta = document.createElement("p");
        meta.className = "stat-card__meta";
        meta.textContent = config.meta || "";
        card.appendChild(meta);

        return card;
    }

    function renderStats(user) {
        el.statGrid.replaceChildren();

        el.statGrid.appendChild(statCard({
            label: "Age",
            value: user.age === null ? null : user.age,
            meta: "years",
            prompt: "Add your date of birth"
        }));

        el.statGrid.appendChild(statCard({
            label: "Height",
            value: user.height_cm === null ? null : Number(user.height_cm),
            meta: "cm",
            prompt: "Add your height"
        }));

        el.statGrid.appendChild(statCard({
            label: "Weight",
            value: user.weight_kg === null ? null : Number(user.weight_kg),
            meta: "kg",
            prompt: "Add your weight"
        }));

        el.statGrid.appendChild(statCard({
            label: "BMI",
            value: user.bmi === null ? null : user.bmi,
            // Category omitted entirely when there is no BMI to categorise.
            meta: user.bmi_category || "",
            prompt: "Needs height and weight"
        }));

        renderBmiScale(user.bmi, user.bmi_category);
    }

    function renderBmiScale(bmi, category) {
        // The whole scale disappears without a BMI. A marker parked at the far
        // left would read as a real measurement of a very low BMI.
        if (bmi === null || bmi === undefined) {
            el.bmiScaleCard.classList.add("is-hidden");
            return;
        }

        el.bmiScaleCard.classList.remove("is-hidden");
        el.bmiScale.replaceChildren();

        const track = document.createElement("div");
        track.className = "bmi-scale__track";

        let previous = SCALE_MIN;
        SCALE_BANDS.forEach(function (band) {
            const segment = document.createElement("div");
            segment.className = "bmi-scale__band bmi-scale__band--" + band.tone;
            segment.style.flexGrow = String(band.upto - previous);
            segment.title = band.label;
            track.appendChild(segment);
            previous = band.upto;
        });

        const clamped = Math.min(SCALE_MAX, Math.max(SCALE_MIN, bmi));
        const marker = document.createElement("div");
        marker.className = "bmi-scale__marker";
        marker.style.left =
            ((clamped - SCALE_MIN) / (SCALE_MAX - SCALE_MIN) * 100) + "%";
        track.appendChild(marker);

        el.bmiScale.appendChild(track);

        const caption = document.createElement("p");
        caption.className = "bmi-scale__caption";
        // Never colour alone: the number and the category name are both text.
        caption.textContent = bmi + (category ? " · " + category : "");
        el.bmiScale.appendChild(caption);
    }

    // ============================================================
    // WEIGHT CHART
    // ============================================================

    function monthsAgoIso(months) {
        const date = new Date();
        date.setMonth(date.getMonth() - months);
        return [
            date.getFullYear(),
            String(date.getMonth() + 1).padStart(2, "0"),
            String(date.getDate()).padStart(2, "0")
        ].join("-");
    }

    async function loadWeightChart(months) {
        // 0 months means "All", which is simply no lower bound.
        const query = months > 0 ? "?from=" + monthsAgoIso(months) : "";

        window.ui.renderSkeleton(el.weightChart, { rows: 1, parts: ["chart"] });

        try {
            const payload = await window.api.get("/weight-logs" + query);
            // The chart takes {date, weight}; the API speaks logged_on/weight_kg.
            window.charts.weightOverTime(el.weightChart, payload.data.map(function (entry) {
                return { date: isoDay(entry.logged_on), weight: entry.weight_kg };
            }));
        } catch (error) {
            window.ui.renderErrorState(el.weightChart, error, function () {
                loadWeightChart(months);
            });
        }
    }

    function wireWeightRanges() {
        el.weightRanges.querySelectorAll(".chip").forEach(function (chip) {
            chip.addEventListener("click", function () {
                el.weightRanges.querySelectorAll(".chip").forEach(function (other) {
                    other.setAttribute("aria-pressed", String(other === chip));
                });
                loadWeightChart(Number(chip.dataset.months));
            });
        });
    }

    function activeRangeMonths() {
        const pressed = el.weightRanges.querySelector('.chip[aria-pressed="true"]');
        return pressed ? Number(pressed.dataset.months) : 3;
    }

    // ============================================================
    // DETAILS (read view)
    // ============================================================

    function detailRow(label, value, prompt) {
        const row = document.createElement("div");
        row.className = "profile-item";

        const term = document.createElement("dt");
        term.className = "profile-item__label";
        term.textContent = label;

        const detail = document.createElement("dd");
        detail.className = "profile-item__value";

        if (value === null || value === undefined || value === "") {
            detail.classList.add("text-muted");
            detail.textContent = prompt || "Not set";
        } else {
            detail.textContent = value;
        }

        row.appendChild(term);
        row.appendChild(detail);
        return row;
    }

    function renderDetails(user) {
        el.detailsView.replaceChildren();
        el.detailsView.appendChild(detailRow("Name", user.full_name));
        el.detailsView.appendChild(detailRow("Email", user.email));
        el.detailsView.appendChild(
            detailRow("Contact", user.contact_number, "Not set"));
        el.detailsView.appendChild(
            detailRow("Date of birth", formatDay(user.date_of_birth), "Not set"));
        el.detailsView.appendChild(detailRow(
            "Fitness goal",
            user.fitness_goal ? (GOAL_LABELS[user.fitness_goal] || user.fitness_goal) : null,
            "No goal set"
        ));
    }

    function renderAll(user) {
        snapshot = user;
        renderHeader(user);
        renderStats(user);
        renderDetails(user);
    }

    // ============================================================
    // EDIT MODE
    // ============================================================

    function fillForm(user) {
        document.getElementById("full_name").value = user.full_name || "";
        document.getElementById("contact_number").value = user.contact_number || "";
        document.getElementById("date_of_birth").value = isoDay(user.date_of_birth) || "";
        document.getElementById("height_cm").value =
            user.height_cm === null ? "" : user.height_cm;
        document.getElementById("weight_kg").value =
            user.weight_kg === null ? "" : user.weight_kg;
        document.getElementById("fitness_goal").value = user.fitness_goal || "";
    }

    function enterEditMode() {
        window.ui.clearFieldErrors(el.detailsForm);
        fillForm(snapshot);
        el.detailsView.classList.add("is-hidden");
        el.detailsForm.classList.remove("is-hidden");
        el.editBtn.classList.add("is-hidden");
        document.getElementById("full_name").focus();
    }

    function leaveEditMode() {
        el.detailsForm.classList.add("is-hidden");
        el.detailsView.classList.remove("is-hidden");
        el.editBtn.classList.remove("is-hidden");
        el.editBtn.focus();
    }

    function cancelEdit() {
        // Restore from the snapshot rather than refetching: no request, and the
        // user sees exactly what was there before they started.
        fillForm(snapshot);
        window.ui.clearFieldErrors(el.detailsForm);
        leaveEditMode();
    }

    /** Only what actually changed. An untouched field is never sent, so it is
     *  never at risk of being cleared by an empty string. */
    function changedFields() {
        const changes = {};

        EDITABLE.forEach(function (name) {
            const raw = document.getElementById(name).value.trim();
            let before = snapshot[name];

            if (name === "date_of_birth") before = isoDay(before) || "";
            else if (before === null || before === undefined) before = "";
            else before = String(before);

            if (raw !== before) changes[name] = raw;
        });

        return changes;
    }

    async function saveDetails(event) {
        event.preventDefault();
        window.ui.clearFieldErrors(el.detailsForm);

        const changes = changedFields();
        if (Object.keys(changes).length === 0) {
            leaveEditMode();
            window.ui.showToast("Nothing changed.", "info");
            return;
        }

        window.ui.setLoading(el.saveBtn, true);

        try {
            const payload = await window.api.patch("/me", changes);
            renderAll(payload.data);
            // The cached session now holds an old name; drop it so the nav and
            // dashboard pick up the change on the next page.
            window.api.clearSession();
            leaveEditMode();
            window.ui.showToast("Profile updated.", "success");
        } catch (error) {
            if (error.field) window.ui.setFieldError(error.field, error.message);
            else document.getElementById("detailsError").textContent = error.message;
            window.ui.showToast(error.message, "error");
            window.ui.focusFirstError(el.detailsForm);
        } finally {
            window.ui.setLoading(el.saveBtn, false);
        }
    }

    // ============================================================
    // PASSWORD
    // ============================================================

    async function changePassword(event) {
        event.preventDefault();
        window.ui.clearFieldErrors(el.passwordForm);

        const current = document.getElementById("current_password").value;
        const replacement = document.getElementById("new_password").value;
        const confirmation = document.getElementById("confirm_password").value;

        // The live checklist under the field carries the detail; this is the
        // backstop, and it defers to ui.js so the rules exist in one place.
        if (!window.ui.passwordRulesPassed(replacement)) {
            window.ui.setFieldError("new_password",
                "Password does not meet the requirements below.");
            window.ui.focusFirstError(el.passwordForm);
            return;
        }

        if (replacement !== confirmation) {
            window.ui.setFieldError("confirm_password", "These do not match.");
            window.ui.focusFirstError(el.passwordForm);
            return;
        }

        window.ui.setLoading(el.passwordBtn, true);

        try {
            await window.api.post("/me/password", {
                current_password: current,
                new_password: replacement
            });
            el.passwordForm.reset();
            document.getElementById("new_passwordStrength").hidden = true;
            window.ui.showToast("Password updated.", "success");
        } catch (error) {
            // The server returns every failed rule at once, so show them all
            // rather than making the user rediscover them one submit at a time.
            const detail = error.details.length
                ? error.message + " " + error.details.join(". ") + "."
                : error.message;
            if (error.field) window.ui.setFieldError(error.field, detail);
            else document.getElementById("passwordFormError").textContent = detail;
            window.ui.focusFirstError(el.passwordForm);
        } finally {
            window.ui.setLoading(el.passwordBtn, false);
        }
    }

    // ============================================================
    // SESSION AND DELETION
    // ============================================================

    async function logout() {
        const confirmed = await window.ui.confirmDialog({
            title: "Log out?",
            body: "You will need your email and password to get back in.",
            confirmLabel: "Log out",
            danger: true
        });
        if (!confirmed) return;

        window.ui.setLoading(el.logoutBtn, true);
        try {
            await window.api.post("/logout");
            window.api.clearSession();
            window.location.href = "index.html";
        } catch (error) {
            window.ui.showToast(error.message, "error");
            window.ui.setLoading(el.logoutBtn, false);
        }
    }

    /* Typed confirmation plus the password: deleting a training history should
       take deliberate effort, not one misplaced click. */
    function deleteDialog() {
        const panel = document.createElement("div");
        panel.className = "modal__panel modal__panel--wide";

        const title = document.createElement("h2");
        title.className = "modal__title";
        title.textContent = "Delete your account";

        const body = document.createElement("p");
        body.className = "modal__body";
        body.textContent = "This removes your profile and every workout and set you " +
                           "have logged. It cannot be undone.";

        const typedField = document.createElement("div");
        typedField.className = "field";

        const typedLabel = document.createElement("label");
        typedLabel.className = "field__label";
        typedLabel.setAttribute("for", "deleteConfirmText");
        typedLabel.textContent = "Type DELETE to confirm";

        const typedInput = document.createElement("input");
        typedInput.className = "input";
        typedInput.id = "deleteConfirmText";
        typedInput.autocomplete = "off";

        typedField.appendChild(typedLabel);
        typedField.appendChild(typedInput);

        const passField = document.createElement("div");
        passField.className = "field";

        const passLabel = document.createElement("label");
        passLabel.className = "field__label";
        passLabel.setAttribute("for", "deletePassword");
        passLabel.textContent = "Your password";

        const passInput = document.createElement("input");
        passInput.className = "input";
        passInput.type = "password";
        passInput.id = "deletePassword";
        passInput.autocomplete = "current-password";

        passField.appendChild(passLabel);
        passField.appendChild(passInput);

        const error = document.createElement("p");
        error.className = "form-error";
        error.setAttribute("role", "alert");

        const actions = document.createElement("div");
        actions.className = "modal__actions";

        const cancel = document.createElement("button");
        cancel.type = "button";
        cancel.className = "btn btn--ghost";
        cancel.textContent = "Keep my account";

        const confirm = document.createElement("button");
        confirm.type = "button";
        confirm.className = "btn btn--danger";
        confirm.textContent = "Delete permanently";
        confirm.disabled = true;

        // Stays disabled until the word is exactly right.
        typedInput.addEventListener("input", function () {
            confirm.disabled = typedInput.value !== "DELETE";
        });

        actions.appendChild(cancel);
        actions.appendChild(confirm);

        panel.appendChild(title);
        panel.appendChild(body);
        panel.appendChild(typedField);
        panel.appendChild(passField);
        panel.appendChild(error);
        panel.appendChild(actions);

        const dialog = window.ui.openDialog(panel, { label: "Delete your account" });

        cancel.addEventListener("click", function () { dialog.close("cancel"); });

        confirm.addEventListener("click", async function () {
            error.textContent = "";
            window.ui.setLoading(confirm, true);

            try {
                await window.api.del("/me", { password: passInput.value });
                window.api.clearSession();
                window.location.href = "index.html";
            } catch (failure) {
                error.textContent = failure.message;
                window.ui.setLoading(confirm, false);
            }
        });

        typedInput.focus();
    }

    // ============================================================
    // INIT
    // ============================================================

    async function init() {
        cache();

        el.editBtn.addEventListener("click", enterEditMode);
        el.cancelBtn.addEventListener("click", cancelEdit);
        el.detailsForm.addEventListener("submit", saveDetails);
        el.passwordForm.addEventListener("submit", changePassword);
        el.logoutBtn.addEventListener("click", logout);
        el.deleteBtn.addEventListener("click", deleteDialog);
        wireWeightRanges();

        window.ui.wirePasswordToggle("currentToggle", "current_password");
        window.ui.wirePasswordToggle("newToggle", "new_password");
        window.ui.wireStrengthMeter("new_password", MIN_PASSWORD_LENGTH);
        window.ui.wirePasswordRequirements("new_password", {
            submitId: "passwordBtn",
            matchId: "confirm_password"
        });

        try {
            const user = await window.api.requireSession();
            if (!user) return;
            renderAll(user);
            await loadWeightChart(activeRangeMonths());
        } catch (error) {
            window.ui.showToast(error.message, "error");
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
