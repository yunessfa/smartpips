#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

trap 'echo "STOP: upgrade failed at line $LINENO. Services may remain stopped. Do not use --fake or delete data; send the last error."' ERR

cd /home/ubuntu/smartpips

[[ "${CONFIRM_SMARTPIPS_MAINTENANCE:-0}" == 1 ]] || {
  echo 'Maintenance confirmation required'
  exit 1
}

C=(docker compose -p smartpips -f docker-compose.yml -f docker-compose.demo.yml)

NEW_BACKEND=$(docker image inspect -f '{{.Id}}' smartpips-backend:audit-staging)
NEW_FRONTEND=$(docker image inspect -f '{{.Id}}' smartpips-frontend:audit-staging)

for service in backend frontend; do
  [[ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "smartpips-$service")" == smartpips ]]
done

STATE="/root/smartpips-backups/release-$(date +%Y%m%d-%H%M%S)"
install -d -m 700 "$STATE"
printf '%s\n' "$STATE" > /root/smartpips-last-audit-release

exec > >(tee -a "$STATE/deploy.log") 2>&1

"${C[@]}" config --quiet 2> "$STATE/compose-check.log"

if grep -Eqi 'is not set|defaulting to a blank string' "$STATE/compose-check.log"; then
  echo 'STOP: Compose interpolation warning. Review backend/.env locally, without sharing secrets.'
  exit 1
fi

TAG="pre-audit-live-$(date +%Y%m%d-%H%M%S)"

for service in backend frontend; do
  docker image tag \
    "$(docker inspect -f '{{.Image}}' "smartpips-$service")" \
    "smartpips-$service:$TAG"
done

printf '%s\n' "$TAG" > "$STATE/rollback-image-tag.txt"
cp -p backend/.env "$STATE/backend.env"
chmod 600 "$STATE/backend.env"
git rev-parse HEAD > "$STATE/source-commit.txt"

prod_backend() {
  docker run --rm \
    --network smartpips_network \
    --env-file backend/.env \
    -e POSTGRES_HOST=smartpips-postgres \
    -e POSTGRES_PORT=5432 \
    -e POSTGRES_DB=smartpips \
    "$NEW_BACKEND" python manage.py "$@"
}

prod_fingerprint() {
  docker exec -i smartpips-postgres sh -c \
    'exec psql -X -A -t -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:-postgres}" -d smartpips' <<'SQL'
SELECT count(*), md5(COALESCE(string_agg(
  (to_jsonb(t) - ARRAY[
    'fees_paid','funding_paid','costs_verified',
    'execution_verified','external_order_id','external_position_id',
    'execution_evidence','entry_snapshot','entry_snapshot_hash'
  ]::text[])::text,
  E'\n' ORDER BY t.id), ''))
FROM public.trades_trade t;
SQL
}

prod_backend shell -c "
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

assert connection.vendor == 'postgresql'
assert connection.settings_dict['NAME'] == 'smartpips'
assert connection.settings_dict['HOST'] == 'smartpips-postgres'

executor = MigrationExecutor(connection)
executor.loader.check_consistent_history(connection)
plan = executor.migration_plan([('trades', '0008_accounting_provenance')])

assert all(
    not backwards
    and (migration.app_label, migration.name)
        == ('trades', '0008_accounting_provenance')
    for migration, backwards in plan
), 'Unexpected or reverse migration plan'

print('PRODUCTION_PREFLIGHT_OK')
"

echo 'Beginning SmartPips maintenance.'
echo 'cTrader bridge and legacy Gunicorn will remain stopped pending review.'

systemctl stop smartpips-ctrader.service gunicorn.service
"${C[@]}" stop frontend backend demo-monitor

BACKUP="$STATE/smartpips-before-upgrade.dump"

docker exec smartpips-postgres sh -c \
  'exec pg_dump -U "${POSTGRES_USER:-postgres}" -d smartpips -Fc' > "$BACKUP"

test -s "$BACKUP"

docker exec -i smartpips-postgres \
  pg_restore --list < "$BACKUP" > "$STATE/backup.list"

sha256sum "$BACKUP" > "$STATE/backup.sha256"

BEFORE=$(prod_fingerprint)
test -n "$BEFORE"
printf '%s\n' "$BEFORE" > "$STATE/trades-before.txt"

prod_backend migrate trades 0008_accounting_provenance --noinput
prod_backend prepare_entry_audit --require-persistent-db
prod_backend prepare_entry_audit --require-persistent-db --apply
prod_backend check

AFTER=$(prod_fingerprint)
printf '%s\n' "$AFTER" > "$STATE/trades-after.txt"

[[ "$BEFORE" == "$AFTER" ]]

prod_backend shell -c "
from apps.trades.models import Trade

assert not Trade.objects.exclude(
    entry_snapshot={},
    entry_snapshot_hash=''
).exists(), 'Unexpected historical snapshots'

print('HISTORICAL_SNAPSHOTS_EMPTY_OK')
"

echo "LEGACY_TRADE_DATA_UNCHANGED: $AFTER"

docker image tag "$NEW_BACKEND" smartpips-backend:latest
docker image tag "$NEW_FRONTEND" smartpips-frontend:latest

"${C[@]}" up -d --no-build --no-deps --force-recreate backend frontend

curl \
  --retry 10 \
  --retry-connrefused \
  --retry-delay 1 \
  --fail --silent --show-error \
  -H 'Host: smartpips.ir' \
  http://127.0.0.1:8001/api/auth/config/ > /dev/null

curl \
  --retry 10 \
  --retry-connrefused \
  --retry-delay 1 \
  --fail --silent --show-error \
  -H 'Host: smartpips.ir' \
  http://127.0.0.1:8082/ > /dev/null

"${C[@]}" ps
prod_backend showmigrations trades ctrader

echo "UPGRADE_BASE_CHECKS_PASSED  backup and logs: $STATE"
echo 'demo-monitor, legacy gunicorn.service and smartpips-ctrader.service remain stopped pending review.'
echo 'Browser login, refresh, charts and demo acceptance checks are still required.'
