# SmartPips — AI Trading Assistant

A bilingual (فارسی / English) trading dashboard with an AI assistant that reads
your reference sources, indicators, Telegram channels and live prices — and learns
from your own trade journal.

> ⚠️ For research & education only. **Not financial advice.**

## Features
- **Bilingual UI** (Persian/English) with full RTL support.
- **Dashboard** — large TradingView charts (now with your active indicators overlaid),
  live watchlist, auto-refresh.
- **Assistant (ChatGPT-style)** — conversation history per user; replies are anchored to
  **live prices only** (no more made-up prices); applies your indicators; can read
  Telegram signals; ends with a not-advice note.
- **References (Sources page)**:
  - **Sources** with optional RSS feeds (the bot reads recent news).
  - **Indicators** — choose RSI, MACD, EMA, Fibonacci, etc. The bot uses them in its
    analysis and they're drawn on the charts.
  - **Telegram channels** (beta) — add a *public* channel; the bot reads recent posts
    via the t.me web preview (no bot token needed). Use “Preview” to verify it loads.
- **Trade Journal** — broker-style page. Log a trade (direction, entry, size/margin,
  leverage, TP/SL), close it with an exit price, and see realised **P&L**, win-rate and
  totals. Every assistant recommendation has a **“Did you take this trade?”** button that
  pre-fills the log. The bot reads your recent trades to match your style.
- **Login** — token auth; the token **expires after 1 day**.
- **PostgreSQL-ready** — set `POSTGRES_DB` (+ creds) to use Postgres; otherwise SQLite.
  All data is scoped per user.

## Quick start

### Backend (Django)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py makemigrations accounts market sources strategy trades ai chat
python manage.py migrate
python manage.py seed        # demo data, indicators, demo user
python manage.py runserver
```
Runs at http://localhost:8000 — **demo login:** `demo` / `demo12345`

#### Using PostgreSQL
Create a database, then set these (e.g. in `backend/.env`) before migrating:
```
POSTGRES_DB=smartpips
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```
(`psycopg2-binary` is already in requirements.)

### Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:5173 (proxies `/api` to the backend).

## Tests
```bash
cd backend
python manage.py test      # auth/token expiry, chat history, trades P&L, strategy
```

## How the assistant reasons (per message)
1. Reads recent **news** (RSS) + **Telegram** signals; mentions relevant ones first.
2. Analyses using your active **indicators**.
3. Looks at your **trade history** to match your style.
4. Proposes ideas anchored to the **live price** (it won't invent prices).

## Notes & limits
- Telegram: only **public** channels work via web preview; treat it as a beta feature.
- Prices come from a public exchange API with a deterministic fallback when offline —
  in that case the assistant says it can't confirm a live price.



## AI model (default + local options)
The app ships with **Groq** pre-configured and active (free tier, fast). You can
change or add models on the **AI Models** page. To keep your key out of the repo,
set `GROQ_API_KEY` in `backend/.env` instead of using the bundled default.

### Run a model locally (no API key) with Ollama
1. Install Ollama (https://ollama.com), then pull a model, e.g. `ollama pull llama3.1`.
2. On the **AI Models** page choose **Ollama (local, no key)** — base URL
   `http://localhost:11434`, model `llama3.1` — and set it active.

Good local models for this kind of analysis (OpenAI-compatible via Ollama/LM Studio):
- **Llama 3.1 8B / 3.3 70B** — strong general reasoning (8B runs on ~8GB VRAM; 70B needs a lot).
- **Qwen2.5 14B / 32B Instruct** — excellent at structured output & numbers.
- **DeepSeek-R1 distill (Qwen 14B/32B)** — step-by-step reasoning, good for analysis.
- **Mistral Small / Mixtral** — fast, decent quality on modest hardware.

Rule of thumb: 7–8B needs ~8GB RAM/VRAM, 14B ~12–16GB, 32B ~24GB+, 70B a high-end GPU.


## Deploying to a server
See **deploy/DEPLOY.md** for a full step-by-step guide (Ubuntu 24.04 + Nginx +
Gunicorn + PostgreSQL + Cloudflare for smartpips.ir).

## Tech
React 18 · Vite · Tailwind · React Router · Django 5 · DRF · SQLite/PostgreSQL · TradingView
