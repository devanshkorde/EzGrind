/* Workout history - sessions grouped by date, collapsible, paginated.

   Private page: api.requireSession() bounces anonymous visitors.

   Filters live in the URL query string, so a filtered view survives a refresh
   and can be pasted to someone else. The URL is the single source of truth for
   what is on screen - nothing reads filter state out of the inputs.
*/

(function () {
    "use strict";

    const PAGE_SIZE = 20;
    const FILTER_KEYS = ["from", "to", "muscle_id", "exercise_id"];

    const state = {
        page: 1,
        sessions: [],
        total: 0,
        hasMore: false
    };

    const el = {};

    function cache() {
        [
            "filterBar", "filterFrom", "filterTo", "filterMuscle", "filterExercise",
            "clearFilters", "volumeChart", "historyList", "loadMoreBtn", "resultCount"
        ].forEach(function (id) { el[id] = document.getElementById(id); });
    }

    // ============================================================
    // URL AS STATE
    // ============================================================

    function activeFilters() {
        const params = new URLSearchParams(window.location.search);
        const filters = {};
        FILTER_KEYS.forEach(function (key) {
            const value = params.get(key);
            if (value) filters[key] = value;
        });
        return filters;
    }

    function hasFilters() {
        return Object.keys(activeFilters()).length > 0;
    }

    function writeFiltersToUrl(filters) {
        const params = new URLSearchParams();
        FILTER_KEYS.forEach(function (key) {
            if (filters[key]) params.set(key, filters[key]);
        });
        const query = params.toString();
        window.history.replaceState({}, "",
            window.location.pathname + (query ? "?" + query : ""));
    }

    function fillFilterInputs() {
        const filters = activeFilters();
        el.filterFrom.value = filters.from || "";
        el.filterTo.value = filters.to || "";
        el.filterMuscle.value = filters.muscle_id || "";
        el.filterExercise.value = filters.exercise_id || "";
    }

    function buildQuery(page) {
        const params = new URLSearchParams(activeFilters());
        params.set("page", page);
        params.set("limit", PAGE_SIZE);
        return params.toString();
    }

    // ============================================================
    // FORMATTING
    // ============================================================

    const DATE_FORMAT = new Intl.DateTimeFormat(undefined, {
        weekday: "short", day: "numeric", month: "short", year: "numeric"
    });

    /** Server sends midnight GMT; read the UTC parts so the day cannot shift. */
    function isoDay(value) {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return null;
        return [
            date.getUTCFullYear(),
            String(date.getUTCMonth() + 1).padStart(2, "0"),
            String(date.getUTCDate()).padStart(2, "0")
        ].join("-");
    }

    function formatSessionDate(value) {
        const day = isoDay(value);
        if (!day) return String(value);
        return DATE_FORMAT.format(new Date(day + "T00:00:00"));
    }

    function epley1rm(weight, reps) {
        return Math.round(weight * (1 + reps / 30));
    }

    // ============================================================
    // RENDER: SESSIONS
    // ============================================================

    /* One definition drives the header, the body and the column widths.
       The <colgroup> applies to every row in the table by definition, so a
       header and its cells cannot end up in differently sized columns. */
    const SET_COLUMNS = [
        { label: "Set", width: "8%" },
        { label: "Weight", width: "16%", unit: "kg" },
        { label: "Reps", width: "12%" },
        { label: "Est. 1RM", width: "16%", unit: "kg" },
        { label: "Notes", width: "48%" }
    ];

    /** Number and unit in one cell, but the unit styled to recede. */
    function valueCell(cell, value, unit) {
        if (value === null) {
            cell.textContent = "—";
            cell.classList.add("table__empty");
            return;
        }

        cell.textContent = String(value);
        if (unit) {
            const suffix = document.createElement("span");
            suffix.className = "table__unit";
            suffix.textContent = unit;
            cell.appendChild(suffix);
        }
    }

    function buildSetsTable(exercise) {
        const wrap = document.createElement("div");
        wrap.className = "table-wrap";

        const table = document.createElement("table");
        table.className = "table table--sets";

        // Fixed widths, so a long note cannot stretch the numeric columns.
        const group = document.createElement("colgroup");
        SET_COLUMNS.forEach(function (column) {
            const col = document.createElement("col");
            col.style.width = column.width;
            group.appendChild(col);
        });
        table.appendChild(group);

        const head = document.createElement("thead");
        const headRow = document.createElement("tr");
        SET_COLUMNS.forEach(function (column) {
            const cell = document.createElement("th");
            cell.scope = "col";
            cell.textContent = column.label;
            headRow.appendChild(cell);
        });
        head.appendChild(headRow);
        table.appendChild(head);

        const body = document.createElement("tbody");

        exercise.sets.forEach(function (set, index) {
            const row = document.createElement("tr");
            const oneRepMax = (set.weight === null || !set.reps)
                ? null : epley1rm(set.weight, set.reps);

            const values = [index + 1, set.weight, set.reps, oneRepMax, set.comments];

            SET_COLUMNS.forEach(function (column, position) {
                const cell = document.createElement("td");

                if (position === 4) {
                    cell.textContent = set.comments || "—";
                    if (!set.comments) cell.classList.add("table__empty");
                } else {
                    valueCell(cell, values[position], column.unit);
                }

                // Read back as a label by the stacked mobile layout, where the
                // header row is visually hidden.
                if (position === 3 || position === 4) {
                    cell.dataset.label = column.label;
                }

                row.appendChild(cell);
            });

            body.appendChild(row);
        });

        table.appendChild(body);
        wrap.appendChild(table);
        return wrap;
    }

    function buildSession(session, index) {
        const details = document.createElement("details");
        details.className = "session";
        // Newest session opens by default; the rest stay collapsed.
        details.open = index === 0;

        const summary = document.createElement("summary");
        summary.className = "session__summary";

        const date = document.createElement("span");
        date.className = "session__date";
        date.textContent = formatSessionDate(session.workout_date);

        const stats = document.createElement("span");
        stats.className = "session__stats";

        const parts = [
            session.total_sets + (session.total_sets === 1 ? " set" : " sets"),
            Math.round(session.total_volume).toLocaleString() + " kg",
            session.exercise_count +
                (session.exercise_count === 1 ? " exercise" : " exercises")
        ];
        // Only shown when there is a real spread: sets logged before per-set
        // timestamps existed all share one stamp, so their duration is zero.
        if (session.duration_estimate > 0) {
            parts.push("~" + session.duration_estimate + " min");
        }

        parts.forEach(function (text) {
            const badge = document.createElement("span");
            badge.className = "badge";
            badge.textContent = text;
            stats.appendChild(badge);
        });

        summary.appendChild(date);
        summary.appendChild(stats);
        details.appendChild(summary);

        const body = document.createElement("div");
        body.className = "session__body";

        session.exercises.forEach(function (exercise) {
            const block = document.createElement("div");
            block.className = "session__exercise";

            const heading = document.createElement("h3");
            heading.className = "session__exercise-name";
            heading.textContent = exercise.exercise_name;

            const muscle = document.createElement("span");
            muscle.className = "badge badge--gold";
            muscle.textContent = exercise.muscle_name;
            heading.appendChild(muscle);

            block.appendChild(heading);
            block.appendChild(buildSetsTable(exercise));
            body.appendChild(block);
        });

        details.appendChild(body);
        return details;
    }

    function renderSessions() {
        if (state.sessions.length === 0) {
            renderEmpty();
            return;
        }

        // One mutation for the whole list rather than one per session.
        el.historyList.replaceChildren.apply(el.historyList,
            state.sessions.map(buildSession));

        el.loadMoreBtn.classList.toggle("is-hidden", !state.hasMore);
        el.resultCount.textContent = state.sessions.length + " of " +
            state.total + (state.total === 1 ? " session" : " sessions");
    }

    function renderEmpty() {
        el.loadMoreBtn.classList.add("is-hidden");
        el.resultCount.textContent = "";

        // Two genuinely different situations: nothing logged ever, versus
        // nothing matching the current filters.
        if (hasFilters()) {
            window.ui.renderEmptyState(el.historyList, {
                icon: "🔍",
                title: "No sessions match these filters",
                body: "Try a wider date range, or clear the filters to see everything.",
                actionLabel: "Clear filters",
                onAction: clearFilters
            });
            return;
        }

        window.ui.renderEmptyState(el.historyList, {
            icon: "📓",
            title: "No workouts logged yet",
            body: "Your sessions will appear here once you log your first set.",
            actionLabel: "Log a workout",
            onAction: function () { window.location.href = "log-workout.html"; }
        });
    }

    function renderSkeletons() {
        window.ui.renderSkeleton(el.historyList,
            { rows: 3, parts: ["title", "text", "text"], card: true });
        // The chart occupies real height, so it gets a placeholder too rather
        // than collapsing and shoving the list up.
        window.ui.renderSkeleton(el.volumeChart, { rows: 1, parts: ["chart"] });
    }

    // ============================================================
    // RENDER: CHART
    // ============================================================

    function renderChart() {
        // Oldest first: time runs left to right.
        const points = state.sessions
            .map(function (session) {
                return { date: isoDay(session.workout_date), volume: session.total_volume };
            })
            .filter(function (point) { return point.date !== null; })
            .reverse();

        window.charts.volumeOverTime(el.volumeChart, points);
    }

    // ============================================================
    // DATA
    // ============================================================

    async function load(page, append) {
        // No skeleton flash on refetch: the existing render dims instead, so
        // nothing jumps and the reader keeps their place.
        if (append || state.sessions.length > 0) {
            el.historyList.classList.add("is-refetching");
        } else {
            renderSkeletons();
        }

        try {
            const payload = await window.api.get("/workout-history?" + buildQuery(page));

            state.page = payload.meta.page;
            state.total = payload.meta.total;
            state.hasMore = payload.meta.has_more;
            state.sessions = append
                ? state.sessions.concat(payload.data)
                : payload.data;

            renderSessions();
            renderChart();
        } catch (error) {
            // Only a first load gets the error state; a failed "load more"
            // should not replace the sessions already on screen.
            if (state.sessions.length === 0) {
                window.ui.renderErrorState(el.historyList, error, function () {
                    load(page, append);
                });
                window.charts.volumeOverTime(el.volumeChart, []);
            } else {
                window.ui.showToast(error.message, "error");
            }
        } finally {
            el.historyList.classList.remove("is-refetching");
        }
    }

    async function loadFilterOptions() {
        try {
            const [muscles, exercises] = await Promise.all([
                window.api.get("/muscles"),
                window.api.get("/exercises")
            ]);

            muscles.data.forEach(function (muscle) {
                const option = document.createElement("option");
                option.value = muscle.muscle_id;
                option.textContent = muscle.muscle_name;
                el.filterMuscle.appendChild(option);
            });

            exercises.data.forEach(function (exercise) {
                const option = document.createElement("option");
                option.value = exercise.exercise_id;
                option.textContent = exercise.exercise_name;
                el.filterExercise.appendChild(option);
            });

            fillFilterInputs();
        } catch (error) {
            window.ui.showToast(error.message, "error");
        }
    }

    function applyFilters(event) {
        if (event) event.preventDefault();

        writeFiltersToUrl({
            from: el.filterFrom.value,
            to: el.filterTo.value,
            muscle_id: el.filterMuscle.value,
            exercise_id: el.filterExercise.value
        });

        state.sessions = [];
        load(1, false);
    }

    function clearFilters() {
        writeFiltersToUrl({});
        fillFilterInputs();
        state.sessions = [];
        load(1, false);
    }

    // ============================================================
    // INIT
    // ============================================================

    async function init() {
        cache();

        const user = await window.api.requireSession();
        if (!user) return;

        el.filterBar.addEventListener("submit", applyFilters);
        el.clearFilters.addEventListener("click", clearFilters);
        el.loadMoreBtn.addEventListener("click", function () {
            load(state.page + 1, true);
        });

        await loadFilterOptions();
        await load(1, false);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
