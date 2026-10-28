#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test -f backend/.env || { echo "Missing backend/.env; do not replace production secrets."; exit 1; }
test -n "${BACKUP_FILE:-}" && test -s "$BACKUP_FILE" || {
  echo "Set BACKUP_FILE to a verified non-empty PostgreSQL backup before continuing."; exit 1;
}
compose=(docker compose -f docker-compose.yml -f docker-compose.demo.yml)
if [[ "${ENABLE_RESEARCH:-0}" == "1" ]]; then
  compose+=(-f docker-compose.research.yml)
fi
"${compose[@]}" build backend frontend
"${compose[@]}" run --rm --no-deps backend python manage.py prepare_refresh --require-persistent-db
"${compose[@]}" run --rm --no-deps backend python manage.py prepare_alerts --require-persistent-db
"${compose[@]}" run --rm --no-deps backend python manage.py prepare_trade_accounting --require-persistent-db
"${compose[@]}" run --rm --no-deps backend python manage.py check
"${compose[@]}" up -d backend frontend demo-monitor
"${compose[@]}" ps
"${compose[@]}" logs --tail=60 backend demo-monitor
echo "Historical PnL unchanged. No REAL orders sent; demo risk v1 defaults enabled."