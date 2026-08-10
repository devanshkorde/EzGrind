/* Landing page for signed-out visitors, dashboard for signed-in ones.

   One entry point, one /api/me (shared with shell.js through the api cache),
   one render function per view. Nothing mutable lives at module scope.

   The statistics used to be computed here from a full history download. They
   now come from /api/stats/*, so the streak arithmetic, the rolling-window
   sums and the trend comparison have all been deleted rather than left to rot
   as a second, disagreeing implementation.
*/

(function () {
    "use strict";

    const RECENT_LIMIT = 5;
    const RECENT_PAGE = 10;      // enough sessions to fill the recent list
    const PR_RECENT_DAYS = 7;    // a PR this new gets a badge

    // ============================================================
    // DATES
    // ============================================================

    function localKey(date) {
        return [
            date.getFullYear(),
            String(date.getMonth() + 1).padStart(2, "0"),
            String(date.getDate()).padStart(2, "0")
        ].join("-");
    }

    /** The API sends dates as midnight GMT, so read the UTC parts back out. */
    function serverKey(value) {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return null;
        return [
            date.getUTCFullYear(),
            String(date.getUTCMonth() + 1).padStart(2, "0"),
            String(date.getUTCDate()).padStart(2, "0")
        ].join("-");
    }

    function daysAgoKey(count) {
        const date = new Date();
        date.setDate(date.getDate() - count);
        return localKey(date);
    }

    function formatDay(key) {
        const date = new Date(key + "T00:00:00");
        if (Number.isNaN(date.getTime())) return key;
        if (key === localKey(new Date())) return "Today";
        if (key === daysAgoKey(1)) return "Yesterday";
        return date.toLocaleDateString(undefined, {
            weekday: "short", day: "numeric", month: "short"
        });
    }

    function daysSince(key) {
        const then = new Date(key + "T00:00:00");
        if (Number.isNaN(then.getTime())) return Infinity;
        return Math.floor((Date.now() - then.getTime()) / 86400000);
    }

    function firstNameOf(user) {
        const full = (user.full_name || "").trim();
        if (!full) return null;
        return full.split(/\s+/)[0];
    }

    // ============================================================
    // VIEW SWITCH
    // ============================================================

    function showView(id) {
        document.querySelectorAll("[data-view]").forEach(function (view) {
            // Removed rather than hidden: leaving both in the document would
            // leave two <h1> elements and a second nav target for the tab key.
            if (view.id === id) view.hidden = false;
            else view.remove();
        });

        // Here rather than on DOMContentLoaded: both views start hidden until
        // the session resolves, so an intro tied to page load would play to a
        // blank screen and finish before anything was visible. Guarded because
        // motion.js is optional - the page works without it.
        if (window.motion) window.motion.playIntro(id);
    }

    // ============================================================
    // STAT CARDS
    // ============================================================

    function statCard(label, value, meta) {
        const card = document.createElement("div");
        card.className = "stat-card";

        const labelNode = document.createElement("p");
        labelNode.className = "stat-card__label";
        labelNode.textContent = label;

        const valueNode = document.createElement("p");
        valueNode.className = "stat-card__value";
        valueNode.textContent = value;

        const metaNode = document.createElement("p");
        metaNode.className = "stat-card__meta";
        metaNode.textContent = meta || "";

        card.appendChild(labelNode);
        card.appendChild(valueNode);
        card.appendChild(metaNode);
        return card;
    }

    function skeletonStats(container, count) {
        container.replaceChildren();

        for (let index = 0; index < count; index++) {
            const card = document.createElement("div");
            card.className = "stat-card";
            ["label", "value", "meta"].forEach(function (part) {
                const line = document.createElement("span");
                line.className = "skeleton skeleton--" + part;
                card.appendChild(line);
            });
            container.appendChild(card);
        }
    }

    function renderStats(container, stats) {
        container.replaceChildren();

        container.appendChild(statCard(
            "Workouts this week", stats.workouts_this_week, "last 7 days"));

        container.appendChild(statCard(
            "Total volume",
            Math.round(stats.total_volume_kg).toLocaleString() + " kg",
            "all time"));

        container.appendChild(statCard(
            "Total workouts", stats.total_workouts,
            stats.workouts_this_month + " this month"));

        container.appendChild(statCard(
            "Sets per workout", stats.avg_sets_per_workout,
            stats.favourite_muscle_group
                ? "most trained: " + stats.favourite_muscle_group
                : "average"));
    }

    // ============================================================
    // STREAK
    // ============================================================

    function renderStreak(container, stats) {
        container.replaceChildren();

        const alive = stats.current_streak > 0;

        const figure = document.createElement("div");
        figure.className = "streak__figure";

        const current = document.createElement("p");
        current.className = "streak__value";
        current.textContent = stats.current_streak;

        const unit = document.createElement("p");
        unit.className = "streak__unit";
        unit.textContent = stats.current_streak === 1 ? "day" : "days";

        figure.appendChild(current);
        figure.appendChild(unit);

        const dots = document.createElement("div");
        dots.className = "streak__dots";
        dots.setAttribute("role", "img");
        dots.setAttribute("aria-label", stats.week_activity.filter(function (day) {
            return day.trained;
        }).length + " of the last 7 days trained.");

        const todayKey = localKey(new Date());
        stats.week_activity.forEach(function (day) {
            const dot = document.createElement("span");
            dot.className = "streak__dot";
            if (day.trained) dot.classList.add("is-filled");
            // The pulse marks today, and only while the streak is actually
            // alive - a pulsing dot on a broken streak would be misleading.
            if (day.date === todayKey && alive) dot.classList.add("is-today");
            dot.title = day.date;
            dots.appendChild(dot);
        });

        const longest = document.createElement("p");
        longest.className = "streak__longest";
        longest.textContent = stats.longest_streak > 0
            ? "Longest streak: " + stats.longest_streak +
              (stats.longest_streak === 1 ? " day" : " days")
            : "No streak yet — log a set to start one.";

        container.appendChild(figure);
        container.appendChild(dots);
        container.appendChild(longest);
    }

    // ============================================================
    // BODYWEIGHT
    // ============================================================

    /* Whether a change is good depends on what the user said they wanted, not
       on the direction. Down is only progress if they are trying to lose. */
    const GOAL_DIRECTION = {
        gain: 1,       // heavier is toward the goal
        muscle: 1,
        lose: -1,      // lighter is toward the goal
        maintain: 0    // either direction away from flat is drift
    };

    const MAINTAIN_TOLERANCE_KG = 1;

    /**
     * @returns {{tone: string, note: string}} tone is "success", "warning" or "".
     */
    function judgeWeightChange(change, goal) {
        const direction = GOAL_DIRECTION[goal];

        // No stated goal means no opinion. Showing a colour here would be the
        // app inventing a target the user never set.
        if (direction === undefined) {
            return { tone: "", note: "Set a fitness goal to track progress." };
        }

        if (direction === 0) {
            return Math.abs(change) <= MAINTAIN_TOLERANCE_KG
                ? { tone: "success", note: "Holding steady." }
                : { tone: "warning", note: "Drifting from maintenance." };
        }

        if (change === 0) return { tone: "", note: "No change over 30 days." };

        const towardGoal = (change > 0) === (direction > 0);
        return towardGoal
            ? { tone: "success", note: "Moving toward your goal." }
            : { tone: "warning", note: "Moving away from your goal." };
    }

    function renderWeight(container, stats, goal) {
        container.replaceChildren();

        if (stats.current_weight === null || stats.current_weight === undefined) {
            const prompt = document.createElement("p");
            prompt.className = "text-muted";
            prompt.textContent = "Log your weight below to start tracking it.";
            container.appendChild(prompt);
            return;
        }

        const value = document.createElement("p");
        value.className = "weight-card__value";
        value.textContent = stats.current_weight + " kg";
        container.appendChild(value);

        const change = stats.weight_change_30d;

        // null means "not enough history to say", which is not the same as 0.
        if (change === null || change === undefined) {
            const pending = document.createElement("p");
            pending.className = "stat-card__meta";
            pending.textContent = "Log again in a few days to see a trend.";
            container.appendChild(pending);
            return;
        }

        const verdict = judgeWeightChange(change, goal);

        const delta = document.createElement("p");
        delta.className = "weight-card__delta";
        if (verdict.tone) delta.classList.add("weight-card__delta--" + verdict.tone);
        // Arrow and number carry the meaning; the colour only reinforces it.
        delta.textContent = (change > 0 ? "▲ +" : (change < 0 ? "▼ " : "")) +
                            change.toFixed(1) + " kg over 30 days";
        container.appendChild(delta);

        const note = document.createElement("p");
        note.className = "stat-card__meta";
        note.textContent = verdict.note;
        container.appendChild(note);

        if (stats.starting_weight !== null && stats.starting_weight !== undefined) {
            const since = document.createElement("p");
            since.className = "stat-card__meta";
            since.textContent = "Started at " + stats.starting_weight + " kg.";
            container.appendChild(since);
        }
    }

    function wireWeightForm(onLogged) {
        const form = document.getElementById("weightForm");
        const input = document.getElementById("weight_kg");
        const button = document.getElementById("weightBtn");

        form.addEventListener("submit", async function (event) {
            event.preventDefault();
            window.ui.setFieldError("weight_kg", "");

            if (!input.value.trim()) {
                window.ui.setFieldError("weight_kg", "Enter a weight first.");
                return;
            }

            window.ui.setLoading(button, true);
            try {
                await window.api.post("/weight-logs", { weight_kg: input.value });
                input.value = "";
                // The profile figure and BMI move with it, so the cached
                // session is now stale.
                window.api.clearSession();
                window.ui.showToast("Weight logged.", "success");
                await onLogged();
            } catch (error) {
                if (error.field) window.ui.setFieldError(error.field, error.message);
                else window.ui.showToast(error.message, "error");
            } finally {
                window.ui.setLoading(button, false);
            }
        });
    }

    // ============================================================
    // TODAY / RECENT
    // ============================================================

    function renderToday(container, entries) {
        if (entries.length === 0) {
            window.ui.renderEmptyState(container, {
                icon: "🏋️",
                title: "Nothing logged today",
                body: "One set is enough to keep the streak alive.",
                actionLabel: "Log your first set",
                onAction: function () { window.location.href = "log-workout.html"; }
            });
            return;
        }

        // Built into an array first: replaceChildren(...nodes) is one DOM
        // mutation, where appending in a loop is one per row.
        const rows = entries.map(function (entry) {
            const row = document.createElement("div");
            row.className = "today__item";

            const name = document.createElement("span");
            name.className = "today__exercise";
            name.textContent = entry.exercise_name;

            const count = document.createElement("span");
            count.className = "badge badge--gold";
            count.textContent = entry.total_sets +
                                (entry.total_sets === 1 ? " set" : " sets");

            row.appendChild(name);
            row.appendChild(count);
            return row;
        });

        container.replaceChildren.apply(container, rows);
    }

    function renderRecent(container, sessions) {
        if (sessions.length === 0) {
            window.ui.renderEmptyState(container, {
                icon: "📓",
                title: "No sessions yet",
                body: "Your logged workouts will appear here."
            });
            return;
        }

        const rows = sessions.slice(0, RECENT_LIMIT).map(function (session) {
            const key = serverKey(session.workout_date);

            const row = document.createElement("a");
            row.className = "recent-row";
            row.href = "history.html";

            const date = document.createElement("span");
            date.className = "recent-row__date";
            date.textContent = key ? formatDay(key) : "—";

            const detail = document.createElement("span");
            detail.className = "recent-row__detail";
            detail.textContent = session.total_sets +
                (session.total_sets === 1 ? " set · " : " sets · ") +
                Math.round(session.total_volume).toLocaleString() + " kg";

            row.appendChild(date);
            row.appendChild(detail);
            return row;
        });

        container.replaceChildren.apply(container, rows);
    }

    // ============================================================
    // PERSONAL RECORDS
    // ============================================================

    const PR_COLUMNS = [
        { key: "exercise_name", label: "Exercise", numeric: false },
        { key: "best", label: "Best set", numeric: true },
        { key: "estimated_1rm", label: "Est. 1RM", numeric: true },
        { key: "achieved_on", label: "Achieved", numeric: false }
    ];

    function renderPersonalRecords(container, records) {
        if (records.length === 0) {
            window.ui.renderEmptyState(container, {
                icon: "🏅",
                title: "No records yet",
                body: "Log a set with a weight and your first record appears here."
            });
            return;
        }

        let sortKey = "estimated_1rm";
        let ascending = false;

        function draw() {
            const rows = records.slice().sort(function (a, b) {
                let left = a[sortKey];
                let right = b[sortKey];
                if (sortKey === "best") {
                    left = a.best_weight;
                    right = b.best_weight;
                }
                if (left === right) return 0;
                const order = left > right ? 1 : -1;
                return ascending ? order : -order;
            });

            container.replaceChildren();

            const wrap = document.createElement("div");
            wrap.className = "table-wrap";

            const table = document.createElement("table");
            table.className = "table";

            const head = document.createElement("thead");
            const headRow = document.createElement("tr");

            PR_COLUMNS.forEach(function (column) {
                const cell = document.createElement("th");
                cell.scope = "col";
                if (column.numeric) cell.className = "table__numeric";
                cell.setAttribute("aria-sort", sortKey !== column.key
                    ? "none" : (ascending ? "ascending" : "descending"));

                const button = document.createElement("button");
                button.type = "button";
                button.className = "table__sort";
                button.textContent = column.label;
                button.addEventListener("click", function () {
                    if (sortKey === column.key) ascending = !ascending;
                    else { sortKey = column.key; ascending = false; }
                    draw();
                });

                cell.appendChild(button);
                headRow.appendChild(cell);
            });

            head.appendChild(headRow);
            table.appendChild(head);

            const body = document.createElement("tbody");

            rows.forEach(function (record) {
                const key = serverKey(record.achieved_on);
                const isNew = key !== null && daysSince(key) <= PR_RECENT_DAYS;

                const row = document.createElement("tr");

                const name = document.createElement("td");
                name.textContent = record.exercise_name;
                if (isNew) {
                    const badge = document.createElement("span");
                    badge.className = "badge badge--gold pr-badge";
                    badge.textContent = "New PR";
                    name.appendChild(badge);
                }

                const best = document.createElement("td");
                best.className = "table__numeric";
                best.textContent = record.best_weight + " kg × " + record.best_reps;

                const oneRm = document.createElement("td");
                oneRm.className = "table__numeric";
                oneRm.textContent = Math.round(record.estimated_1rm) + " kg";

                const achieved = document.createElement("td");
                achieved.textContent = key ? formatDay(key) : "—";

                row.appendChild(name);
                row.appendChild(best);
                row.appendChild(oneRm);
                row.appendChild(achieved);
                body.appendChild(row);
            });

            table.appendChild(body);
            wrap.appendChild(table);
            container.appendChild(wrap);
        }

        draw();
    }

    // ============================================================
    // VIEWS
    // ============================================================

    function renderSignedOut() {
        showView("landingView");
    }

    /* One async region: skeleton while it loads, error state with its own retry
       if it fails. Written once rather than six times, so every panel on this
       page behaves the same way when the network does.
    */
    async function loadRegion(panel, request, render, skeleton) {
        if (!panel) return;
        window.ui.renderSkeleton(panel, skeleton);

        try {
            render(await request());
        } catch (error) {
            window.ui.renderErrorState(panel, error, function () {
                loadRegion(panel, request, render, skeleton);
            });
        }
    }

    function loadDistribution(period) {
        return loadRegion(
            document.getElementById("distributionPanel"),
            function () {
                return window.api.get("/stats/muscle-distribution?period=" + period);
            },
            function (payload) {
                window.charts.muscleBars(
                    document.getElementById("distributionPanel"), payload.data);
            },
            { rows: 5, parts: ["text"] }
        );
    }

    async function renderSignedIn(user) {
        showView("dashboardView");

        const firstName = firstNameOf(user);
        document.getElementById("greeting").textContent =
            firstName ? "Welcome back, " + firstName : "Welcome back";

        const statGrid = document.getElementById("statGrid");
        const periodSelect = document.getElementById("distributionPeriod");
        periodSelect.addEventListener("change", function () {
            loadDistribution(this.value);
        });


        const streakPanel = document.getElementById("streakPanel");
        const weightPanel = document.getElementById("weightPanel");

        /* Three regions share one request, so they share one loader and one
           retry - retrying the streak would otherwise refetch the same summary
           three times. */
        async function loadSummary() {
            skeletonStats(statGrid, 4);
            window.ui.renderSkeleton(streakPanel, { rows: 1, parts: ["title", "text"] });
            window.ui.renderSkeleton(weightPanel, { rows: 1, parts: ["title", "text"] });

            try {
                const payload = await window.api.get("/stats/summary");
                renderStats(statGrid, payload.data);
                renderStreak(streakPanel, payload.data);
                renderWeight(weightPanel, payload.data, user.fitness_goal);
            } catch (error) {
                statGrid.replaceChildren();
                window.ui.renderErrorState(streakPanel, error, loadSummary);
                window.ui.renderErrorState(weightPanel, error, loadSummary);
            }
        }

        wireWeightForm(async function () {
            const refreshed = await window.api.get("/stats/summary");
            renderWeight(weightPanel, refreshed.data, user.fitness_goal);
        });

        await Promise.all([
            loadSummary(),

            loadRegion(
                document.getElementById("todayPanel"),
                function () { return window.api.get("/today-workout"); },
                function (payload) {
                    renderToday(document.getElementById("todayPanel"), payload.data);
                },
                { rows: 3, parts: ["text"] }
            ),

            loadRegion(
                document.getElementById("recentPanel"),
                function () {
                    return window.api.get("/workout-history?limit=" + RECENT_PAGE);
                },
                function (payload) {
                    renderRecent(document.getElementById("recentPanel"), payload.data);
                },
                { rows: 5, parts: ["text"] }
            ),

            loadRegion(
                document.getElementById("prPanel"),
                function () { return window.api.get("/personal-records"); },
                function (payload) {
                    renderPersonalRecords(document.getElementById("prPanel"), payload.data);
                },
                { rows: 4, parts: ["text"] }
            ),

            loadDistribution(periodSelect.value)
        ]);
    }

    async function init() {
        let user = null;

        try {
            user = await window.api.session();
        } catch (error) {
            window.ui.showToast(error.message, "error");
        }

        if (user) await renderSignedIn(user);
        else renderSignedOut();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
