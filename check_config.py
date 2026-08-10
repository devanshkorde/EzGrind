"""Self-check for config.py. Run directly: python check_config.py

Stubs python-dotenv so the real .env cannot leak into the assertions, then
reimports config under different environments. Touches no database and needs
no server. The branch worth guarding here is the cookie matrix: SameSite=None
paired with Secure=False is silently rejected by browsers, which is the bug
this module exists to prevent.
"""

import importlib
import os
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

stub = types.ModuleType("dotenv")
stub.load_dotenv = lambda *a, **k: False
sys.modules["dotenv"] = stub

BASE = {"SECRET_KEY": "s" * 64, "DB_PASSWORD": "pw"}
OWNED = ("SECRET_KEY", "DB_PASSWORD", "FLASK_ENV", "DB_HOST", "DB_PORT",
         "DB_USER", "DB_NAME", "ALLOWED_ORIGINS", "DB_POOL_SIZE")


def load(**env):
    for key in OWNED:
        os.environ.pop(key, None)
    os.environ.update(env)
    sys.modules.pop("config", None)
    return importlib.import_module("config")


def expect_refusal(missing, **env):
    try:
        load(**env)
    except Exception as exc:
        assert type(exc).__name__ == "ConfigError", f"wrong type: {type(exc)}"
        assert missing in str(exc), f"message must name {missing}: {exc}"
        return
    raise AssertionError(f"expected refusal when {missing} is missing")


# 1. Refuses to start without secrets. No fallback default, blank is not set.
expect_refusal("SECRET_KEY", DB_PASSWORD="pw")
expect_refusal("DB_PASSWORD", SECRET_KEY="s" * 64)
expect_refusal("SECRET_KEY", SECRET_KEY="   ", DB_PASSWORD="pw")

# 2. Undeclared environment falls back to production: debug off, cookie secure.
cfg = load(**BASE)
assert cfg.IS_PRODUCTION is True
assert cfg.DEBUG is False, "debug must default to False"
assert cfg.SESSION_COOKIE_SECURE is True

# 3. Development relaxes Secure (no HTTPS locally) and nothing else.
cfg = load(FLASK_ENV="development", **BASE)
assert cfg.DEBUG is True
assert cfg.SESSION_COOKIE_SECURE is False

# 4. SameSite is Lax everywhere now that Flask serves the frontend: the cookie
#    is same-site by construction. SameSite=None is the weaker setting and only
#    existed to survive the split-origin dev setup, which is gone.
for env in ("development", "production", "staging", "DEVELOPMENT", ""):
    cfg = load(FLASK_ENV=env, **BASE)
    assert cfg.SESSION_COOKIE_SAMESITE == "Lax", env
    assert cfg.SESSION_COOKIE_HTTPONLY is True, env
assert load(FLASK_ENV="DEVELOPMENT", **BASE).DEBUG is True, "must be case-insensitive"

# 5. RESEND_API_KEY is required only when it would actually be used.
expect_refusal("RESEND_API_KEY", EMAIL_BACKEND="resend", **BASE)
assert load(EMAIL_BACKEND="console", **BASE).RESEND_API_KEY == "", \
    "console backend must start without a key"

# 5. HttpOnly is not negotiable.
assert load(FLASK_ENV="development", **BASE).SESSION_COOKIE_HTTPONLY is True

# 6. Origins: comma-split, trimmed, blanks dropped, never a wildcard.
cfg = load(ALLOWED_ORIGINS=" http://a.test , ,http://b.test ", **BASE)
assert cfg.ALLOWED_ORIGINS == ["http://a.test", "http://b.test"], cfg.ALLOWED_ORIGINS
cfg = load(**BASE)
assert cfg.ALLOWED_ORIGINS == ["http://localhost:5500", "http://127.0.0.1:5500"]
assert "*" not in cfg.ALLOWED_ORIGINS

# 7. Port is an int, and a bad value names itself in the error.
assert load(**BASE).DB_CONFIG["port"] == 3306
assert load(DB_PORT="3307", **BASE).DB_CONFIG["port"] == 3307
expect_refusal("DB_PORT", DB_PORT="abc", **BASE)

# 8. The password reaches the driver; the session secret does not.
cfg = load(**BASE)
assert cfg.DB_CONFIG["password"] == "pw"
assert "secret" not in {k.lower() for k in cfg.DB_CONFIG}

# 9. Pool size defaults sanely and rejects what mysql-connector would reject.
assert load(**BASE).DB_POOL_SIZE == 5
assert load(DB_POOL_SIZE="12", **BASE).DB_POOL_SIZE == 12
expect_refusal("DB_POOL_SIZE", DB_POOL_SIZE="0", **BASE)
expect_refusal("DB_POOL_SIZE", DB_POOL_SIZE="33", **BASE)
expect_refusal("DB_POOL_SIZE", DB_POOL_SIZE="many", **BASE)

print("check_config: all 9 checks passed")
