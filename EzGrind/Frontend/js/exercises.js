/* Exercise library - filterable catalogue with a detail dialog.

   Public page. The catalogue is the same for everyone; the "your numbers"
   section of the detail panel appears only for a signed-in user and is scoped
   server-side to that session.

   Filters live in the URL query string, so a filtered view survives a refresh
   and can be shared. The URL is the source of truth - nothing reads filter
   state back out of the controls.
*/

(function () {
    "use strict";

    const SEARCH_DEBOUNCE = 250;
    const SORTS = ["name", "muscle"];

    const el = {};
    let searchTimer = null;

    /* Paging state. `cursor` is whatever the last response put in meta.next -
       the client never builds one, it only hands back what it was given.
       `requestId` exists because a slow reply must not overwrite a newer one:
       type "bench", then "squat", and the bench response may still land last. */
    let cursor = null;
    let requestId = 0;

    function cache() {
        [
            "filterBar", "searchInput", "muscleChips", "equipmentSelect",
            "difficultySelect", "typeSelect", "sortSelect", "clearFilters",
            "resultCount", "exerciseGrid", "loadMoreWrap", "loadMoreBtn"
        ].forEach(function (id) { el[id] = document.getElementById(id); });
    }

    // ============================================================
    // URL AS STATE
    // ============================================================

    function readFilters() {
        const params = new URLSearchParams(window.location.search);
        const muscles = (params.get("muscle_id") || "")
            .split(",")
            .map(function (value) { return value.trim(); })
            .filter(Boolean);

        return {
            q: params.get("q") || "",
            muscle_id: muscles,
            equipment: params.get("equipment") || "",
            difficulty: params.get("difficulty") || "",
            type: params.get("type") || "",
            sort: SORTS.includes(params.get("sort")) ? params.get("sort") : "name"
        };
    }

    function writeFilters(filters) {
        const params = new URLSearchParams();
        if (filters.q) params.set("q", filters.q);
        if (filters.muscle_id.length) params.set("muscle_id", filters.muscle_id.join(","));
        if (filters.equipment) params.set("equipment", filters.equipment);
        if (filters.difficulty) params.set("difficulty", filters.difficulty);
        if (filters.type) params.set("type", filters.type);
        if (filters.sort && filters.sort !== "name") params.set("sort", filters.sort);

        const query = params.toString();
        window.history.replaceState({}, "",
            window.location.pathname + (query ? "?" + query : ""));
    }

    function syncControls() {
        const filters = readFilters();
        el.searchInput.value = filters.q;
        el.equipmentSelect.value = filters.equipment;
        el.difficultySelect.value = filters.difficulty;
        el.typeSelect.value = filters.type;
        el.sortSelect.value = filters.sort;

        el.muscleChips.querySelectorAll(".chip").forEach(function (chip) {
            chip.setAttribute("aria-pressed",
                String(filters.muscle_id.includes(chip.dataset.muscleId)));
        });
    }

    // ============================================================
    // CARDS
    // ============================================================

    function buildCard(exercise) {
        const card = document.createElement("article");
        card.className = "exercise-card card--interactive";
        card.tabIndex = 0;
        card.setAttribute("role", "button");
        card.setAttribute("aria-label",
            exercise.exercise_name + ", " + exercise.muscle_name + ". View details.");

        // Fixed box behind the image so the grid keeps its geometry before
        // anything loads - no reflow as images arrive.
        const frame = document.createElement("div");
        frame.className = "exercise-card__frame";

        const image = document.createElement("img");
        image.className = "exercise-card__image";
        image.src = exercise.image_path;
        image.alt = "";
        image.width = 88;
        image.height = 88;
        image.loading = "lazy";
        image.decoding = "async";
        frame.appendChild(image);

        const name = document.createElement("h2");
        name.className = "exercise-card__name";
        name.textContent = exercise.exercise_name;

        const badges = document.createElement("div");
        badges.className = "exercise-card__badges";

        const muscle = document.createElement("span");
        muscle.className = "badge badge--gold";
        muscle.textContent = exercise.muscle_name;

        const equipment = document.createElement("span");
        equipment.className = "badge";
        equipment.textContent = exercise.equipment || "Bodyweight";

        badges.appendChild(muscle);
        badges.appendChild(equipment);

        card.appendChild(frame);
        card.appendChild(name);
        card.appendChild(badges);

        function open() { openDetail(exercise.exercise_id, card); }

        card.addEventListener("click", open);
        card.addEventListener("keydown", function (event) {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                open();
            }
        });

        return card;
    }

    /* The count is the server's total for the whole filtered set, not the
       length of this page. With 2,924 rows behind a Load more button, "24
       exercises" would be a lie about how much is there. */
    function renderGrid(exercises, total) {
        const shown = total === undefined ? exercises.length : total;
        el.resultCount.textContent = shown.toLocaleString() +
            (shown === 1 ? " exercise" : " exercises");

        if (exercises.length === 0) {
            el.resultCount.textContent = "";
            window.ui.renderEmptyState(el.exerciseGrid, {
                icon: "🔍",
                title: "Nothing matches those filters",
                body: "Try a different muscle group, or clear the filters to see everything.",
                actionLabel: "Clear filters",
                onAction: clearFilters
            });
            return;
        }

        // One DOM mutation for the whole grid rather than one per card.
        el.exerciseGrid.replaceChildren.apply(el.exerciseGrid, exercises.map(buildCard));
    }

    function appendCards(exercises) {
        const batch = document.createDocumentFragment();
        exercises.forEach(function (exercise) { batch.appendChild(buildCard(exercise)); });
        el.exerciseGrid.appendChild(batch);
    }

    function renderSkeletons() {
        el.exerciseGrid.replaceChildren();
        for (let index = 0; index < 8; index++) {
            const card = document.createElement("div");
            card.className = "exercise-card";
            const frame = document.createElement("div");
            frame.className = "exercise-card__frame skeleton";
            card.appendChild(frame);
            ["title", "text"].forEach(function (part) {
                const line = document.createElement("span");
                line.className = "skeleton skeleton--" + part;
                card.appendChild(line);
            });
            el.exerciseGrid.appendChild(card);
        }
    }

    // ============================================================
    // DETAIL DIALOG
    // ============================================================

    function statLine(label, value) {
        const row = document.createElement("div");
        row.className = "profile-item";

        const term = document.createElement("span");
        term.className = "profile-item__label";
        term.textContent = label;

        const detail = document.createElement("span");
        detail.className = "profile-item__value";
        detail.textContent = value;

        row.appendChild(term);
        row.appendChild(detail);
        return row;
    }

    function formatDate(value) {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "—";
        return new Intl.DateTimeFormat(undefined, {
            day: "numeric", month: "short", year: "numeric", timeZone: "UTC"
        }).format(date);
    }

    function buildHistorySection(history) {
        const section = document.createElement("div");
        section.className = "detail__section";

        const heading = document.createElement("h3");
        heading.className = "detail__heading";
        heading.textContent = "Your numbers";
        section.appendChild(heading);

        if (history === null) {
            const prompt = document.createElement("p");
            prompt.className = "text-muted";
            prompt.textContent = "Sign in to see your numbers on this lift.";
            section.appendChild(prompt);

            const link = document.createElement("a");
            link.className = "btn btn--secondary btn--sm";
            link.href = "login.html";
            link.textContent = "Log in";
            section.appendChild(link);
            return section;
        }

        if (history.total_sets === 0) {
            const none = document.createElement("p");
            none.className = "text-muted";
            none.textContent = "You have not logged this exercise yet.";
            section.appendChild(none);
            return section;
        }

        const list = document.createElement("div");
        list.className = "profile-list";
        list.appendChild(statLine("Total sets", history.total_sets));
        list.appendChild(statLine("Last performed", formatDate(history.last_performed)));

        if (history.best_set) {
            list.appendChild(statLine("Best set",
                history.best_set.weight + " kg × " + history.best_set.reps));
            list.appendChild(statLine("Estimated 1RM",
                Math.round(history.estimated_1rm) + " kg"));
        }

        section.appendChild(list);

        if (history.recent_sets.length > 0) {
            const recentHeading = document.createElement("h4");
            recentHeading.className = "detail__subheading";
            recentHeading.textContent = "Recent sets";
            section.appendChild(recentHeading);

            const recent = document.createElement("div");
            recent.className = "today__list";
            history.recent_sets.forEach(function (set) {
                const row = document.createElement("div");
                row.className = "today__item";

                const when = document.createElement("span");
                when.textContent = formatDate(set.workout_date);

                const what = document.createElement("span");
                what.className = "badge";
                what.textContent = (set.weight === null ? "—" : set.weight + " kg") +
                                   " × " + set.reps;

                row.appendChild(when);
                row.appendChild(what);
                recent.appendChild(row);
            });
            section.appendChild(recent);
        }

        return section;
    }

    function buildDetailPanel(exercise, history, dialogRef) {
        const panel = document.createElement("div");
        panel.className = "modal__panel modal__panel--wide";

        const close = document.createElement("button");
        close.type = "button";
        close.className = "dialog__close";
        close.setAttribute("aria-label", "Close");
        close.textContent = "×";
        close.addEventListener("click", function () { dialogRef.current.close("close"); });
        panel.appendChild(close);

        const header = document.createElement("div");
        header.className = "detail__header";

        const image = document.createElement("img");
        image.className = "detail__image";
        image.src = exercise.image_path;
        image.alt = "";
        image.width = 72;
        image.height = 72;

        const headings = document.createElement("div");

        const title = document.createElement("h2");
        title.className = "modal__title";
        title.textContent = exercise.exercise_name;

        const badges = document.createElement("div");
        badges.className = "cluster";

        const muscle = document.createElement("span");
        muscle.className = "badge badge--gold";
        muscle.textContent = exercise.muscle_name;

        const equipment = document.createElement("span");
        equipment.className = "badge";
        equipment.textContent = exercise.equipment || "Bodyweight";

        badges.appendChild(muscle);
        badges.appendChild(equipment);

        // Imported metadata, absent on plenty of rows. A missing badge is
        // better than a badge reading "null".
        [exercise.difficulty_level, exercise.exercise_type].forEach(function (value) {
            if (!value) return;
            const badge = document.createElement("span");
            badge.className = "badge";
            badge.textContent = value;
            badges.appendChild(badge);
        });

        headings.appendChild(title);
        headings.appendChild(badges);

        header.appendChild(image);
        header.appendChild(headings);
        panel.appendChild(header);

        /* Over half the imported catalogue has no description. Saying so is
           better than a panel that just stops after the badges - silence reads
           as a bug, an explicit line reads as a fact about the data. */
        const description = document.createElement("p");
        if (exercise.description) {
            description.className = "detail__description";
            description.textContent = exercise.description;
        } else {
            description.className = "detail__description text-muted";
            description.textContent = "No description available for this exercise.";
        }
        panel.appendChild(description);

        panel.appendChild(buildHistorySection(history));

        const action = document.createElement("a");
        action.className = "btn btn--primary btn--block";
        action.href = "log-workout.html?exercise_id=" + exercise.exercise_id;
        action.textContent = "Log this exercise";
        panel.appendChild(action);

        return panel;
    }

    async function openDetail(exerciseId, originCard) {
        try {
            const payload = await window.api.get("/exercises/" + exerciseId);
            const exercise = payload.data.exercise;

            // The panel needs the dialog to close itself, and the dialog needs
            // the panel to exist. A one-field holder breaks the cycle.
            const dialogRef = { current: null };
            const panel = buildDetailPanel(exercise, payload.data.history, dialogRef);

            dialogRef.current = window.ui.openDialog(panel, {
                label: exercise.exercise_name,
                onClose: function () {
                    // Native <dialog> restores focus on its own, but the card
                    // may have been replaced by a re-render in the meantime.
                    if (originCard && originCard.isConnected) originCard.focus();
                }
            });
        } catch (error) {
            window.ui.showToast(error.message, "error");
        }
    }

    // ============================================================
    // DATA
    // ============================================================

    function buildQuery(nextCursor) {
        const filters = readFilters();
        const params = new URLSearchParams();
        if (filters.q) params.set("q", filters.q);
        if (filters.muscle_id.length) params.set("muscle_id", filters.muscle_id.join(","));
        if (filters.equipment) params.set("equipment", filters.equipment);
        if (filters.difficulty) params.set("difficulty", filters.difficulty);
        if (filters.type) params.set("type", filters.type);
        params.set("sort", filters.sort);

        // Both halves or neither - the server ignores half a cursor, and
        // sending one would quietly page from the top.
        if (nextCursor) {
            params.set("after", nextCursor[0]);
            params.set("after_2", nextCursor[1]);
        }
        return params.toString();
    }

    function showLoadMore(hasMore) {
        el.loadMoreWrap.hidden = !hasMore;
    }

    /* Two entry points, one request. `load` replaces the grid and reads the
       total; `loadMore` appends and leaves the total alone, because the server
       only counts on the first page. */
    async function load() {
        const ticket = ++requestId;
        cursor = null;
        showLoadMore(false);
        renderSkeletons();

        try {
            const payload = await window.api.get("/exercises?" + buildQuery(null));
            if (ticket !== requestId) return;      // a newer search already won

            cursor = payload.meta.next;
            renderGrid(payload.data, payload.meta.total);
            showLoadMore(Boolean(cursor));
        } catch (error) {
            if (ticket !== requestId) return;
            el.resultCount.textContent = "";
            window.ui.renderErrorState(el.exerciseGrid, error, load);
        }
    }

    async function loadMore() {
        if (!cursor) return;

        const ticket = requestId;
        const pending = cursor;
        window.ui.setLoading(el.loadMoreBtn, true);

        try {
            const payload = await window.api.get("/exercises?" + buildQuery(pending));
            if (ticket !== requestId) return;      // filters changed mid-flight

            appendCards(payload.data);
            cursor = payload.meta.next;
            showLoadMore(Boolean(cursor));
        } catch (error) {
            // The rows already on screen are still valid, so this stays a toast
            // rather than replacing the grid with an error state.
            window.ui.showToast(error.message, "error");
        } finally {
            window.ui.setLoading(el.loadMoreBtn, false);
        }
    }

    async function loadFilterOptions() {
        try {
            const payload = await window.api.get("/exercise-filters");

            payload.data.muscles.forEach(function (muscle) {
                const chip = document.createElement("button");
                chip.type = "button";
                chip.className = "chip";
                chip.dataset.muscleId = String(muscle.muscle_id);
                chip.setAttribute("aria-pressed", "false");
                chip.textContent = muscle.muscle_name;
                chip.addEventListener("click", function () { toggleMuscle(chip); });
                el.muscleChips.appendChild(chip);
            });

            fillSelect(el.equipmentSelect, payload.data.equipment);
            fillSelect(el.difficultySelect, payload.data.difficulties);
            fillSelect(el.typeSelect, payload.data.types);

            syncControls();
        } catch (error) {
            window.ui.showToast(error.message, "error");
        }
    }

    function fillSelect(select, values) {
        values.forEach(function (name) {
            const option = document.createElement("option");
            option.value = name;
            option.textContent = name;
            select.appendChild(option);
        });
    }

    // ============================================================
    // CONTROLS
    // ============================================================

    function currentFromControls() {
        const pressed = Array.from(
            el.muscleChips.querySelectorAll('.chip[aria-pressed="true"]')
        ).map(function (chip) { return chip.dataset.muscleId; });

        return {
            q: el.searchInput.value.trim(),
            muscle_id: pressed,
            equipment: el.equipmentSelect.value,
            difficulty: el.difficultySelect.value,
            type: el.typeSelect.value,
            sort: el.sortSelect.value
        };
    }

    function commit() {
        writeFilters(currentFromControls());
        load();
    }

    function toggleMuscle(chip) {
        const wasPressed = chip.getAttribute("aria-pressed") === "true";
        chip.setAttribute("aria-pressed", String(!wasPressed));
        commit();
    }

    function clearFilters() {
        writeFilters({
            q: "", muscle_id: [], equipment: "",
            difficulty: "", type: "", sort: "name"
        });
        syncControls();
        load();
    }

    function wireControls() {
        // Debounced so a search reaches the server once per pause, not once
        // per keystroke.
        el.searchInput.addEventListener("input", function () {
            window.clearTimeout(searchTimer);
            searchTimer = window.setTimeout(commit, SEARCH_DEBOUNCE);
        });

        el.equipmentSelect.addEventListener("change", commit);
        el.difficultySelect.addEventListener("change", commit);
        el.typeSelect.addEventListener("change", commit);
        el.sortSelect.addEventListener("change", commit);
        el.clearFilters.addEventListener("click", clearFilters);
        el.loadMoreBtn.addEventListener("click", loadMore);

        // The bar is a <form> so Enter submits; nothing here needs a round trip
        // through a page load.
        el.filterBar.addEventListener("submit", function (event) {
            event.preventDefault();
            window.clearTimeout(searchTimer);
            commit();
        });
    }

    async function init() {
        cache();
        wireControls();
        await loadFilterOptions();
        await load();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
