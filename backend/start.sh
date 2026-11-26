#!/bin/sh
# Container entry point: update the database schema, optionally add demo
# data, then start the API.
set -e

alembic upgrade head

if [ "$DEMO_SEED" = "true" ]; then
  python -m app.demo_seed
fi

exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
