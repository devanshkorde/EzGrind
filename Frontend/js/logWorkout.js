/* Log Workout - pick a muscle, pick an exercise, log sets into today's session.

   Private page: api.requireSession() bounces anonymous visitors before any
   request that could 401.

   The bounds below mirror Backend/validators.py. That copy is authoritative;
   this one exists so the user is not waiting on a round-trip to be told 200
   reps is not a number of reps.
*/

(function () {
    "use strict";

    const WEIGHT_MIN = 0;
    const WEIGHT_MAX = 500;
    const REPS_MIN = 1;
    const REPS_MAX = 100;
    const COMMENT_MAX = 500;

    const SEARCH_DEBOUNCE = 250;
    const PICKER_LIMIT = 30;

    /* Selection state. Deliberately the only mutable thing in the module -
       everything else derives from it or from a server response. */
    const state = {
        muscleId: null,
        exercise: null,
        exercises: [],
        recents: [],
        cursor: null,
        requestId: 0,
        sets: []
    };

    const el = {};
    let searchTimer = null;

    function cache() {
        [
            "muscleGrid", "exerciseCard", "exerciseSearch", "exerciseList",
            "setCard", "setCardTitle", "lastSetHint", "setForm", "weight", "reps",
            "comments", "addSetBtn", "sessionList", "summaryBar",
            "summarySets", "summaryVolume", "summaryElapsed"
        ].forEach(function (id) { el[id] = document.getElementById(id); });
    }

    // ============================================================
    // FORMATTING
    // ============================================================

    function epley1rm(weight, reps) {
        return weight * (1 + reps / 30);
    }

    function formatWeight(value) {
        const number = Number(value);
        return (Number.isInteger(number) ? number : number.toFixed(1)) + " kg";
    }

    function formatElapsed(fromIso) {
        const start = new Date(fromIso);
        if (Number.isNaN(start.getTime())) return "—";

        const minutes = Math.max(0, Math.round((Date.now() - start.getTime()) / 60000));
        if (minutes < 60) return minutes + " min";
        return Math.floor(minutes / 60) + "h " + (minutes % 60) + "m";
    }

    // ============================================================
    // STEP 1 - MUSCLE GRID
    // ============================================================

    function buildMuscleCard(muscle) {
        const card = document.createElement("button");
        card.type = "button";
        card.className = "muscle-card";
        card.setAttribute("role", "radio");
        card.setAttribute("aria-checked", "false");
        card.dataset.muscleId = muscle.muscle_id;

        const image = document.createElement("img");
        image.className = "muscle-card__image";
        image.src = muscle.image_path;
        image.alt = "";
        image.width = 64;
        image.height = 64;
        image.loading = "lazy";

        const name = document.createElement("span");
        name.className = "muscle-card__name";
        name.textContent = muscle.muscle_name;

        card.appendChild(image);
        card.appendChild(name);
        card.addEventListener("click", function () { selectMuscle(muscle); });
        return card;
    }

    async function loadMuscles() {
        window.ui.renderSkeleton(el.muscleGrid, { rows: 4, parts: ["text"] });

        try {
            const payload = await window.api.get("/muscles");
            el.muscleGrid.replaceChildren();
            payload.data.forEach(function (muscle) {
                el.muscleGrid.appendChild(buildMuscleCard(muscle));
            });
        } catch (error) {
            window.ui.renderErrorState(el.muscleGrid, error, loadMuscles);
        }
    }

    /* The muscle grid is a filter, not a gate. Clicking the selected group
       again clears it, which is the only way back to searching all 2,924
       without reloading the page. */
    async function selectMuscle(muscle) {
        const wasSelected = state.muscleId === muscle.muscle_id;
        state.muscleId = wasSelected ? null : muscle.muscle_id;
        state.exercise = null;

        el.muscleGrid.querySelectorAll(".muscle-card").forEach(function (card) {
            const isChosen = Number(card.dataset.muscleId) === state.muscleId;
            card.classList.toggle("is-selected", isChosen);
            card.setAttribute("aria-checked", String(isChosen));
        });

        el.exerciseCard.classList.remove("is-hidden");
        el.setCard.classList.add("is-hidden");
        el.exerciseSearch.value = "";

        await fetchExercises();
        el.exerciseCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    // ============================================================
    // STEP 2 - EXERCISE PICKER
    // ============================================================

    /* Searching moved to the server with the 2,900-row import. Quads alone
       holds 646 exercises and Core 661, so the old approach - fetch the whole
       group, filter in memory - meant a payload of hundreds of rows with their
       descriptions, and hundreds of DOM nodes, before the user typed anything.
       The server already has the index for this; the page asks it. */
    async function fetchExercises(append) {
        const ticket = ++state.requestId;
        const params = new URLSearchParams({ limit: String(PICKER_LIMIT) });

        if (state.muscleId !== null) params.set("muscle_id", String(state.muscleId));

        const query = el.exerciseSearch.value.trim();
        if (query) params.set("q", query);

        if (append && state.cursor) {
            params.set("after", state.cursor[0]);
            params.set("after_2", state.cursor[1]);
        }

        try {
            const payload = await window.api.get("/exercises?" + params.toString());
            if (ticket !== state.requestId) return;   // a later keystroke won

            state.exercises = append ? state.exercises.concat(payload.data) : payload.data;
            state.cursor = payload.meta.next;
            renderExercises(query);
        } catch (error) {
            if (ticket !== state.requestId) return;
            window.ui.showToast(error.message, "error");
        }
    }

    function buildOption(exercise, isRecent) {
        const option = document.createElement("button");
        option.type = "button";
        option.className = "option";
        option.setAttribute("role", "radio");
        option.dataset.exerciseId = String(exercise.exercise_id);
        option.setAttribute("aria-checked",
            String(Boolean(state.exercise) &&
                   state.exercise.exercise_id === exercise.exercise_id));

        const name = document.createElement("span");
        name.className = "option__name";
        name.textContent = exercise.exercise_name;

        const badge = document.createElement("span");
        badge.className = isRecent ? "badge badge--gold" : "badge";
        badge.textContent = isRecent ? "Recent" : (exercise.equipment || "Bodyweight");

        option.appendChild(name);
        option.appendChild(badge);
        option.addEventListener("click", function () { selectExercise(exercise); });
        return option;
    }

    /* Recents sit above the results, and only when nothing is being searched
       or filtered - once the user is looking for something specific, a fixed
       list at the top is noise between them and their answer. */
    function renderExercises(query) {
        el.exerciseList.replaceChildren();

        const showRecents = !query && state.muscleId === null && state.recents.length > 0;
        if (showRecents) {
            const heading = document.createElement("p");
            heading.className = "option-list__heading";
            heading.textContent = "Recent";
            el.exerciseList.appendChild(heading);
            state.recents.forEach(function (exercise) {
                el.exerciseList.appendChild(buildOption(exercise, true));
            });

            const rest = document.createElement("p");
            rest.className = "option-list__heading";
            rest.textContent = "All exercises";
            el.exerciseList.appendChild(rest);
        }

        if (state.exercises.length === 0) {
            const empty = document.createElement("p");
            empty.className = "text-muted";
            empty.textContent = query
                ? "No exercises match “" + query + "”."
                : "No exercises in this group.";
            el.exerciseList.appendChild(empty);
            return;
        }

        state.exercises.forEach(function (exercise) {
            el.exerciseList.appendChild(buildOption(exercise, false));
        });

        if (state.cursor) {
            const more = document.createElement("button");
            more.type = "button";
            more.className = "btn btn--ghost btn--sm option-list__more";
            more.textContent = "Show more";
            more.addEventListener("click", function () { fetchExercises(true); });
            el.exerciseList.appendChild(more);
        }
    }

    async function selectExercise(exercise) {
        state.exercise = exercise;

        // Matched on the id rather than the rendered name: with 2,924 rows the
        // same name legitimately exists under more than one muscle group.
        el.exerciseList.querySelectorAll(".option").forEach(function (option) {
            const isChosen = Number(option.dataset.exerciseId) === exercise.exercise_id;
            option.classList.toggle("is-selected", isChosen);
            option.setAttribute("aria-checked", String(isChosen));
        });

        el.setCardTitle.textContent = exercise.exercise_name;
        el.setCard.classList.remove("is-hidden");
        el.setCard.scrollIntoView({ behavior: "smooth", block: "nearest" });

        await prefillFromLastSet(exercise.exercise_id);
        el.weight.focus();
    }

    async function prefillFromLastSet(exerciseId) {
        el.lastSetHint.textContent = "";

        try {
            const payload = await window.api.get(
                "/exercises/" + exerciseId + "/last-set"
            );
            const last = payload.data;

            if (!last) {
                el.weight.value = "";
                el.reps.value = "";
                el.lastSetHint.textContent = "First time logging this one.";
                return;
            }

            el.weight.value = Number(last.weight);
            el.reps.value = last.reps;
            el.lastSetHint.textContent = "Last time: " +
                formatWeight(last.weight) + " × " + last.reps;
        } catch (error) {
            // A missing prefill is a convenience, not a failure - the user can
            // still type the numbers.
            el.lastSetHint.textContent = "";
        }
    }

    // ============================================================
    // STEP 3 - SET ENTRY
    // ============================================================

    function wireSteppers() {
        document.querySelectorAll(".stepper__btn").forEach(function (button) {
            button.addEventListener("click", function () {
                const input = document.getElementById(button.dataset.target);
                const step = Number(button.dataset.step);
                const min = Number(input.min);
                const max = Number(input.max);

                const next = (Number(input.value) || 0) + step;
                input.value = Math.min(max, Math.max(min, Math.round(next * 10) / 10));
                input.dispatchEvent(new Event("input", { bubbles: true }));
            });
        });
    }

    function validate() {
        const problems = {};
        const weight = Number(el.weight.value);
        const reps = Number(el.reps.value);

        if (!state.exercise) {
            problems.form = "Pick an exercise first.";
        }
        if (el.weight.value === "" || Number.isNaN(weight)) {
            problems.weight = "Enter a weight.";
        } else if (weight < WEIGHT_MIN || weight > WEIGHT_MAX) {
            problems.weight = "Weight must be between 0 and 500 kg.";
        } else if (Math.abs(weight * 10 - Math.round(weight * 10)) > 1e-9) {
            problems.weight = "One decimal place at most.";
        }

        if (el.reps.value === "" || Number.isNaN(reps)) {
            problems.reps = "Enter your reps.";
        } else if (!Number.isInteger(reps)) {
            problems.reps = "Whole reps only.";
        } else if (reps < REPS_MIN || reps > REPS_MAX) {
            problems.reps = "Reps must be between 1 and 100.";
        }

        if (el.comments.value.length > COMMENT_MAX) {
            problems.comments = "Keep comments under " + COMMENT_MAX + " characters.";
        }
        return problems;
    }

    async function submitSet(event) {
        event.preventDefault();
        window.ui.clearFieldErrors(el.setForm);

        /* Offline: warn and keep the form, rather than queueing the set to
           replay later. Three reasons a queue would be worse here:

           - POST /api/log-workout is not idempotent, so a replayed queue can
             insert the same set twice.
           - workout_date is the server's CURDATE(). A set queued at 11pm and
             replayed next morning lands on the wrong day, corrupting the very
             streak the queue was meant to protect.
           - the form is already optimistic, so a queue would show a row that
             looks saved and might fail hours later with nobody watching.

           Warning costs nothing: every value stays in the form and one tap
           resends it. Queueing needs an idempotency key on the endpoint and a
           client-supplied date before it would be safe. */
        if (!navigator.onLine) {
            document.getElementById("formError").textContent =
                "You're offline, so this set wasn't saved. Your entry is still " +
                "here — tap Add Set again once you reconnect.";
            window.ui.showToast("Offline — set not saved.", "warning");
            return;
        }

        const problems = validate();
        if (Object.keys(problems).length > 0) {
            Object.keys(problems).forEach(function (key) {
                if (key === "form") document.getElementById("formError").textContent = problems[key];
                else window.ui.setFieldError(key, problems[key]);
            });
            window.ui.focusFirstError(el.setForm);
            return;
        }

        const draft = {
            set_id: null,                       // assigned by the server
            pending: true,
            exercise_name: state.exercise.exercise_name,
            weight: Number(el.weight.value),
            reps: Number(el.reps.value),
            comments: el.comments.value.trim(),
            created_at: new Date().toISOString()
        };

        // Optimistic: the row appears now and is reconciled below.
        state.sets.push(draft);
        renderSession();
        window.ui.setLoading(el.addSetBtn, true);

        try {
            const payload = await window.api.post("/log-workout", {
                exercise_id: state.exercise.exercise_id,
                weight: draft.weight,
                reps: draft.reps,
                comments: draft.comments
            });

            draft.set_id = payload.data.set_id;
            draft.pending = false;
            el.comments.value = "";
            window.ui.showToast("Set logged.", "success");
        } catch (error) {
            // Roll the optimistic row back out; the entry itself stays in the
            // form so nothing has to be retyped.
            state.sets = state.sets.filter(function (row) { return row !== draft; });
            window.ui.showToast(error.message, "error");
            if (error.field) window.ui.setFieldError(error.field, error.message);
        } finally {
            window.ui.setLoading(el.addSetBtn, false);
            renderSession();
        }
    }

    // ============================================================
    // SESSION LIST
    // ============================================================

    async function removeSet(row) {
        const confirmed = await window.ui.confirmDialog({
            title: "Delete this set?",
            body: row.exercise_name + " — " + formatWeight(row.weight) + " × " + row.reps,
            confirmLabel: "Delete",
            danger: true
        });
        if (!confirmed) return;

        const index = state.sets.indexOf(row);
        state.sets = state.sets.filter(function (item) { return item !== row; });
        renderSession();

        try {
            await window.api.del("/workout-sets/" + row.set_id);
            window.ui.showToast("Set deleted.", "success");
        } catch (error) {
            state.sets.splice(index, 0, row);       // put it back where it was
            renderSession();
            window.ui.showToast(error.message, "error");
        }
    }

    function buildSetRow(row, position) {
        const item = document.createElement("div");
        item.className = "session-row" + (row.pending ? " is-pending" : "");

        const number = document.createElement("span");
        number.className = "session-row__number";
        number.textContent = position;

        const body = document.createElement("div");
        body.className = "session-row__body";

        const name = document.createElement("span");
        name.className = "session-row__exercise";
        name.textContent = row.exercise_name;

        const detail = document.createElement("span");
        detail.className = "session-row__detail";
        detail.textContent = formatWeight(row.weight) + " × " + row.reps + " reps · " +
                             "1RM ≈ " + Math.round(epley1rm(Number(row.weight), row.reps)) + " kg";

        body.appendChild(name);
        body.appendChild(detail);

        item.appendChild(number);
        item.appendChild(body);

        if (row.pending) {
            const badge = document.createElement("span");
            badge.className = "badge";
            badge.textContent = "Saving…";
            item.appendChild(badge);
        } else {
            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "session-row__delete";
            remove.setAttribute("aria-label", "Delete set " + position);
            remove.textContent = "×";
            remove.addEventListener("click", function () { removeSet(row); });
            item.appendChild(remove);
        }

        return item;
    }

    function renderSession() {
        renderSummary();

        if (state.sets.length === 0) {
            window.ui.renderEmptyState(el.sessionList, {
                icon: "🏋️",
                title: "No sets yet today",
                body: "Pick a muscle group to get started."
            });
            return;
        }

        el.sessionList.replaceChildren();
        // Numbered by position, not by set_order: deleting the third set should
        // leave 1-2-3-4, not 1-2-4-5.
        state.sets.forEach(function (row, index) {
            el.sessionList.appendChild(buildSetRow(row, index + 1));
        });
    }

    function renderSummary() {
        if (state.sets.length === 0) {
            el.summaryBar.classList.add("is-hidden");
            return;
        }

        const volume = state.sets.reduce(function (total, row) {
            return total + Number(row.weight) * Number(row.reps);
        }, 0);

        el.summaryBar.classList.remove("is-hidden");
        el.summarySets.textContent = state.sets.length;
        el.summaryVolume.textContent = Math.round(volume).toLocaleString() + " kg";
        el.summaryElapsed.textContent = formatElapsed(state.sets[0].created_at);
    }

    async function loadRecents() {
        try {
            const payload = await window.api.get("/exercises/recent");
            state.recents = payload.data;
        } catch (error) {
            // Recents are a shortcut, not the feature. Losing them leaves the
            // search box and the muscle grid working exactly as before.
            state.recents = [];
        }
    }

    async function loadTodaySets() {
        try {
            const payload = await window.api.get("/today-sets");
            state.sets = payload.data.map(function (row) {
                return {
                    set_id: row.set_id,
                    pending: false,
                    exercise_name: row.exercise_name,
                    weight: Number(row.weight),
                    reps: row.reps,
                    comments: row.comments,
                    created_at: row.created_at
                };
            });
        } catch (error) {
            window.ui.showToast(error.message, "error");
        }
        renderSession();
    }

    // ============================================================
    // INIT
    // ============================================================

    /* Deep link from the exercise library: ?exercise_id=N arrives without a
       muscle, so look the exercise up to find which group to open first. */
    async function preselectFromUrl() {
        const exerciseId = new URLSearchParams(window.location.search).get("exercise_id");
        if (!exerciseId) return;

        try {
            const payload = await window.api.get(
                "/exercises/" + encodeURIComponent(exerciseId)
            );
            const exercise = payload.data.exercise;

            // The detail response is the whole exercise, so select it directly.
            // Hunting for it in the fetched page would miss whenever the target
            // sits past the first 30 rows of its group - which, at 646
            // exercises for Quads, is most of them.
            await selectMuscle({ muscle_id: exercise.muscle_id });
            await selectExercise(exercise);
        } catch (error) {
            // A broken deep link is a convenience failing, not the page failing.
            window.ui.showToast("Could not open that exercise — pick it below.", "warning");
        }
    }

    async function init() {
        cache();

        const user = await window.api.requireSession();
        if (!user) return;

        wireSteppers();

        // Debounced so a search reaches the server once per pause, not once
        // per keystroke.
        el.exerciseSearch.addEventListener("input", function () {
            window.clearTimeout(searchTimer);
            state.cursor = null;
            searchTimer = window.setTimeout(function () { fetchExercises(); },
                                            SEARCH_DEBOUNCE);
        });
        el.setForm.addEventListener("submit", submitSet);

        await Promise.all([loadMuscles(), loadTodaySets(), loadRecents()]);

        // The picker is open from the start now. With recents at the top and
        // search across the whole catalogue, making the user pick a muscle
        // group first would add a step to the common case - logging the same
        // lift they logged on Monday.
        el.exerciseCard.classList.remove("is-hidden");
        await fetchExercises();

        await preselectFromUrl();

        // Elapsed time is the only thing on screen that changes on its own.
        window.setInterval(renderSummary, 30000);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
