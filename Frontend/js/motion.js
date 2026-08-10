/* Entrance motion: the one-time intro, and a reusable scroll reveal.

   This file only ever adds and removes class names. It never measures, never
   writes a style, and never waits on anything — so it cannot delay a fetch, and
   removing it entirely leaves every page fully functional.

   The hidden starting states all live behind html.js-enabled in motion.css. That
   class is set by an inline script in <head>, not here: if this file fails to
   load, the class is still absent and the page renders as ordinary content
   rather than staying invisible.
*/

(function () {
    "use strict";

    // Once per session, not once per page load. Someone moving between pages
    // during a workout should see the brand moment on the first one and never
    // again until they come back tomorrow.
    const SESSION_KEY = "ezgrind.introPlayed";

    // 15%: enough of a card on screen that the movement reads as the card
    // arriving, rather than something twitching at the edge of the viewport.
    const REVEAL_RATIO = 0.15;

    // Fade starts at 900ms and runs 200ms. Must match --intro-brand-fade-at
    // plus --intro-brand-fade in tokens.css; removing the node earlier would
    // cut the fade off mid-way.
    const BRAND_TOTAL = 1100;

    function prefersReducedMotion() {
        return window.matchMedia
            && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    }

    /* sessionStorage throws in Safari private mode rather than returning null,
       so both accessors swallow. Failing to read means "not played yet", which
       shows the intro one extra time — the harmless direction to fail in. */
    function alreadyPlayed() {
        try {
            return window.sessionStorage.getItem(SESSION_KEY) === "1";
        } catch (error) {
            return false;
        }
    }

    function markPlayed() {
        try {
            window.sessionStorage.setItem(SESSION_KEY, "1");
        } catch (error) {
            // Nothing to do. The intro simply plays again next page.
        }
    }

    /* ------------------------------------------------------------
       REUSABLE REVEAL

       motion.reveal(".card") on any page. Elements animate once when
       they cross the threshold and are then unobserved, so scrolling
       back up never replays anything.
       ------------------------------------------------------------ */
    function reveal(selector, options) {
        const settings = options || {};
        const root = settings.within || document;
        const elements = Array.prototype.slice.call(root.querySelectorAll(selector));
        if (elements.length === 0) return;

        // No observer support, or the user wants no motion: mark everything
        // revealed immediately. The class carries the final state, so this is
        // the fully-visible result with no animation in between.
        if (!("IntersectionObserver" in window) || prefersReducedMotion()) {
            elements.forEach(function (element) {
                element.classList.add("is-revealed");
            });
            return;
        }

        const observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) return;
                entry.target.classList.add("is-revealed");
                // Unobserved on the way in, which is what makes it once-only.
                observer.unobserve(entry.target);
            });
        }, { threshold: settings.threshold || REVEAL_RATIO });

        elements.forEach(function (element) { observer.observe(element); });
    }

    /* ------------------------------------------------------------
       INTRO
       ------------------------------------------------------------ */

    function playBrand() {
        const brand = document.querySelector(".intro-brand");
        if (!brand) return;

        brand.classList.add("is-playing");
        // Removed rather than left at opacity 0: a fixed full-screen element
        // that outlives its animation is a bug waiting to intercept something,
        // even with pointer-events:none.
        window.setTimeout(function () { brand.remove(); }, BRAND_TOTAL);
    }

    /* Called by dashboard.js the moment a view is unhidden — not on
       DOMContentLoaded. Both views on index.html start hidden until the session
       resolves, so an intro tied to page load would play to a blank screen and
       be finished before anything was visible. */
    function playIntro(viewId) {
        const hero = document.querySelector(".intro-hero");
        const isLanding = viewId === "landingView";

        // Scroll reveals are not part of the intro and always run: they fire on
        // scrolling to a section, which is a fresh action on every page load.
        // Deliberately not .stagger - that fires on load from components.css,
        // and the elements carrying it are filled in after their API call
        // returns, so observing them empty would mean observing a zero-height
        // box that never crosses the threshold.
        reveal("[data-reveal], [data-reveal-stagger]");

        if (prefersReducedMotion()) {
            const brand = document.querySelector(".intro-brand");
            if (brand) brand.remove();
            return;
        }

        // Repeat visit within the session: skip to the end state. The elements
        // are hidden by CSS until .is-playing exists, so adding it without the
        // brand moment still lets the hero settle immediately below.
        if (alreadyPlayed()) {
            const brand = document.querySelector(".intro-brand");
            if (brand) brand.remove();
            if (hero) hero.classList.add("is-playing", "is-instant");
            return;
        }

        // The signed-in dashboard skips the brand moment entirely. Someone who
        // is already logged in has seen the logo; what they came for is their
        // numbers, and the cards stagger on their own.
        if (isLanding) playBrand();

        if (hero) hero.classList.add("is-playing");
        markPlayed();
    }

    window.motion = {
        reveal: reveal,
        playIntro: playIntro,
        prefersReducedMotion: prefersReducedMotion
    };
})();
