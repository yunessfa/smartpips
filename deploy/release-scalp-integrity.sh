#!/usr/bin/env bash
# Scalp-integrity release (2026-10). Applies TWO additive migrations after a verified
# backup: bitunix.0003 (demo LIMIT columns) and alerts.0005 (alert diagnostics).
# Starts the alert-monitor service. No exchange orders are sent.
set -Eeuo pipefail
umask 077
cd "$(dirname "$0")/.."
STATE=""
trap 'echo "STOP: release failed at line $LINENO. Do not rerun old migration scripts. Release state: ${STATE:-not created}. Send the last error; do not share .env files."' ERR
[[ "${CONFIRM_SMARTPIPS_RELEASE:-0}" == 1 ]] || { echo 'Set CONFIRM_SMARTPIPS_RELEASE=1 to deploy.'; exit 1; }
C=(docker compose -p smartpips -f docker-compose.yml -f docker-compose.demo.yml -f docker-compose.monitor.yml)
test -f backend/.env
# Inspect privately: never print Compose's expanded configuration or the key.
python3 - <<'PY'
import json, subprocess
cfg = subprocess.run(['docker','compose','-p','smartpips','-f','docker-compose.yml','-f','docker-compose.demo.yml','config','--format','json'], capture_output=True, text=True)
assert cfg.returncode == 0, 'STOP: invalid Compose config; inspect locally without sharing secrets'
assert not cfg.stderr.strip(), 'STOP: Compose warning; inspect locally without sharing secrets'
config = json.loads(cfg.stdout)
container = json.loads(subprocess.check_output(['docker','inspect','smartpips-backend'],text=True))[0]
assert container['State']['Running'], 'STOP: backend must be running before this update'
assert container['Config']['Labels']['com.docker.compose.project'] == 'smartpips', 'STOP: unexpected Compose project'
env = dict(x.split('=',1) for x in container['Config']['Env'] if '=' in x)
key = config['services']['backend']['environment'].get('DJANGO_SECRET_KEY')
assert key and key == env.get('DJANGO_SECRET_KEY'), 'STOP: SECRET_KEY differs from running backend; no deployment performed'
assert config['services']['backend']['environment'].get('POSTGRES_HOST') == 'smartpips-postgres', 'STOP: unexpected database host'
print('CONFIG_AND_RUNNING_SECRET_MATCH')
PY
STATE="/root/smartpips-backups/scalp-integrity-$(date +%Y%m%d-%H%M%S)"
install -d -m 700 "$STATE"
exec > >(tee -a "$STATE/release.log") 2>&1
TAG="scalp-integrity-before-$(date +%Y%m%d-%H%M%S)"
for service in backend frontend; do
  docker image tag "$(docker inspect -f '{{.Image}}' "smartpips-$service")" "smartpips-$service:$TAG"
done
printf '%s\n' "$TAG" > "$STATE/rollback-tag.txt"
cp -p backend/.env "$STATE/backend.env"
cp -p docker-compose.yml docker-compose.demo.yml "$STATE/"
git rev-parse HEAD > "$STATE/source-commit.txt"
# A consistent PostgreSQL archive; existing services stay running during build.
docker exec smartpips-postgres sh -c 'exec pg_dump -U "${POSTGRES_USER:-postgres}" -d smartpips -Fc' > "$STATE/database.dump"
test -s "$STATE/database.dump"
docker exec -i smartpips-postgres pg_restore --list < "$STATE/database.dump" > "$STATE/database.list"
sha256sum "$STATE/database.dump" > "$STATE/database.sha256"
"${C[@]}" build backend frontend
"${C[@]}" run --rm --no-deps backend python manage.py shell -c "from django.db import connection; assert connection.vendor == 'postgresql'; assert connection.settings_dict['NAME'] == 'smartpips'; assert connection.settings_dict['HOST'] == 'smartpips-postgres'; print('PRODUCTION_DATABASE_TARGET_OK')"
"${C[@]}" run --rm --no-deps backend python manage.py check
# Only these two additive migrations may be pending. The trades 0002/0005 edits are
# no-ops on databases that already applied them.
"${C[@]}" run --rm --no-deps backend python manage.py showmigrations --plan > "$STATE/migrations-before.txt"
UNEXPECTED=$(grep '^\[ \]' "$STATE/migrations-before.txt" | grep -v -e 'bitunix.0003_demo_limit_orders' -e 'alerts.0005_usersignalstate_diagnostics' || true)
if [[ -n "$UNEXPECTED" ]]; then
  echo "STOP: unexpected pending migrations; nothing applied:"; echo "$UNEXPECTED"; exit 1
fi
"${C[@]}" run --rm --no-deps backend python manage.py migrate bitunix 0003
"${C[@]}" run --rm --no-deps backend python manage.py migrate alerts 0005
# Session refresh needs a correct CSRF origin behind the HTTPS proxy.
if "${C[@]}" run --rm --no-deps backend python manage.py check --deploy 2>&1 | grep -q smartpips.W001; then
  echo "WARNING: set CSRF_TRUSTED_ORIGINS=https://smartpips.ir (or USE_PROXY_SSL_HEADER=True) in backend/.env, otherwise users are logged out when their access token expires."
fi
"${C[@]}" run --rm --no-deps backend python manage.py migrate --check
"${C[@]}" up -d --no-build --no-deps backend frontend
# Alert monitor as a service (heartbeat visible on the Notifications page).
"${C[@]}" up -d --no-build --no-deps alert-monitor
if crontab -l 2>/dev/null | grep -q monitor_scalp; then
  echo "NOTE: a host cron also runs monitor_scalp. Remove that cron line now that alert-monitor runs (duplicates are harmless but wasteful)."
fi
# demo-monitor runs the same image: restart it so it fills/expires demo LIMIT orders.
if docker inspect smartpips-demo-monitor >/dev/null 2>&1 || "${C[@]}" ps --services | grep -qx demo-monitor; then
  "${C[@]}" up -d --no-build --no-deps demo-monitor
fi
wait_http() {
  local url="$1" name="$2" code
  for i in $(seq 1 30); do
    code=$(curl --max-time 5 --silent --output /dev/null --write-out '%{http_code}' -H 'Host: smartpips.ir' "$url" || true)
    if [[ "$code" == 200 ]]; then echo "${name}_HTTP=200"; return 0; fi
    sleep 2
  done
  echo "STOP: $name did not become ready; inspect container logs."
  return 1
}
wait_http http://127.0.0.1:8001/api/auth/config/ BACKEND
wait_http http://127.0.0.1:8082/ FRONTEND
"${C[@]}" ps
printf '%s\n' "$STATE" > /root/smartpips-last-scalp-integrity-release
echo "RELEASE_READY: $STATE"
echo 'Applied: bitunix.0003 + alerts.0005. Rollback: restore images by tag in rollback-tag.txt; the 3 new columns are harmless to old code.'
echo 'Now verify: login, a 5m BTC signal (stop/TP sizes), a DEMO LIMIT order (pending -> fill/expire), demo close. No real order is required.'
