"""Static checks for the frontend. Run directly: python check_frontend.py

A development tool, not shipped to the browser. Asserts the invariants this
codebase keeps breaking by hand: pages that link a stylesheet at the wrong
path, <link> tags stranded in <body>, colours hardcoded outside tokens.css,
and raw fetch() calls that bypass the API layer.

Reads files only. Changes nothing.
"""

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PAGES = ["index.html", "login.html", "signup.html", "profile.html",
         "log-workout.html", "exercises.html", "history.html",
         # Both reached from an email link, often on a device that has never
         # signed in here.
         "forgot-password.html", "reset-password.html",
         # Styled to match, though neither is reachable in the current setup:
         # the API answers JSON on every error and Flask does not serve these.
         "404.html", "500.html"]

STYLESHEET_ORDER = ["css/tokens.css", "css/base.css", "css/components.css",
                    "css/layout.css", "css/pages.css",
                    # Last, so it can override the resting state of anything in
                    # pages.css without needing extra specificity. On every page
                    # rather than only index.html, because motion.reveal() is
                    # meant to be reused and one uniform order is easier to hold
                    # than a per-page exception.
                    "css/motion.css"]

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}

HEX_PATTERN = re.compile(r"#[0-9a-fA-F]{3,8}\b")
VAR_USE_PATTERN = re.compile(r"var\(\s*(--[\w-]+)")
VAR_DEF_PATTERN = re.compile(r"^\s*(--[\w-]+)\s*:", re.MULTILINE)

failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


class PageParser(HTMLParser):
    """Collects structure while verifying tags nest and close properly."""

    def __init__(self, page):
        super().__init__(convert_charrefs=True)
        self.page = page
        self.stack = []
        self.tags = []
        self.h1_count = 0
        self.view_count = 0
        self.stylesheets = []
        self.links_in_body = 0
        self.scripts = []
        self.images_without_alt = 0
        self.in_body = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.tags.append(tag)

        if tag == "body":
            self.in_body = True
        if tag == "h1":
            self.h1_count += 1
        if "data-view" in attributes:
            self.view_count += 1
        if tag == "link":
            if attributes.get("rel") == "stylesheet":
                self.stylesheets.append(attributes.get("href", ""))
            if self.in_body:
                self.links_in_body += 1
        if tag == "script" and attributes.get("src"):
            self.scripts.append(attributes["src"])
        if tag == "img" and "alt" not in attributes:
            self.images_without_alt += 1

        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        if not self.stack:
            failures.append(f"{self.page}: stray closing </{tag}>")
            return
        if self.stack[-1] != tag:
            failures.append(
                f"{self.page}: </{tag}> closes out of order "
                f"(expected </{self.stack[-1]}>)"
            )
            # Recover so one mistake does not cascade into noise.
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
            return
        self.stack.pop()


def check_page(name):
    path = ROOT / name
    if not path.exists():
        failures.append(f"{name}: missing")
        return

    source = path.read_text(encoding="utf-8")
    parser = PageParser(name)
    parser.feed(source)

    check(parser.stack == [], f"{name}: unclosed tags {parser.stack}")
    check(source.lstrip().lower().startswith("<!doctype html>"),
          f"{name}: missing <!DOCTYPE html>")
    check('<html lang="en">' in source, f"{name}: <html> missing lang=\"en\"")
    check('charset' in source, f"{name}: missing <meta charset>")
    check('name="viewport"' in source, f"{name}: missing viewport meta")
    check('name="description"' in source, f"{name}: missing description meta")
    # A page may declare mutually-exclusive [data-view] blocks (index.html shows
    # either the landing page or the dashboard). Each needs its own <h1>; only
    # one view is ever in the document at runtime.
    expected_h1 = max(parser.view_count, 1)
    check(parser.h1_count == expected_h1,
          f"{name}: expected {expected_h1} <h1> "
          f"({parser.view_count or 'no'} view blocks), found {parser.h1_count}")
    check(parser.links_in_body == 0,
          f"{name}: {parser.links_in_body} <link> tag(s) inside <body>")
    check(parser.images_without_alt == 0,
          f"{name}: {parser.images_without_alt} <img> without alt")

    check(parser.stylesheets == STYLESHEET_ORDER,
          f"{name}: stylesheets are {parser.stylesheets}, expected {STYLESHEET_ORDER}")

    for tag in ("header", "main", "footer"):
        check(tag in parser.tags, f"{name}: missing <{tag}> landmark")

    for reference in parser.stylesheets + parser.scripts:
        check((ROOT / reference).exists(), f"{name}: references missing file {reference}")

    api_first = parser.scripts[:1] == ["js/api.js"]
    check(api_first, f"{name}: js/api.js must load first, got {parser.scripts[:1]}")


def check_css():
    tokens_path = ROOT / "css" / "tokens.css"
    check(tokens_path.exists(), "css/tokens.css: missing")
    if not tokens_path.exists():
        return

    defined = set(VAR_DEF_PATTERN.findall(tokens_path.read_text(encoding="utf-8")))
    check(bool(defined), "css/tokens.css: defines no custom properties")

    for css_file in sorted((ROOT / "css").glob("*.css")):
        source = css_file.read_text(encoding="utf-8")
        label = f"css/{css_file.name}"

        if css_file.name != "tokens.css":
            for match in HEX_PATTERN.finditer(source):
                line = source[:match.start()].count("\n") + 1
                failures.append(
                    f"{label}:{line}: hardcoded colour {match.group(0)} "
                    f"- move it into tokens.css"
                )

        for used in set(VAR_USE_PATTERN.findall(source)):
            check(used in defined, f"{label}: uses undefined token {used}")

    for dead in ("style.css", "theme.css"):
        check(not (ROOT / "css" / dead).exists(),
              f"css/{dead}: should have been deleted once its rules were ported")

    check_hover_gating()
    check_viewport_units()


def strip_balanced_blocks(source, opener):
    """Remove every `opener { ... }` block, brace-matched, from `source`."""
    out = []
    index = 0

    while True:
        start = source.find(opener, index)
        if start == -1:
            out.append(source[index:])
            return "".join(out)

        out.append(source[index:start])
        brace = source.find("{", start)
        if brace == -1:
            return "".join(out)

        depth, cursor = 1, brace + 1
        while cursor < len(source) and depth:
            if source[cursor] == "{":
                depth += 1
            elif source[cursor] == "}":
                depth -= 1
            cursor += 1
        index = cursor


def check_hover_gating():
    """:hover latches on a touchscreen, so every hover rule must be gated.

    Comments are stripped first: the note explaining this rule mentions
    ":hover" and would otherwise report itself.
    """
    for css_file in sorted((ROOT / "css").glob("*.css")):
        source = strip_comments(css_file.read_text(encoding="utf-8"))
        outside = strip_balanced_blocks(source, "@media (hover: hover)")

        for line in outside.splitlines():
            if ":hover" in line:
                failures.append(
                    f"css/{css_file.name}: ungated :hover -> {line.strip()[:60]!r}"
                    f" (wrap it in @media (hover: hover))"
                )


def check_viewport_units():
    """Every vh needs a dvh sibling: iOS counts the retracted URL bar in vh.

    Comments are stripped so an explanatory note between the two declarations
    cannot separate them.
    """
    for css_file in sorted((ROOT / "css").glob("*.css")):
        stripped = strip_comments(css_file.read_text(encoding="utf-8"))
        # Blank lines dropped too: removing a comment leaves one behind, which
        # would push the dvh declaration out of the adjacency window.
        lines = [line for line in stripped.splitlines() if line.strip()]

        for index, line in enumerate(lines):
            if not re.search(r"\d(vh|vmin|vmax)\b", line):
                continue
            neighbourhood = " ".join(lines[max(0, index - 1):index + 2])
            check("dvh" in neighbourhood,
                  f"css/{css_file.name}: {line.strip()[:60]!r} has no dvh "
                  f"fallback on the line beside it")


def strip_comments(source):
    """Comments discuss the banned calls; only real calls should fail.

    ponytail: naive stripper - the negative lookbehind keeps it from eating
    "http://" but it would still trip on "//" inside a string literal. Good
    enough for this codebase; use a real parser if that ever bites.
    """
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"(?<!:)//[^\n]*", "", source)


def check_js():
    api_file = (ROOT / "js" / "api.js").resolve()

    for js_file in sorted((ROOT / "js").rglob("*.js")):
        if js_file.resolve() == api_file:
            continue
        source = strip_comments(js_file.read_text(encoding="utf-8"))
        if re.search(r"\bfetch\s*\(", source):
            failures.append(
                f"js/{js_file.relative_to(ROOT / 'js')}: calls fetch() directly "
                f"- go through api.js"
            )
        if re.search(r"\balert\s*\(|\bconfirm\s*\(", source):
            failures.append(
                f"js/{js_file.relative_to(ROOT / 'js')}: uses alert()/confirm() "
                f"- use ui.showToast / ui.confirmDialog"
            )


for page in PAGES:
    check_page(page)
check_css()
check_js()

if failures:
    print(f"check_frontend: {len(failures)} problem(s)\n")
    for failure in failures:
        print(f"  - {failure}")
    sys.exit(1)

print(f"check_frontend: {len(PAGES)} pages, CSS and JS all pass")
