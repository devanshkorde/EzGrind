/* Verifies the date and name formatting inside dashboard.js against fixed
   inputs. Loads the real source and exposes its internals, so this tests the
   shipped code rather than a copy of it.

   Run:  node check_stats.js
   A development tool. Node is used only to execute it - the app itself still
   has no build step and ships no dependencies.

   SCOPE NOTE: this file used to test the streak arithmetic and the rolling
   week/month sums too. Those moved to the server in Phase 11a
   (Backend/repositories/stats_repo.py) and their assertions moved with them,
   into Backend/smoke.py. What is left here is the formatting the browser still
   owns: GMT date round-tripping, relative day labels, and first names.

   ponytail: reaches into an IIFE by string-patching the source. It fails loudly
   with a clear message if dashboard.js changes shape. Give the module real
   exports if that starts happening often. */

const fs = require("fs");
const assert = require("assert");

const SOURCE = require("path").join(__dirname, "js", "dashboard.js");

let source = fs.readFileSync(SOURCE, "utf8");
const marker = "    if (document.readyState === \"loading\") {";
assert.ok(source.includes(marker), "init guard not found - did dashboard.js change shape?");
source = source.replace(marker, `
    module.exports = { localKey, serverKey, daysAgoKey, formatDay, daysSince,
                       firstNameOf };
    return;
` + marker);

global.document = { readyState: "complete", addEventListener() {}, querySelectorAll: () => [], getElementById: () => null };
global.window = { api: {}, ui: {}, charts: {} };

const mod = { exports: {} };
new Function("module", "document", "window", source)(mod, global.document, global.window);
const d = mod.exports;

function isoDaysAgo(n) {
    const date = new Date();
    date.setDate(date.getDate() - n);
    return [date.getFullYear(),
            String(date.getMonth() + 1).padStart(2, "0"),
            String(date.getDate()).padStart(2, "0")].join("-");
}

/* The API serialises DATE columns as midnight GMT. */
function serverDate(key) {
    return new Date(key + "T00:00:00Z").toUTCString();
}

// --- serverKey survives the GMT round-trip -------------------------
assert.strictEqual(d.serverKey(serverDate("2026-07-28")), "2026-07-28");
assert.strictEqual(d.serverKey("nonsense"), null);
assert.strictEqual(d.serverKey(serverDate(isoDaysAgo(0))), isoDaysAgo(0));

// --- relative day labels -------------------------------------------
assert.strictEqual(d.formatDay(isoDaysAgo(0)), "Today");
assert.strictEqual(d.formatDay(isoDaysAgo(1)), "Yesterday");
assert.ok(!/Today|Yesterday/.test(d.formatDay(isoDaysAgo(5))));

// --- daysSince drives the "New PR" badge ---------------------------
assert.strictEqual(d.daysSince(isoDaysAgo(0)), 0);
assert.strictEqual(d.daysSince(isoDaysAgo(3)), 3);
assert.strictEqual(d.daysSince(isoDaysAgo(30)), 30);
assert.strictEqual(d.daysSince("nonsense"), Infinity, "an unparseable date must never look recent");

// --- names ---------------------------------------------------------
assert.strictEqual(d.firstNameOf({ full_name: "Devansh Korde" }), "Devansh");
assert.strictEqual(d.firstNameOf({ full_name: "  Devansh  " }), "Devansh");
assert.strictEqual(d.firstNameOf({ full_name: "" }), null);
assert.strictEqual(d.firstNameOf({}), null);

console.log("check_stats: all assertions passed");
