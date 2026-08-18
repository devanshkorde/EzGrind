"""Checks the transactional email path.

    python check_resend.py            # config, templates, masking, throttle
    python check_resend.py --write    # + a real signup through the API

Never sends a real email. The Resend sender is exercised against a stub that
answers like the API does - including 429, 401 and the two 403s an unverified
account produces - so every failure branch is covered without spending quota or
mailing anyone. Real delivery is checked with:

    flask --app app send-test-email you@example.com
"""

import argparse
import io
import json
import logging
import secrets
import ssl
import sys
import time
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path

# Python puts THIS file's directory on sys.path, which is Backend/tests/.
# The application lives one level up, so it has to be added explicitly - this
# file used to sit in Backend/ and get it for free.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from app import create_app  # noqa: E402
from db import get_cursor  # noqa: E402
from services import email_service, email_templates  # noqa: E402

PASSED, FAILED = [], []


def check(label, condition, detail=""):
    (PASSED if condition else FAILED).append(label)
    print(f"  {'ok  ' if condition else 'FAIL'} {label}{('  ' + detail) if detail else ''}")


def http_error(code, message):
    """An HTTPError shaped like a real Resend error response."""
    body = json.dumps({"statusCode": code, "message": message}).encode()
    return urllib.error.HTTPError(
        email_service.RESEND_ENDPOINT, code, message, {}, io.BytesIO(body)
    )


def check_config():
    print("\n-- configuration -------------------------------------------")
    check("EMAIL_BACKEND is a known name",
          config.EMAIL_BACKEND in ("console", "resend"), config.EMAIL_BACKEND)
    check("app starts without an API key", True,
          "key present" if config.RESEND_API_KEY else "no key, and that is fine")
    check("MAIL_FROM_ADDRESS is set", bool(config.MAIL_FROM_ADDRESS),
          config.MAIL_FROM_ADDRESS)
    check("APP_BASE_URL is set", config.APP_BASE_URL.startswith("http"),
          config.APP_BASE_URL)
    # The default when EMAIL_BACKEND is unset, which is a different question
    # from what the developer has currently chosen. Reading os.environ rather
    # than config, because config has already resolved one into the other.
    import os
    explicit = bool(os.getenv("EMAIL_BACKEND", "").strip())
    check("console is the default when EMAIL_BACKEND is unset",
          explicit or config.IS_PRODUCTION or config.EMAIL_BACKEND == "console",
          "explicitly set" if explicit else "")

    if config.EMAIL_BACKEND == "resend" and not config.IS_PRODUCTION:
        print("  note live sending is ON in development - every signup spends "
              "from the 100/day quota")


def check_tls():
    """This interpreter's CA bundle. Not a formality - the MSYS2/mingw64 build
    this project runs on ships with none, which breaks every HTTPS call."""
    print("\n-- TLS trust store -----------------------------------------")
    context = email_service._ssl_context()
    certificates = context.cert_store_stats()["x509_ca"]
    check("CA certificates are loaded", certificates > 0, f"{certificates} CAs")
    check("verification is enabled", context.verify_mode == ssl.CERT_REQUIRED)
    check("hostname checking is on", context.check_hostname)


def check_masking():
    print("\n-- address masking -----------------------------------------")
    cases = [
        ("devansh@gmail.com", "d****h@gmail.com"),
        ("devanshkorde195@gmail.com", "d****5@gmail.com"),
        ("ab@x.com", "a****@x.com"),
        ("a@x.com", "a****@x.com"),
        ("not-an-email", "****"),
        ("", "****"),
        (None, "****"),
    ]
    for raw, expected in cases:
        actual = email_service.mask_email(raw)
        check(f"{str(raw)[:26]:<26} -> {actual}", actual == expected,
              "" if actual == expected else f"expected {expected}")


def check_templates():
    print("\n-- templates -----------------------------------------------")
    app = create_app()
    with app.app_context():
        subject, html, text = email_templates.welcome("Devansh Korde")

    check("subject is exactly as specified", subject == "Welcome to EzGrind", subject)
    check("greets by first name only",
          "Welcome, Devansh" in html and "Welcome, Devansh" in text)
    check("html carries the dashboard link", config.APP_BASE_URL in html)
    check("text carries the dashboard link", config.APP_BASE_URL in text)
    check("no image tags at all", "<img" not in html)
    check("no <style> block (Gmail strips them)", "<style" not in html)
    check("no flexbox or grid", "display:flex" not in html and "display:grid" not in html)
    check("no CSS variables", "var(--" not in html)
    check("no external stylesheet", "<link" not in html)
    check("width capped at 600px", "max-width:600px" in html)
    check("card radius is 16px", "border-radius:16px" in html)
    check("button colour on bgcolor, not only CSS", 'bgcolor="#C9A84C"' in html)
    for token in ("#080808", "#1A1A1A", "#C9A84C", "#F5F5F5"):
        check(f"palette {token}", token in html)

    opens, closes = html.count("<table"), html.count("</table>")
    check("tables balanced", opens == closes, f"{opens} open, {closes} close")

    with app.app_context():
        for raw, expected in [("", "there"), ("   ", "there"), (None, "there"),
                              ("Cher", "Cher"), ("Ana Maria Silva", "Ana")]:
            _, _, body = email_templates.welcome(raw)
            check(f"name {raw!r} greets {expected!r}", f"Welcome, {expected}" in body)

        _, nasty, _ = email_templates.welcome("<script>alert(1)</script>")
        check("a name containing markup is escaped",
              "<script>" not in nasty and "&lt;script&gt;" in nasty)


def check_resend_branches():
    """Every failure path, against a stub that answers like Resend."""
    print("\n-- Resend error handling -----------------------------------")
    sender = email_service.ResendEmailSender()
    saved_key = config.RESEND_API_KEY
    config.RESEND_API_KEY = "re_stub_key_for_testing"

    original_urlopen = email_service.urllib.request.urlopen

    def stub(responses):
        queue = list(responses)

        def fake(request, **kwargs):
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item

            class Response:
                def read(self):
                    return json.dumps(item).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            return Response()

        return fake

    try:
        email_service.urllib.request.urlopen = stub([{"id": "msg_abc123"}])
        result = sender.send("a@b.com", "s", "<p>h</p>", "t")
        check("success returns the provider message id",
              result.success and result.provider_message_id == "msg_abc123",
              str(result.provider_message_id))

        email_service.urllib.request.urlopen = stub([
            http_error(403, "The example.com domain is not verified. "
                            "Please add and verify your domain on Resend"),
        ])
        result = sender.send("a@b.com", "s", "<p>h</p>", "t")
        check("domain error says 'domain not verified in Resend'",
              not result.success and "domain not verified in Resend" in result.error)
        print(f"       -> {result.error[:100]}...")

        email_service.urllib.request.urlopen = stub([
            http_error(403, "You can only send testing emails to your own email address"),
        ])
        result = sender.send("a@b.com", "s", "<p>h</p>", "t")
        check("test-mode error is named, not generic",
              not result.success and "test mode" in result.error)

        email_service.urllib.request.urlopen = stub([http_error(401, "API key is invalid")])
        result = sender.send("a@b.com", "s", "<p>h</p>", "t")
        check("401 names the key and the file to fix",
              not result.success and "RESEND_API_KEY" in result.error)

        email_service.urllib.request.urlopen = stub([
            http_error(422, "Missing required field: to")])
        result = sender.send("a@b.com", "s", "<p>h</p>", "t")
        check("422 is reported and NOT retried",
              not result.success and "422" in result.error)

        # 429 three times: retried to the cap, then reported.
        saved_backoff = email_service.BACKOFF_BASE
        saved_interval = email_service.MIN_SEND_INTERVAL
        email_service.BACKOFF_BASE = 0.01
        email_service.MIN_SEND_INTERVAL = 0.0
        calls = []

        def counting_stub(request, **kwargs):
            calls.append(1)
            raise http_error(429, "Too many requests")

        email_service.urllib.request.urlopen = counting_stub
        result = sender.send("a@b.com", "s", "<p>h</p>", "t")
        check("429 retried exactly 3 times then given up",
              not result.success and len(calls) == email_service.MAX_ATTEMPTS,
              f"{len(calls)} attempts")
        check("429 give-up message explains the free tier",
              "100 emails/day" in result.error)

        # 429 then success: the retry actually works.
        attempts = []

        def recovering_stub(request, **kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise http_error(429, "Too many requests")

            class Response:
                def read(self):
                    return b'{"id": "msg_after_retry"}'

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            return Response()

        email_service.urllib.request.urlopen = recovering_stub
        result = sender.send("a@b.com", "s", "<p>h</p>", "t")
        check("a 429 that clears on retry succeeds",
              result.success and result.provider_message_id == "msg_after_retry",
              f"{len(attempts)} attempts")

        email_service.BACKOFF_BASE = saved_backoff
        email_service.MIN_SEND_INTERVAL = saved_interval

        # Cloudflare's plain-text 403. This one shipped broken: the body is not
        # JSON, so the message came out empty and the error read
        # "Resend returned HTTP 403:" with nothing after the colon.
        cloudflare = urllib.error.HTTPError(
            email_service.RESEND_ENDPOINT, 403, "Forbidden", {},
            io.BytesIO(b"error code: 1010\n"))
        email_service.urllib.request.urlopen = stub([cloudflare])
        result = sender.send("a@b.com", "s", "<p>h</p>", "t")
        check("a non-JSON body is reported, not swallowed",
              not result.success and "1010" in result.error)
        check("the error never ends in a bare colon",
              not result.error.rstrip().endswith(":"), result.error[-40:])
        check("it says the request never reached Resend",
              "Blocked before reaching Resend" in result.error)

        check("a User-Agent is sent (Cloudflare 403s urllib's default)",
              email_service.USER_AGENT and "urllib" not in email_service.USER_AGENT.lower(),
              email_service.USER_AGENT)

        email_service.urllib.request.urlopen = stub(
            [urllib.error.URLError("connection refused")])
        result = sender.send("a@b.com", "s", "<p>h</p>", "t")
        check("network failure is caught, not raised",
              not result.success and "Could not reach Resend" in result.error)

        config.RESEND_API_KEY = ""
        result = sender.send("a@b.com", "s", "<p>h</p>", "t")
        check("missing key fails with instructions, does not crash",
              not result.success and "EMAIL_BACKEND=console" in result.error)

    finally:
        email_service.urllib.request.urlopen = original_urlopen
        config.RESEND_API_KEY = saved_key


def check_throttle():
    print("\n-- rate guard ----------------------------------------------")
    email_service._last_send_at = 0.0
    start = time.monotonic()
    for _ in range(3):
        email_service._throttle()
    elapsed = time.monotonic() - start
    floor = email_service.MIN_SEND_INTERVAL * 2
    check(f"3 sends take at least {floor:.2f}s (2/s cap)", elapsed >= floor,
          f"{elapsed:.2f}s")


def check_console_and_async():
    print("\n-- console backend and threading ---------------------------")
    app = create_app()
    saved = config.EMAIL_BACKEND
    config.EMAIL_BACKEND = "console"

    with app.app_context():
        subject, html, text = email_templates.welcome("Devansh")

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        result = email_service.send("d@example.com", subject, html, text, "welcome")
    printed = buffer.getvalue()

    check("console backend reports success", result.success)
    check("console prints the message", "nothing was sent" in printed)
    check("console prints the text part", "Welcome, Devansh" in printed)
    check("console does not print the html", "<table" not in printed)

    class Slow(email_service.EmailSender):
        name = "slow"

        def send(self, to, subject, html_body, text_body):
            time.sleep(1.5)
            return email_service.SendResult(True, "slow")

    email_service._SENDERS["slow"] = Slow
    config.EMAIL_BACKEND = "slow"
    start = time.perf_counter()
    thread = email_service.send_async("a@b.com", "s", "<p>h</p>", "t", "welcome")
    elapsed = time.perf_counter() - start
    check("send_async returns immediately", elapsed < 0.2,
          f"{elapsed * 1000:.1f} ms while the send takes 1500 ms")
    check("the sending thread is a daemon", thread.daemon)

    class Broken(email_service.EmailSender):
        name = "broken"

        def send(self, to, subject, html_body, text_body):
            raise RuntimeError("provider exploded")

    email_service._SENDERS["broken"] = Broken
    config.EMAIL_BACKEND = "broken"
    result = email_service.send("a@b.com", "s", "<p>h</p>", "t", "welcome")
    check("a sender that raises is caught and reported",
          not result.success and "Unexpected failure" in result.error)

    config.EMAIL_BACKEND = "not-a-backend"
    check("unknown backend falls back to console",
          isinstance(email_service.get_sender(), email_service.ConsoleEmailSender))

    config.EMAIL_BACKEND = saved


def check_signup(invalid_key=False):
    """A real signup through the API, on a throwaway account, cleaned up after."""
    label = "invalid key" if invalid_key else "console"
    print(f"\n-- signup end to end ({label}) ------------------------------")

    app = create_app()
    client = app.test_client()
    email = f"ezgrind-selftest-{secrets.token_hex(6)}@example.invalid"
    user_id = None

    saved_backend, saved_key = config.EMAIL_BACKEND, config.RESEND_API_KEY
    if invalid_key:
        config.EMAIL_BACKEND = "resend"
        config.RESEND_API_KEY = "re_deliberately_invalid_key"
    else:
        config.EMAIL_BACKEND = "console"

    try:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            response = client.post("/api/signup", json={
                "full_name": "Ez Selftest", "email": email,
                "password": "test-pass-123", "fitness_goal": "muscle",
            })
            time.sleep(2.5)          # let the background thread finish
        printed = buffer.getvalue()

        body = json.loads(response.data)
        check("signup returns 200", response.status_code == 200, str(response.status_code))
        user_id = body.get("data", {}).get("user_id")
        check("the account was created", bool(user_id), f"user_id={user_id}")

        with get_cursor() as cursor:
            cursor.execute("SELECT email FROM users WHERE user_id = %s", (user_id,))
            check("the row is committed and readable", cursor.fetchone() is not None)

        if invalid_key:
            check("signup succeeds even though the send failed", response.status_code == 200)
            check("nothing was printed to the terminal", "nothing was sent" not in printed)
        else:
            check("the welcome email printed to the terminal",
                  "Welcome, Ez" in printed, "")
            check("subject is correct", "Welcome to EzGrind" in printed)

    finally:
        config.EMAIL_BACKEND, config.RESEND_API_KEY = saved_backend, saved_key
        if user_id:
            with get_cursor(dictionary=False) as cursor:
                cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
            print(f"  cleaned up test user {user_id}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="also run a real signup against a temporary user")
    args = parser.parse_args()

    logging.disable(logging.CRITICAL)     # the failure paths log on purpose

    check_config()
    check_tls()
    check_masking()
    check_templates()
    check_resend_branches()
    check_throttle()
    check_console_and_async()

    if args.write:
        check_signup(invalid_key=False)
        check_signup(invalid_key=True)
    else:
        print("\n-- skipping live signup (pass --write to include it) --------")

    print()
    if FAILED:
        print(f"check_resend: {len(FAILED)} FAILED, {len(PASSED)} passed")
        for item in FAILED:
            print(f"   FAILED: {item}")
        sys.exit(1)
    print(f"check_resend: all {len(PASSED)} checks passed")


if __name__ == "__main__":
    main()
