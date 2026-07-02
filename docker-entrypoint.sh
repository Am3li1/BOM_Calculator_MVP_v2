#!/usr/bin/env bash
set -euo pipefail

# ── Database readiness check (skipped for SQLite) ──────────────────────────
DATABASE_URL="${DATABASE_URL:-}"

if echo "$DATABASE_URL" | grep -q "^postgres"; then
    DB_HOST=$(echo "$DATABASE_URL" | sed -E 's|.*@([^:]+):([0-9]+)/.*|\1|')
    DB_PORT=$(echo "$DATABASE_URL" | sed -E 's|.*@([^:]+):([0-9]+)/.*|\2|')
    MAX_RETRIES=30
    COUNT=0

    echo "==> Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT}..."
    until python -c "
import socket, sys
try:
    s = socket.create_connection(('${DB_HOST}', ${DB_PORT}), timeout=2)
    s.close(); sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
        COUNT=$((COUNT + 1))
        if [ "$COUNT" -ge "$MAX_RETRIES" ]; then
            echo "ERROR: Database not reachable after $MAX_RETRIES attempts. Aborting."
            exit 1
        fi
        echo "    ...not ready yet ($COUNT/$MAX_RETRIES). Retrying in 2s."
        sleep 2
    done
    echo "==> PostgreSQL is ready."
else
    echo "==> Using SQLite — skipping database wait."
fi

# ── Django startup ──────────────────────────────────────────────────────────
echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "==> Starting Gunicorn..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --threads "${GUNICORN_THREADS:-2}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --keep-alive 5 \
    --log-level "${GUNICORN_LOG_LEVEL:-info}" \
    --access-logfile - \
    --error-logfile -