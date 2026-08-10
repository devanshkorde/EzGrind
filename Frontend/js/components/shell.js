/* ============================================================
   shell.js
   One source for the nav and footer, injected into the <header>
   and <footer> landmarks every page already declares.

   The landmarks live in the HTML rather than here so the document
   outline survives JavaScript failing, and .nav reserves its height
   in CSS so filling it shifts nothing.

   Auth-dependent links appear once api.session() resolves - one
   request, shared with the page script through the same cache.
   ============================================================ */

(function () {
    "use strict";

    const LINKS_SIGNED_IN = [
        { href: "index.html", label: "Dashboard" },
        { href: "log-workout.html", label: "Log Workout" },
        { href: "history.html", label: "History" },
        { href: "exercises.html", label: "Exercises" },
        { href: "profile.html", label: "Profile" }
    ];

    const LINKS_SIGNED_OUT = [
        { href: "login.html", label: "Login" },
        { href: "signup.html", label: "Sign Up" }
    ];

    function currentPage() {
        return window.location.pathname.split("/").pop() || "index.html";
    }

    function buildLink(link) {
        const anchor = document.createElement("a");
        anchor.className = "nav__link";
        anchor.href = link.href;
        anchor.textContent = link.label;
        if (link.href === currentPage()) {
            anchor.setAttribute("aria-current", "page");
        }
        return anchor;
    }

    function buildBrand() {
        const brand = document.createElement("a");
        brand.className = "nav__brand";
        brand.href = "index.html";

        const logo = document.createElement("img");
        logo.src = "assets/logo.png";
        logo.alt = "";                 // decorative; the wordmark carries the name
        logo.width = 40;
        logo.height = 40;

        const name = document.createElement("span");
        name.textContent = "EzGrind";

        brand.appendChild(logo);
        brand.appendChild(name);
        return brand;
    }

    function buildLogoutButton() {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "nav__link";
        button.textContent = "Logout";

        button.addEventListener("click", async function () {
            try {
                await window.api.post("/logout");
                window.api.clearSession();
                window.location.href = "login.html";
            } catch (error) {
                window.ui.showToast(error.message, "error");
            }
        });

        return button;
    }

    function renderNav(header) {
        header.className = "nav";

        const nav = document.createElement("nav");
        nav.className = "nav__links";
        nav.setAttribute("aria-label", "Main");

        header.replaceChildren(buildBrand(), nav);
        return nav;
    }

    function fillNav(nav, user) {
        const links = user ? LINKS_SIGNED_IN : LINKS_SIGNED_OUT;
        nav.replaceChildren();
        links.forEach(function (link) {
            nav.appendChild(buildLink(link));
        });
        if (user) {
            nav.appendChild(buildLogoutButton());
        }
    }

    function renderFooter(footer) {
        footer.className = "footer";
        footer.textContent = "EzGrind © 2026";
    }

    /* First thing in the tab order: lets a keyboard user jump past the nav
       instead of tabbing through every link on every page. Injected here
       rather than added to nine documents by hand. */
    function addSkipLink() {
        if (document.querySelector(".skip-link")) return;

        const main = document.querySelector("main");
        if (!main) return;

        if (!main.id) main.id = "main";

        const link = document.createElement("a");
        link.className = "skip-link";
        link.href = "#" + main.id;
        link.textContent = "Skip to content";

        // <main> is not focusable by default, so the jump would move the
        // viewport but not the focus ring.
        if (!main.hasAttribute("tabindex")) main.setAttribute("tabindex", "-1");

        document.body.insertBefore(link, document.body.firstChild);
    }

    function init() {
        addSkipLink();

        const header = document.getElementById("siteHeader");
        const footer = document.getElementById("siteFooter");

        if (footer) {
            renderFooter(footer);
        }

        if (!header) return;

        const nav = renderNav(header);

        window.api.session()
            .then(function (user) { fillNav(nav, user); })
            .catch(function () {
                // Session unknown (backend down). Signed-out links are the
                // safe default - both destinations work either way.
                fillNav(nav, null);
            });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
