#!/bin/sh
# Apply database migrations, then start the server. Fails fast (the container exits) if migrations fail.
set -eu
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    python -m alembic upgrade head
fi
exec "$@"
