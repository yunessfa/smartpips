#!/usr/bin/env bash
# Run from the project root AFTER copying the corrected source and backing up DB.
set -euo pipefail
cd "$(dirname "$0")/.."
test -f backend/.env || { echo 'backend/.env missing; keep your production environment file.' >&2; exit 1; }
docker compose build backend frontend
# Applies only accounts.0004; refuses unrelated pending migrations/schema drift.
docker compose run --rm --no-deps backend python manage.py prepare_refresh --require-persistent-db
docker compose up -d backend frontend
docker compose ps
docker compose logs --tail=80 backend
