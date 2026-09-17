# Deploying SmartPips to Ubuntu 24.04 + Cloudflare (smartpips.ir)

Final architecture:

```
Browser ──HTTPS──> Cloudflare ──HTTPS──> Nginx (your server)
                                          ├── /            -> React build (static files)
                                          ├── /static/     -> Django admin/DRF static
                                          └── /api,/admin  -> Gunicorn -> Django -> PostgreSQL
```

Everything is served from one domain, so there are **no CORS problems**.

Replace `smartpips.ir` only if you change the domain. Commands assume you SSH in as a
sudo user. `$` = run as your user, lines with `sudo` elevate as needed.

---

## 0) Point the domain at the server (Cloudflare)
In the Cloudflare dashboard → DNS:
- `A` record: name `smartpips.ir` (or `@`) → your server's IPv4. Proxy = **ON** (orange cloud).
- `A` (or `CNAME`) record: name `www` → `smartpips.ir`. Proxy = ON.

SSL/TLS → Overview → set encryption mode to **Full (strict)** (after step 7) — for now
**Flexible** also works to get the site up, but Full (strict) is the clean/secure target.

---

## 1) Server basics
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-venv python3-pip build-essential libpq-dev \
                    nginx postgresql postgresql-contrib git curl ufw

# Node.js 20 LTS (for building the React frontend)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node -v && npm -v
```

Firewall (allow SSH + web):
```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw --force enable
```

---

## 2) PostgreSQL database
```bash
sudo -u postgres psql <<'SQL'
CREATE DATABASE smartpips;
CREATE USER smartpips WITH PASSWORD 'CHANGE_ME_STRONG_DB_PASSWORD';
ALTER ROLE smartpips SET client_encoding TO 'utf8';
ALTER ROLE smartpips SET default_transaction_isolation TO 'read committed';
ALTER ROLE smartpips SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE smartpips TO smartpips;
\q
SQL

# On PostgreSQL 15+, also grant schema rights:
sudo -u postgres psql -d smartpips -c "GRANT ALL ON SCHEMA public TO smartpips;"
```

---

## 3) Get the code onto the server
```bash
sudo mkdir -p /var/www/smartpips
sudo chown -R $USER:$USER /var/www/smartpips

# Option A: upload the project zip and unzip into /var/www/smartpips
#   (so you end up with /var/www/smartpips/backend and /var/www/smartpips/frontend)
# Option B: git clone your repo into /var/www/smartpips
```
You should now have `/var/www/smartpips/backend` and `/var/www/smartpips/frontend`.

---

## 4) Backend (Django + Gunicorn)
```bash
cd /var/www/smartpips/backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Create the production .env (template is in deploy/.env.production.example)
cp ../deploy/.env.production.example .env
nano .env        # set a real DJANGO_SECRET_KEY, DB password, GROQ_API_KEY, etc.

# Generate a secret key if you need one:
python -c "import secrets; print(secrets.token_urlsafe(50))"

python manage.py migrate
python manage.py collectstatic --noinput
python manage.py seed            # demo data + indicators + default Groq model + demo user
# (optional) your own admin account:
python manage.py createsuperuser
deactivate
```

Quick local test (optional): `gunicorn --bind 127.0.0.1:8000 config.wsgi` then Ctrl-C.

---

## 5) Frontend (build the React app)
```bash
cd /var/www/smartpips/frontend
npm ci          # or: npm install
npm run build   # outputs to frontend/dist
```
The API client already calls `/api` on the same origin, so no config change is needed.

---

## 6) Gunicorn as a service
```bash
sudo cp /var/www/smartpips/deploy/gunicorn.service /etc/systemd/system/gunicorn.service

# Let www-data own the app so the service can read it
sudo chown -R www-data:www-data /var/www/smartpips

sudo systemctl daemon-reload
sudo systemctl enable --now gunicorn
sudo systemctl status gunicorn   # should be "active (running)"
```
If you edit code later: `sudo systemctl restart gunicorn`.

---

## 7) Nginx
```bash
sudo cp /var/www/smartpips/deploy/nginx-smartpips.conf /etc/nginx/sites-available/smartpips.conf
sudo ln -s /etc/nginx/sites-available/smartpips.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t          # test config
sudo systemctl reload nginx
```
Visit `http://smartpips.ir` — the app should load. Log in with `demo / demo12345`.

---

## 8) HTTPS the clean way (Cloudflare Origin Certificate)
This gives full end-to-end encryption and works perfectly with proxied DNS.

1. Cloudflare → SSL/TLS → **Origin Server** → **Create Certificate** (leave defaults,
   15-year). Copy the **certificate** and **private key**.
2. On the server:
   ```bash
   sudo mkdir -p /etc/ssl/cloudflare
   sudo nano /etc/ssl/cloudflare/smartpips.ir.pem   # paste the certificate
   sudo nano /etc/ssl/cloudflare/smartpips.ir.key   # paste the private key
   sudo chmod 600 /etc/ssl/cloudflare/smartpips.ir.key
   ```
3. In `/etc/nginx/sites-available/smartpips.conf`: uncomment the **443 server block**
   at the bottom, and in the port-80 block uncomment `return 301 https://...` to force
   HTTPS. Then:
   ```bash
   sudo nginx -t && sudo systemctl reload nginx
   ```
4. Cloudflare → SSL/TLS → set mode to **Full (strict)**.
5. (Recommended) Cloudflare → SSL/TLS → Edge Certificates → enable **Always Use HTTPS**.

Because `.env` has `USE_PROXY_SSL_HEADER=True` and `CSRF_TRUSTED_ORIGINS=https://smartpips.ir`,
the Django admin login works correctly over HTTPS behind Cloudflare.

> Alternative (Let's Encrypt): temporarily set the DNS records to **grey cloud**
> (DNS only), run `sudo apt install certbot python3-certbot-nginx` then
> `sudo certbot --nginx -d smartpips.ir -d www.smartpips.ir`, then turn the proxy
> back on. The Origin Certificate route above is simpler with Cloudflare.

---

## 9) Updating later
After pulling new code or editing files:
```bash
cd /var/www/smartpips
sudo ./deploy/update.sh
```
(installs deps, migrates, collects static, rebuilds the frontend, restarts services.)

---

## Troubleshooting
- **502 Bad Gateway** → Gunicorn isn't running: `sudo systemctl status gunicorn` and
  `sudo journalctl -u gunicorn -n 50`.
- **Admin CSS missing** → run `collectstatic` and confirm the Nginx `/static/` `alias`
  path matches `STATIC_ROOT` (`backend/staticfiles`).
- **DisallowedHost / 400** → add the domain to `DJANGO_ALLOWED_HOSTS` in `.env`,
  then `sudo systemctl restart gunicorn`.
- **Admin login "CSRF verification failed"** → check `CSRF_TRUSTED_ORIGINS` and that
  `USE_PROXY_SSL_HEADER=True`, then restart gunicorn.
- **Redirect loop** → your Cloudflare SSL mode and Nginx don't agree. Use **Full
  (strict)** with the Origin Certificate (don't force HTTPS in Nginx while Cloudflare
  is on **Flexible**).
- **Frontend updates not showing** → `npm run build` again and hard-refresh; Cloudflare
  may cache — purge cache in the dashboard if needed.
- **AI returns an error** → confirm `GROQ_API_KEY` is set in `.env` and re-run
  `python manage.py seed` (it activates the Groq model).

## Security notes
- Don't commit your real `.env` (it holds secrets). Rotate the Groq key if it leaked.
- Keep `DJANGO_DEBUG=False` in production.
- Consider Cloudflare WAF / rate-limiting and fail2ban for SSH.
