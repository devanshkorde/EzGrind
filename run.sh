#!/usr/bin/env bash
# Starts the EzGrind backend on macOS or Linux. The Windows equivalent is
# run.ps1 next to this file; both do the same three things.
#
#   ./run.sh
#
# LOCAL DEVELOPMENT ONLY. This runs Flask's built-in server, which is
# single-threaded and not meant to face the internet. Production runs gunicorn -
# see the Render start command in README.md.
#
# Leave the window open: Flask's reloader picks up .py changes on its own.
# Frontend files are served by this process too, so they need only a refresh.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/EzGrind/Backend"

# venv layout differs by platform: POSIX builds bin/, Windows python.org builds
# Scripts/. Accept whichever is present so this works in WSL and Git Bash too.
PYTHON=""
for candidate in "$BACKEND/venv/bin/python" "$BACKEND/venv/bin/python3" \
                 "$BACKEND/venv/Scripts/python.exe"; do
    if [ -x "$candidate" ]; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "No virtualenv found under EzGrind/Backend/venv" >&2
    echo >&2
    echo "Create one with:" >&2
    echo "  cd \"$BACKEND\"" >&2
    echo "  python3 -m venv venv" >&2
    echo "  ./venv/bin/python -m pip install -r requirements.txt" >&2
    exit 1
fi

if [ ! -f "$BACKEND/.env" ]; then
    echo "EzGrind/Backend/.env is missing." >&2
    echo >&2
    echo "The app refuses to start without SECRET_KEY and DATABASE_URL. Create it with:" >&2
    echo "  cd \"$BACKEND\"" >&2
    echo "  cp .env.example .env" >&2
    echo "  # then fill in SECRET_KEY and DATABASE_URL (Neon -> Connection Details)" >&2
    exit 1
fi

echo "EzGrind  http://127.0.0.1:5000"
echo "Open that address, not Live Server - Flask serves the frontend too, and"
echo "the session cookie is same-origin."
echo "Ctrl+C to stop."
echo

cd "$BACKEND"
exec "$PYTHON" app.py
