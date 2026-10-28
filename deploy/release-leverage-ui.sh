#!/usr/bin/env bash
# Existing, migrated SmartPips production only. No migrations or exchange orders.
set -Eeuo pipefail
umask 077
cd "$(dirname "$0")/.."
STATE=""
trap 'echo "STOP: release failed at line $LINENO. Do not rerun old migration scripts. Release state: ${STATE:-not created}. Send the last error; do not share .env files."' ERR
[[ "${CONFIRM_SMARTPIPS_RELEASE:-0}" == 1 ]] || { echo 'Set CONFIRM_SMARTPIPS_RELEASE=1 to deploy.'; exit 1; }
C=(docker compose -p smartpips -f docker-compose.yml -f docker-compose.demo.yml)
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
# Compare actual container environments, not config's rendered dollar escaping.
assert env.get('DJANGO_SECRET_KEY'), 'STOP: running secret is unavailable'
probe_code = (
    "import os,sys; expected=sys.stdin.read(); "
    "sys.exit(0 if os.environ.get('DJANGO_SECRET_KEY') == expected else 42)"
)
probe = subprocess.run(
    ['docker','compose','-p','smartpips',
     '-f','docker-compose.yml','-f','docker-compose.demo.yml',
     'run','--rm','--no-deps','--pull','never','-T',
     '--entrypoint','python','backend','-c',probe_code],
    input=env['DJANGO_SECRET_KEY'], capture_output=True, text=True,
)
assert probe.returncode == 0, (
    'STOP: actual Compose environment key check failed; no deployment performed. '
    'Probe exit code: ' + str(probe.returncode)
)
assert config['services']['backend']['environment'].get('POSTGRES_HOST') == 'smartpips-postgres', 'STOP: unexpected database host'
print('CONFIG_AND_RUNNING_SECRET_MATCH')
PY
STATE="/root/smartpips-backups/leverage-ui-$(date +%Y%m%d-%H%M%S)"
install -d -m 700 "$STATE"
exec > >(tee -a "$STATE/release.log") 2>&1
TAG="leverage-ui-before-$(date +%Y%m%d-%H%M%S)"
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
# New code must work against the schema already deployed. Never apply migrations here.
"${C[@]}" run --rm --no-deps backend python manage.py shell -c "from django.db import connection; assert connection.vendor == 'postgresql'; assert connection.settings_dict['NAME'] == 'smartpips'; assert connection.settings_dict['HOST'] == 'smartpips-postgres'; print('PRODUCTION_DATABASE_TARGET_OK')"
"${C[@]}" run --rm --no-deps backend python manage.py check
"${C[@]}" run --rm --no-deps backend python manage.py migrate --check
"${C[@]}" up -d --no-build --no-deps backend frontend
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
printf '%s\n' "$STATE" > /root/smartpips-last-leverage-ui-release
echo "RELEASE_READY: $STATE"
echo 'No migrations applied. No systemd service or demo-monitor was started/stopped by this script.'
echo 'Now verify browser login, refresh, charts and DEMO orders. No real order is required for acceptance.'
