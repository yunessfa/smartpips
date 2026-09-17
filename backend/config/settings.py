"""
Django settings for the Trade Assistant project.
"""
from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-change-me-in-production")
DEBUG = os.getenv("DJANGO_DEBUG", "True") == "True"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third party
    "rest_framework",
    "corsheaders",
    # local apps
    "apps.accounts",
    "apps.market",
    "apps.sources",
    "apps.strategy",
    "apps.trades",
    "apps.ai",
    "apps.chat",
    "apps.alerts",
    "apps.mt5",
    "apps.ctrader",
    "apps.lbank",
    "apps.bitunix",
    "apps.prefs",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Use PostgreSQL when POSTGRES_DB (or DATABASE_URL) is provided, else SQLite.
# This keeps local dev zero-config while supporting per-user Postgres in prod.
if os.getenv("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB"),
            "USER": os.getenv("POSTGRES_USER", "postgres"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Shared cache across all gunicorn workers (file-based, no extra services needed).
# Used to share fetched candles so we don't burn the Twelve Data quota per-worker.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": str(BASE_DIR / ".cache"),
        "TIMEOUT": 120,
        "OPTIONS": {"MAX_ENTRIES": 2000},
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.ExpiringTokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # Rate limiting: protects login from brute force and caps order spam.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "login": "8/min",
        "order": "30/min",
        "anon": "60/min",
    },
}

# Bearer tokens expire after this many seconds (1 day).
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", 60 * 60 * 24))

# CORS — allow the Vite dev server during development.
CORS_ALLOWED_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
).split(",")
CORS_ALLOW_CREDENTIALS = True

# --- Production / behind Cloudflare ---
# Domains allowed to submit the Django admin login form over HTTPS.
CSRF_TRUSTED_ORIGINS = [
    o for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o
]
# Cloudflare/Nginx terminate TLS and forward this header so Django knows it's HTTPS.
if os.getenv("USE_PROXY_SSL_HEADER", "False") == "True":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Optional default key picked up from environment if you prefer not to store
# it in the database. The AI management page can override this per-provider.
DEFAULT_DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# ---- Web Push (scalp alerts) ----
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_CLAIM_EMAIL = os.getenv("VAPID_CLAIM_EMAIL", "mailto:admin@smartpips.ir")

# ---- MT5 bridge (EA <-> server shared secret) ----
MT5_BRIDGE_KEY = os.getenv("MT5_BRIDGE_KEY", "")

# ---- cTrader Open API ----
CTRADER_CLIENT_ID = os.getenv("CTRADER_CLIENT_ID", "")
CTRADER_CLIENT_SECRET = os.getenv("CTRADER_CLIENT_SECRET", "")
CTRADER_HOST = os.getenv("CTRADER_HOST", "demo.ctraderapi.com")  # or live.ctraderapi.com
CTRADER_REDIRECT_URI = os.getenv("CTRADER_REDIRECT_URI", "https://smartpips.ir/api/ctrader/callback/")
CTRADER_GOLD_SYMBOL = os.getenv("CTRADER_GOLD_SYMBOL", "XAUUSD")
CTRADER_SILVER_SYMBOL = os.getenv("CTRADER_SILVER_SYMBOL", "XAGUSD")

# ---- Bitunix (RESTORED 2026-09-05 — live again) ----
# Rolled back the 2026-09 shutdown: Bitunix is the crypto data + execution
# venue again. Gold/silver are the ONLY thing still on LBank (see
# METALS_DATA_SOURCE below), so the two venues never quote the same symbol.
BITUNIX_API_KEY = os.getenv("BITUNIX_API_KEY", "")
BITUNIX_SECRET_KEY = os.getenv("BITUNIX_SECRET_KEY", "")
BITUNIX_BASE_URL = os.getenv("BITUNIX_BASE_URL", "https://fapi.bitunix.com")
# which venue feeds crypto-perp candles/ticks: bitunix (single-source with
# execution) or binance (legacy)
CRYPTO_PERP_DATA_SOURCE = os.getenv("CRYPTO_PERP_DATA_SOURCE", "bitunix")

LBANK_API_KEY = os.getenv("LBANK_API_KEY", "")
LBANK_SECRET_KEY = os.getenv("LBANK_SECRET_KEY", "")
LBANK_BASE_URL = os.getenv("LBANK_BASE_URL", "https://api.lbkex.com")
# "HmacSHA256" (default) or "MD5" — try MD5 if HmacSHA256 gives "Invalid signature"
LBANK_SIGN_METHOD = os.getenv("LBANK_SIGN_METHOD", "HmacSHA256")
# LBank USDT-margined futures host — also the source of gold/silver
# (GOLD(XAU)USDT Perp, SILVER(XAG)USDT Perp) since 2026-09.
LBANK_FUTURES_BASE_URL = os.getenv("LBANK_FUTURES_BASE_URL", "https://lbkperp.lbank.com")
# Metals data source: "lbank" (current) or "legacy" to re-enable the old
# cTrader/MT5 -> gold-api.com -> iTick -> Twelve Data stack, which is
# commented out (not deleted) in apps/market/metals.py and candles.py.
METALS_DATA_SOURCE = os.getenv("METALS_DATA_SOURCE", "lbank")


# ---------------------------------------------------------------------------
# Logging / observability  (fixes T-2 from the technical review)
# ---------------------------------------------------------------------------
# Before this block there was no LOGGING config at all: 46 `except Exception`
# blocks swallowed their errors and the only trace of anything was gunicorn's
# access log in journald. Now every logger writes JSON lines to both stdout
# (journald/docker) and a rotating file that /api/logs/ can read back.
#
# The directory is created here rather than by an ops step, because a missing
# logs/ folder makes Django fail at startup with a confusing traceback.
LOG_DIR = BASE_DIR / "logs"
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    # Read-only filesystem: fall back to console-only logging instead of
    # refusing to boot. Losing the log file is bad; not starting is worse.
    LOG_DIR = None

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": '{"t":"%(asctime)s","lvl":"%(levelname)s",'
                      '"logger":"%(name)s","msg":"%(message)s"}',
        },
        # Human-readable, used when DEBUG so local dev output stays readable.
        "plain": {
            "format": "%(asctime)s %(levelname)-8s %(name)s | %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "plain" if DEBUG else "json",
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        # Order path gets its own logger so "what happened to my order" is one
        # grep away instead of buried in request noise.
        "smartpips.orders": {"level": "INFO"},
        "smartpips.alerts": {"level": "INFO"},
        "smartpips.market": {"level": "INFO"},
        "django.request": {"level": "ERROR", "propagate": True},
        # Django's DB logger at DEBUG would log every single query — pin it.
        "django.db.backends": {"level": "WARNING", "propagate": True},
    },
}

if LOG_DIR is not None:
    LOGGING["handlers"]["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": str(LOG_DIR / "smartpips.log"),
        "maxBytes": 20_000_000,   # 20 MB per file
        "backupCount": 10,        # ~200 MB of history, then oldest is dropped
        "formatter": "json",
        "encoding": "utf-8",
        # delay=True: don't create/lock the file until something is actually
        # logged, which keeps `manage.py collectstatic` etc. side-effect free.
        "delay": True,
    }
    LOGGING["root"]["handlers"] = ["console", "file"]
