/* charts.js - inline SVG charts built by hand. No library, no build step.

   Exposes window.charts: lineChart plus the volumeOverTime, weightOverTime and
   muscleBars presets. One line-chart implementation serves every time series,
   so a fix to the tooltip or the axis fixes all of them.

   Design decisions, and why:
   - One series, so there is no legend box; the card heading names the measure.
   - Solid hairline gridlines. Dashed rules read as "threshold" when they are
     just a grid.
   - Only the final point is labelled. A number on every point is unreadable.
   - The tooltip enhances but never gates: every value in this chart is also
     listed in the session cards below it, which is the table-view twin.
   - Hover is a nearest-point crosshair driven by pointer x across the whole
     plot, not per-dot hit testing, so there are no pinpoint targets.
   - Keyboard gets the same read as the mouse: the plot is focusable and arrow
     keys step through points.
   - The viewBox includes the x-axis band, so axis labels can never be clipped
     by the container.
*/

(function () {
    "use strict";

    const VIEW_W = 720;
    const VIEW_H = 260;
    const PAD = { top: 20, right: 20, bottom: 44, left: 56 };
    const PLOT_W = VIEW_W - PAD.left - PAD.right;
    const PLOT_H = VIEW_H - PAD.top - PAD.bottom;
    const Y_TICKS = 4;
    const MIN_POINTS = 2;
    const SVG_NS = "http://www.w3.org/2000/svg";

    function svgEl(name, attrs) {
        const node = document.createElementNS(SVG_NS, name);
        Object.keys(attrs || {}).forEach(function (key) {
            node.setAttribute(key, attrs[key]);
        });
        return node;
    }

    function compact(value) {
        if (value >= 1000) {
            const thousands = value / 1000;
            return (thousands >= 10 ? Math.round(thousands) : thousands.toFixed(1)) + "k";
        }
        return String(Math.round(value));
    }

    /** Round the axis maximum up to something a human would have chosen. */
    function niceMax(value) {
        if (value <= 0) return 1;
        const magnitude = Math.pow(10, Math.floor(Math.log10(value)));
        return Math.ceil(value / magnitude) * magnitude;
    }

    function formatDate(iso, style) {
        const date = new Date(iso + "T00:00:00");
        if (Number.isNaN(date.getTime())) return iso;
        return new Intl.DateTimeFormat(undefined, style).format(date);
    }

    function insufficient(container, count, options) {
        container.replaceChildren();

        const message = document.createElement("p");
        message.className = "chart__empty";
        message.textContent = count === 0 ? options.emptyMessage : options.singleMessage;

        container.appendChild(message);
    }

    /**
     * Line chart with an optional area fill, a crosshair tooltip and a keyboard
     * cursor. Shared by every time series in the app.
     *
     * @param {Element} container
     * @param {object[]} points  oldest first, each with a `date` and the value
     *                          named by options.valueKey
     * @param {{valueKey: string, unit: string, ariaLabel: string,
     *          emptyMessage: string, singleMessage: string,
     *          zeroBaseline?: boolean, area?: boolean}} options
     */
    function lineChart(container, points, options) {
        if (!container) return;

        if (!Array.isArray(points) || points.length < MIN_POINTS) {
            insufficient(container, points ? points.length : 0, options);
            return;
        }

        const key = options.valueKey;
        const zeroBaseline = options.zeroBaseline !== false;
        const withArea = options.area !== false;

        const values = points.map(function (point) { return point[key]; });
        const highest = Math.max.apply(null, values);
        const lowest = Math.min.apply(null, values);

        /* A zero baseline is right when the value's distance from zero is the
           point (volume lifted). It is wrong for bodyweight: 75kg on a 0-80
           axis makes a real 3kg change look like a flat line. Those series get
           a padded range instead - and no area fill, since a filled area does
           imply reading magnitude down to zero. */
        const yMax = zeroBaseline ? niceMax(highest) : highest + (highest - lowest || 1) * 0.2;
        const yMin = zeroBaseline ? 0 : lowest - (highest - lowest || 1) * 0.2;
        const ySpan = yMax - yMin || 1;

        const xOf = function (index) {
            return PAD.left + (index / (points.length - 1)) * PLOT_W;
        };
        const yOf = function (value) {
            return PAD.top + PLOT_H - ((value - yMin) / ySpan) * PLOT_H;
        };

        container.replaceChildren();

        const frame = document.createElement("div");
        frame.className = "chart";

        const svg = svgEl("svg", {
            viewBox: "0 0 " + VIEW_W + " " + VIEW_H,
            class: "chart__svg",
            role: "img",
            tabindex: "0",
            "aria-label": options.ariaLabel + ". " + points.length +
                          " points, from " + Math.round(lowest) + " to " +
                          Math.round(highest) + " " + options.unit + "."
        });

        // --- gradient for the area fill --------------------------------
        const defs = svgEl("defs", {});
        const gradient = svgEl("linearGradient", {
            id: "volumeFill", x1: "0", y1: "0", x2: "0", y2: "1"
        });
        gradient.appendChild(svgEl("stop", {
            offset: "0%", "stop-color": "var(--gold)", "stop-opacity": "0.28"
        }));
        gradient.appendChild(svgEl("stop", {
            offset: "100%", "stop-color": "var(--gold)", "stop-opacity": "0"
        }));
        defs.appendChild(gradient);
        svg.appendChild(defs);

        // --- y grid + ticks -------------------------------------------
        for (let tick = 0; tick <= Y_TICKS; tick++) {
            const value = yMin + (ySpan / Y_TICKS) * tick;
            const y = yOf(value);

            svg.appendChild(svgEl("line", {
                x1: PAD.left, y1: y, x2: PAD.left + PLOT_W, y2: y,
                class: "chart__grid"
            }));

            const label = svgEl("text", {
                x: PAD.left - 10, y: y + 4, class: "chart__tick", "text-anchor": "end"
            });
            label.textContent = compact(value);
            svg.appendChild(label);
        }

        // --- x ticks: first, last, and the middle if there is room -----
        const xTickIndexes = points.length > 3
            ? [0, Math.floor((points.length - 1) / 2), points.length - 1]
            : points.map(function (_, index) { return index; });

        xTickIndexes.forEach(function (index) {
            const label = svgEl("text", {
                x: xOf(index),
                y: PAD.top + PLOT_H + 24,
                class: "chart__tick",
                "text-anchor": index === 0
                    ? "start"
                    : (index === points.length - 1 ? "end" : "middle")
            });
            label.textContent = formatDate(points[index].date, { day: "numeric", month: "short" });
            svg.appendChild(label);
        });

        // --- area then line -------------------------------------------
        const line = points.map(function (point, index) {
            return (index === 0 ? "M" : "L") + xOf(index) + " " + yOf(point[key]);
        }).join(" ");

        const baseline = PAD.top + PLOT_H;
        if (withArea) {
            svg.appendChild(svgEl("path", {
                d: line + " L" + xOf(points.length - 1) + " " + baseline +
                   " L" + xOf(0) + " " + baseline + " Z",
                class: "chart__area"
            }));
        }
        svg.appendChild(svgEl("path", { d: line, class: "chart__line" }));

        // --- crosshair + focus marker, hidden until used ---------------
        const crosshair = svgEl("line", {
            y1: PAD.top, y2: baseline, class: "chart__crosshair", visibility: "hidden"
        });
        svg.appendChild(crosshair);

        const marker = svgEl("circle", {
            r: 5, class: "chart__marker", visibility: "hidden"
        });
        svg.appendChild(marker);

        // Final point is labelled directly; the rest live in the tooltip and
        // in the session list below.
        const endLabel = svgEl("text", {
            x: xOf(points.length - 1) - 6,
            y: yOf(points[points.length - 1][key]) - 12,
            class: "chart__endlabel",
            "text-anchor": "end"
        });
        endLabel.textContent = compact(points[points.length - 1][key]) + " " + options.unit;
        svg.appendChild(endLabel);

        svg.appendChild(svgEl("circle", {
            cx: xOf(points.length - 1),
            cy: yOf(points[points.length - 1][key]),
            r: 4,
            class: "chart__endpoint"
        }));

        // --- tooltip (HTML: easier to lay out text than in SVG) --------
        const tooltip = document.createElement("div");
        tooltip.className = "chart__tooltip";
        tooltip.hidden = true;

        function showPoint(index) {
            const point = points[index];
            const x = xOf(index);
            const y = yOf(point[key]);

            crosshair.setAttribute("x1", x);
            crosshair.setAttribute("x2", x);
            crosshair.setAttribute("visibility", "visible");
            marker.setAttribute("cx", x);
            marker.setAttribute("cy", y);
            marker.setAttribute("visibility", "visible");

            tooltip.hidden = false;
            tooltip.textContent = formatDate(point.date, {
                weekday: "short", day: "numeric", month: "short"
            }) + " — " + point[key].toLocaleString() + " " + options.unit;
            tooltip.style.left = (x / VIEW_W * 100) + "%";
        }

        function hidePoint() {
            crosshair.setAttribute("visibility", "hidden");
            marker.setAttribute("visibility", "hidden");
            tooltip.hidden = true;
        }

        /* Nearest point to the pointer's x, so the whole plot is the hit area
           rather than each 10px dot. */
        function nearestIndex(clientX) {
            const box = svg.getBoundingClientRect();
            const ratio = (clientX - box.left) / box.width;
            const plotRatio = (ratio * VIEW_W - PAD.left) / PLOT_W;
            const index = Math.round(plotRatio * (points.length - 1));
            return Math.min(points.length - 1, Math.max(0, index));
        }

        let cursor = points.length - 1;

        svg.addEventListener("pointermove", function (event) {
            cursor = nearestIndex(event.clientX);
            showPoint(cursor);
        });
        svg.addEventListener("pointerleave", hidePoint);
        svg.addEventListener("blur", hidePoint);
        svg.addEventListener("focus", function () { showPoint(cursor); });

        svg.addEventListener("keydown", function (event) {
            if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
            event.preventDefault();
            cursor = Math.min(points.length - 1, Math.max(0,
                cursor + (event.key === "ArrowRight" ? 1 : -1)));
            showPoint(cursor);
        });

        frame.appendChild(svg);
        frame.appendChild(tooltip);
        container.appendChild(frame);
    }

    /* ============================================================
       PRESETS
       ============================================================ */

    /** @param {{date: string, volume: number}[]} points oldest first */
    function volumeOverTime(container, points) {
        return lineChart(container, points, {
            valueKey: "volume",
            unit: "kg",
            ariaLabel: "Training volume per session over time",
            emptyMessage: "Log a few sessions and your volume trend will appear here.",
            singleMessage: "One session so far — a trend needs at least two."
        });
    }

    /** @param {{date: string, weight: number}[]} points oldest first */
    function weightOverTime(container, points) {
        return lineChart(container, points, {
            valueKey: "weight",
            unit: "kg",
            ariaLabel: "Bodyweight over time",
            emptyMessage: "Log your weight and your trend will appear here.",
            singleMessage: "One entry so far — a trend needs at least two.",
            // See the note in lineChart: a zero baseline would flatten real
            // bodyweight variation, and without one an area fill would mislead.
            zeroBaseline: false,
            area: false
        });
    }


    /* ============================================================
       HORIZONTAL BARS - set distribution by muscle group
       ============================================================
       One measure, one series, so one flat gold fill for every bar. A
       gradient or a darker-where-bigger ramp would encode the value a
       second time in colour when the length already says it, and muscle
       groups have no natural order for a ramp to follow.
    */

    const BAR_ROW_H = 34;
    const BAR_LABEL_W = 128;
    const BAR_VALUE_W = 64;

    /**
     * @param {Element} container
     * @param {{muscle_name: string, sets: number, percentage: number}[]} rows
     */
    function muscleBars(container, rows) {
        if (!container) return;

        if (!Array.isArray(rows) || rows.length === 0) {
            container.replaceChildren();
            const message = document.createElement("p");
            message.className = "chart__empty";
            message.textContent = "No sets logged in this period yet.";
            container.appendChild(message);
            return;
        }

        const height = rows.length * BAR_ROW_H;
        const barMax = VIEW_W - BAR_LABEL_W - BAR_VALUE_W;
        const widest = Math.max.apply(null, rows.map(function (r) { return r.sets; }));

        container.replaceChildren();

        const svg = svgEl("svg", {
            viewBox: "0 0 " + VIEW_W + " " + height,
            class: "chart__svg",
            role: "img",
            "aria-label": "Sets per muscle group. " + rows.map(function (r) {
                return r.muscle_name + ": " + r.sets + " sets, " + r.percentage + " percent";
            }).join(". ")
        });

        rows.forEach(function (row, index) {
            const y = index * BAR_ROW_H;
            const barY = y + 9;
            const width = widest ? Math.max(2, (row.sets / widest) * barMax) : 2;

            const label = svgEl("text", {
                x: 0, y: y + 21, class: "bar__label"
            });
            label.textContent = row.muscle_name;
            svg.appendChild(label);

            // Track behind the bar, so a short bar still reads as a proportion.
            svg.appendChild(svgEl("rect", {
                x: BAR_LABEL_W, y: barY, width: barMax, height: 14,
                rx: 7, class: "bar__track"
            }));

            svg.appendChild(svgEl("rect", {
                x: BAR_LABEL_W, y: barY, width: width, height: 14,
                rx: 7, class: "bar__fill"
            }));

            const value = svgEl("text", {
                x: VIEW_W, y: y + 21, class: "bar__value", "text-anchor": "end"
            });
            value.textContent = row.percentage + "%  ·  " + row.sets;
            svg.appendChild(value);
        });

        container.appendChild(svg);
    }

    window.charts = {
        lineChart: lineChart,
        volumeOverTime: volumeOverTime,
        weightOverTime: weightOverTime,
        muscleBars: muscleBars
    };
})();
