#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test -f backend/.env || { echo 'Missing production backend/.env; STOP'; exit 1; }
test -n "${BACKUP_FILE:-}" && test -s "$BACKUP_FILE" || { echo 'Set BACKUP_FILE to a verified restorable PostgreSQL backup'; exit 1; }
[[ "${STAGING_VERIFIED:-0}" == "1" ]] || { echo 'Restore backup and verify this upgrade in staging; then set STAGING_VERIFIED=1'; exit 1; }
compose=(docker compose -f docker-compose.yml -f docker-compose.demo.yml)
[[ "${ENABLE_RESEARCH:-0}" != "1" ]] || compose+=(-f docker-compose.research.yml)
"${compose[@]}" build backend frontend
"${compose[@]}" run --rm --no-deps backend python manage.py showmigrations accounts trades ctrader strategy
"${compose[@]}" run --rm --no-deps backend python manage.py prepare_entry_audit --require-persistent-db
[[ "${APPLY_AUDIT_MIGRATIONS:-0}" == "1" ]] || { echo 'Review the inspected additive plan; set APPLY_AUDIT_MIGRATIONS=1 only after approval'; exit 1; }
# Stop old writers before schema changes; never touch persistent volumes.
"${compose[@]}" stop backend demo-monitor
"${compose[@]}" run --rm --no-deps backend python manage.py prepare_entry_audit --require-persistent-db --apply
"${compose[@]}" run --rm --no-deps backend python manage.py check
"${compose[@]}" up -d backend frontend
if [[ "${START_DEMO_MONITOR:-0}" == "1" ]]; then
  "${compose[@]}" up -d demo-monitor
else
  echo "demo-monitor remains stopped; explicitly set START_DEMO_MONITOR=1 after review."
fi
"${compose[@]}" ps
"${compose[@]}" logs --tail=50 backend demo-monitor
