"""Transactional email: one interface, swappable providers.

Nothing outside this module may make an HTTP call to Resend. Swapping to
Postmark or SES has to be a new EmailSender subclass and one line of .env, not
a search through route files for api.resend.com.

Three rules this module exists to enforce:

  * A send can never fail the thing that triggered it. Callers get a SendResult
    describing what happened; nothing here raises into a request handler.
  * Sends happen on a background thread, so a signup never waits on a network
    call to a third party.
  * Addresses are masked in logs and bodies are never logged at all.

WHY urllib AND NOT requests OR THE resend PACKAGE
    The whole API surface needed here is one POST with a Bearer header and a
    JSON body. The `resend` package depends on `requests`, which brings
    urllib3, certifi, charset-normalizer and idna - five new dependencies for
    fifteen lines of stdlib. This project ships six dependencies in total and
    the retry policy below is hand-written anyway, since neither library
    implements the "429 only, three attempts" rule for free.
"""

import functools
import json
import logging
import ssl
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

import config

logger = logging.getLogger("ezgrind.email")

RESEND_ENDPOINT = "https://api.resend.com/emails"

# Resend allows 2 requests/second account-wide. 0.55s leaves headroom for clock
# jitter without meaningfully slowing anything at this volume.
MIN_SEND_INTERVAL = 0.55

MAX_ATTEMPTS = 3
BACKOFF_BASE = 1.0          # 1s, then 2s, then give up
HTTP_TIMEOUT = 15

# Resend sits behind Cloudflare, which rejects urllib's default
# "Python-urllib/3.10" agent outright with a plain-text 403 (error code 1010)
# that never reaches Resend at all. Any ordinary agent string gets through.
USER_AGENT = "EzGrind/1.0"


@dataclass
class SendResult:
    """What happened. Never an exception - callers are on a happy path already."""

    success: bool
    provider_message_id: str = None
    error: str = None


@functools.lru_cache(maxsize=1)
def _ssl_context():
    """A TLS context that can actually verify a certificate.

    ssl.create_default_context() trusts whatever CA bundle the interpreter was
    built to look for, and some builds point at a path that does not exist. The
    MSYS2/mingw64 Python this project runs on is one: it looks for
    C:/msys64/mingw64/etc/ssl/cert.pem, finds nothing, and loads ZERO CA
    certificates - so every HTTPS request fails CERTIFICATE_VERIFY_FAILED,
    against any host, not just Resend.

    certifi is Mozilla's CA bundle as a Python package, with no dependencies of
    its own. Preferring it makes verification behave the same everywhere
    instead of depending on how the interpreter was compiled.

    Verification is never disabled. An unverified TLS connection to a service
    being handed an API key is worse than no email at all.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
        if context.cert_store_stats()["x509_ca"] == 0:
            logger.error(
                "This Python has no CA certificates, so no HTTPS request can be "
                "verified. Run: pip install certifi"
            )
        return context


def mask_email(address):
    """d****h@gmail.com - enough to match a support request, not enough to leak.

    The domain stays readable because "did it go to gmail or to their work
    address" is the question a bug report usually turns on.
    """
    local, at, domain = str(address or "").partition("@")
    if not at:
        return "****"
    if len(local) <= 2:
        return f"{local[:1]}****@{domain}"
    return f"{local[0]}****{local[-1]}@{domain}"


# ============================================================
# RATE LIMITING
# ============================================================

_throttle_lock = threading.Lock()
_last_send_at = 0.0


def _throttle():
    """Block until at least MIN_SEND_INTERVAL has passed since the last send.

    The sleep happens while holding the lock, deliberately: that serialises
    every sender in the process behind one queue, which is exactly the
    account-wide limit Resend enforces. Letting threads sleep concurrently
    would let them all wake at once and burst.

    ponytail: per-process only. Two Flask workers can still reach 4/s between
    them. Upgrade path is a shared counter in Redis, worth doing only if this
    ever runs multi-process.
    """
    global _last_send_at
    with _throttle_lock:
        wait = MIN_SEND_INTERVAL - (time.monotonic() - _last_send_at)
        if wait > 0:
            time.sleep(wait)
        _last_send_at = time.monotonic()


# ============================================================
# SENDERS
# ============================================================

class EmailSender:
    """The whole contract. A provider implements send() and nothing else."""

    name = "base"

    def send(self, to, subject, html_body, text_body):
        raise NotImplementedError


class ConsoleEmailSender(EmailSender):
    """Prints the message instead of sending it.

    The default in development, and the reason the whole signup flow can be run
    fifty times while building without spending any of the 100/day quota.
    """

    name = "console"

    def send(self, to, subject, html_body, text_body):
        print(
            "\n" + "=" * 72
            + "\n  EMAIL (console backend - nothing was sent)"
            + f"\n  To:      {to}"
            + f"\n  From:    {config.MAIL_FROM_NAME} <{config.MAIL_FROM_ADDRESS}>"
            + f"\n  Subject: {subject}"
            + "\n" + "-" * 72
            + f"\n{text_body}"
            + "\n" + "=" * 72 + "\n",
            flush=True,
        )
        return SendResult(True, provider_message_id="console")


class ResendEmailSender(EmailSender):
    """Delivery via the Resend HTTP API."""

    name = "resend"

    def send(self, to, subject, html_body, text_body):
        if not config.RESEND_API_KEY:
            return SendResult(False, error=(
                "RESEND_API_KEY is not set. Add it to Backend/.env, or set "
                "EMAIL_BACKEND=console to print emails instead of sending them."
            ))

        payload = json.dumps({
            "from": f"{config.MAIL_FROM_NAME} <{config.MAIL_FROM_ADDRESS}>",
            "to": [to],
            "subject": subject,
            "html": html_body,
            "text": text_body,
        }).encode("utf-8")

        for attempt in range(1, MAX_ATTEMPTS + 1):
            _throttle()
            result, retryable = self._attempt(payload)
            if result.success or not retryable:
                return result

            if attempt < MAX_ATTEMPTS:
                delay = BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning("resend rate limited, retrying in %.1fs (attempt %d/%d)",
                               delay, attempt, MAX_ATTEMPTS)
                time.sleep(delay)

        return SendResult(False, error=(
            f"Rate limited by Resend after {MAX_ATTEMPTS} attempts. "
            "The free tier allows 2 requests/second and 100 emails/day."
        ))

    def _attempt(self, payload):
        """One POST. Returns (result, retryable)."""
        request = urllib.request.Request(
            RESEND_ENDPOINT,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {config.RESEND_API_KEY}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
        )

        try:
            with urllib.request.urlopen(
                request, timeout=HTTP_TIMEOUT, context=_ssl_context()
            ) as response:
                body = json.loads(response.read().decode("utf-8") or "{}")
            return SendResult(True, provider_message_id=body.get("id")), False

        except urllib.error.HTTPError as exc:
            return self._classify(exc), exc.code == 429

        except urllib.error.URLError as exc:
            # A failed handshake arrives wrapped in URLError, so the specific
            # cause has to be dug out of .reason - otherwise a missing CA
            # bundle reads as "the network is down", which sends anyone
            # debugging it in entirely the wrong direction.
            if isinstance(exc.reason, ssl.SSLCertVerificationError):
                return SendResult(False, error=(
                    "TLS certificate verification failed. This Python cannot "
                    "verify any HTTPS certificate - its CA bundle is missing. "
                    "Fix with: pip install certifi. "
                    f"Underlying error: {exc.reason}"
                )), False
            return SendResult(False, error=f"Could not reach Resend: {exc}"), False

        except (TimeoutError, OSError, ssl.SSLError) as exc:
            # Network-level failure. Not retried: the caller already has their
            # account, and a burst of retries against a down provider only
            # delays the log entry that says so.
            return SendResult(False, error=f"Could not reach Resend: {exc}"), False

        except json.JSONDecodeError as exc:
            return SendResult(False, error=f"Resend returned unreadable JSON: {exc}"), False

    def _classify(self, exc):
        """Turn an HTTP error into a message that says what to actually do.

        The two failures this project will really hit both come back as a
        generic 403, and "API error 403" tells nobody anything. Until a domain
        is verified, Resend only accepts onboarding@resend.dev as a sender and
        only the account owner's address as a recipient - so those two cases
        get named explicitly.
        """
        raw = ""
        message = ""
        try:
            raw = exc.read().decode("utf-8", errors="replace").strip()
            detail = json.loads(raw)
            message = detail.get("message") or detail.get("name") or ""
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError, OSError):
            # Not JSON. Something in front of the API answered - a proxy, a WAF,
            # a load balancer. Keep the raw text: it is the only description of
            # the failure that exists, and discarding it is how this once
            # produced "Resend returned HTTP 403:" with nothing after the colon.
            message = raw

        # Anything not from the API itself never reached Resend, so no Resend
        # error code applies and none should be guessed at.
        if raw and not raw.startswith("{"):
            return SendResult(False, error=(
                f"Blocked before reaching Resend (HTTP {exc.code}). The API sits "
                f"behind Cloudflare, which rejects some clients by User-Agent. "
                f"Response was not JSON: {raw[:200]!r}"
            ))

        lowered = message.lower()

        if "not verified" in lowered or "verify a domain" in lowered:
            return SendResult(False, error=(
                f"domain not verified in Resend - MAIL_FROM_ADDRESS="
                f"{config.MAIL_FROM_ADDRESS} is not a verified sender. "
                f"Use onboarding@resend.dev until the domain is verified at "
                f"https://resend.com/domains. Resend said: {message}"
            ))

        if "own email address" in lowered or "testing emails" in lowered:
            return SendResult(False, error=(
                "Resend test mode - an unverified account can only send to the "
                "address that owns it. Verify a domain to send anywhere else. "
                f"Resend said: {message}"
            ))

        if exc.code == 401:
            return SendResult(False, error=(
                "Resend rejected the API key (401). Check RESEND_API_KEY in "
                f"Backend/.env. Resend said: {message}"
            ))

        if exc.code == 429:
            return SendResult(False, error=f"Rate limited (429). {message}")

        return SendResult(False, error=f"Resend returned HTTP {exc.code}: {message}")


_SENDERS = {"console": ConsoleEmailSender, "resend": ResendEmailSender}


def get_sender():
    """The provider named by EMAIL_BACKEND.

    An unrecognised name falls back to console rather than raising. Refusing to
    start over a typo would take the whole app down for a feature it can run
    without, and console fails visibly in the log on every send.
    """
    sender_class = _SENDERS.get(config.EMAIL_BACKEND)
    if sender_class is None:
        logger.warning("EMAIL_BACKEND=%r is not one of %s - using console.",
                       config.EMAIL_BACKEND, ", ".join(sorted(_SENDERS)))
        sender_class = ConsoleEmailSender
    return sender_class()


# ============================================================
# PUBLIC API
# ============================================================

def send(to, subject, html_body, text_body, template="unknown"):
    """Send now, on this thread. Always returns a SendResult, never raises."""
    sender = get_sender()
    masked = mask_email(to)

    try:
        result = sender.send(to, subject, html_body, text_body)
    except Exception as exc:                                     # noqa: BLE001
        logger.exception("email[%s] template=%s to=%s CRASHED",
                         sender.name, template, masked)
        return SendResult(False, error=f"Unexpected failure: {exc}")

    if result.success:
        # The message id is the only handle on a delivered email. When someone
        # says "I never got it", this is what gets looked up in the dashboard.
        logger.info("email[%s] template=%s to=%s SENT id=%s",
                    sender.name, template, masked, result.provider_message_id)
    else:
        logger.error("email[%s] template=%s to=%s FAILED: %s",
                     sender.name, template, masked, result.error)
    return result


def send_async(to, subject, html_body, text_body, template="unknown"):
    """Hand the send to a background thread and return immediately.

    A signup must not wait on Resend. The account row is committed before this
    is called, so nothing the network does here can cost the user their
    account - at worst it costs them an email, and that is a log entry.

    Daemon thread: an in-flight send must never hold the process open at
    shutdown. There is no durability here and none is claimed; a dropped email
    is a dropped email, which is why the outcome is logged.
    """
    thread = threading.Thread(
        target=send,
        args=(to, subject, html_body, text_body, template),
        name="ezgrind-email",
        daemon=True,
    )
    thread.start()
    return thread


def warn_if_unconfigured():
    """Called once at boot so misconfiguration is found before a user hits it."""
    if config.EMAIL_BACKEND == "resend" and not config.RESEND_API_KEY:
        logger.warning(
            "EMAIL_BACKEND=resend but RESEND_API_KEY is empty. The app will run "
            "and signups will succeed, but every email will fail. Set the key in "
            "Backend/.env or use EMAIL_BACKEND=console."
        )
    elif config.EMAIL_BACKEND == "console":
        logger.info("EMAIL_BACKEND=console - emails are printed, not sent.")
