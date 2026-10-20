#!/usr/bin/env bash
# After copying source and backing up the existing persistent PostgreSQL database.
set -euo pipefail
cd "$(dirname "$0")/.."
test -f backend/.env || { echo 'backend/.env missing; preserve your production .env.' >&2; exit 1; }
docker compose build backend frontend
docker compose run --rm --no-deps backend python manage.py prepare_refresh --require-persistent-db
docker compose run --rm --no-deps backend python manage.py prepare_alerts --require-persistent-db
docker compose up -d backend frontend
docker compose ps
docker compose logs --tail=80 backend
