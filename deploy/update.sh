#!/usr/bin/env bash
# Re-deploy after you change code. Run from /var/www/smartpips.
set -e
APP=/var/www/smartpips

echo "==> Backend"
cd "$APP/backend"
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
deactivate

echo "==> Frontend"
cd "$APP/frontend"
npm ci
npm run build

echo "==> Restart services"
sudo systemctl restart gunicorn
sudo systemctl reload nginx
echo "Done."
