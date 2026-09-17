#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/backend"
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -r requirements.txt
python manage.py makemigrations accounts market sources strategy trades ai chat
python manage.py migrate
python manage.py seed
echo ">> Backend ready at http://localhost:8000  (admin: create with 'python manage.py createsuperuser')"
python manage.py runserver
