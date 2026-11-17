#!/bin/sh
# Container start-up: apply migrations (waiting for PostgreSQL), create the first administrator once, then run the API.
set -e

attempt=0
until alembic upgrade head; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "Database migrations failed after $attempt attempts; check DATABASE_URL and the db container." >&2
    exit 1
  fi
  echo "Waiting for the database (attempt $attempt)..."
  sleep 2
done

if [ -n "$ADMIN_EMAIL" ] && [ -n "$ADMIN_PASSWORD" ]; then
  # Exits non-zero when the account already exists; that is expected on every restart after the first.
  printf '%s\n' "$ADMIN_PASSWORD" | python -m app.cli create-admin \
    --email "$ADMIN_EMAIL" --display-name "${ADMIN_DISPLAY_NAME:-Administrator}" --password-stdin || true
fi

exec "$@"
