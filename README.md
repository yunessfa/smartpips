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


### Use GitHub Models (free, with your token)
GitHub Models exposes an OpenAI-compatible API, so it plugs straight in:
1. On the **AI Models** page choose **GitHub Models (free, token)**
   (base URL `https://models.github.ai/inference`).
2. Set the model, e.g. `openai/gpt-4o-mini`, `openai/gpt-4o`,
   `meta/Llama-3.3-70B-Instruct`, `mistral-ai/Mistral-Large-2411`.
3. Paste your **GitHub Personal Access Token** as the API key. The token needs the
   `models` permission. Then "Set active" and "Test".
Keep the token private (put it in your `.env`, never commit it).

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



## Live prices (WebSocket)
Crypto prices stream live in the browser from Binance (WebSocket, with a REST
fallback) — independent of the backend. They drive the watchlist, the chat
recommendation cards, and the unrealised P&L on open trades, and are also sent with
each chat message so the AI anchors its analysis to the real-time price.


### Metal prices (gold / silver)
Metals aren't on Binance, so their live price comes from the backend:
`gold-api.com` (free, no key) by default, or **iTick** if you set `ITICK_TOKEN`
in `.env`. These feed the watchlist, the chat recommendation cards, and — crucially
— the price the AI is allowed to use, so it never invents a gold price.
The browser also polls our own `/api/market/quotes/` every 12s, which doubles as a
crypto price fallback when Binance can't be reached directly (e.g. restricted regions).

> If Binance is unreachable in your region, edit `frontend/src/live/LivePrices.jsx`
> (`WS_BASE` / `REST_BASE`) to point at a reachable stream. Metals/forex use the
> live TradingView chart for visuals.


## Scalp mode (gold & silver)
A dedicated **Scalp** page for fast, ultra-short-term trading on metals only:
- A live price tick (~2s) for XAUUSD / XAGUSD via the backend (gold-api / iTick).
- A numeric panel computed from the tick stream: EMA 9, EMA 20, RSI, momentum,
  ATR proxy, and a composite BUY/SELL/WAIT score (with an ATR gate so flat markets
  say "wait").
- An **AI scalp signal** button → a tight prompt returns a decisive call with
  scalp-sized entry / TP / SL, which you can log to the journal in one tap.

> Metals have no free public WebSocket, so the tick uses fast same-origin polling
> (works in restricted regions). `frontend/src/live/useMetalTick.js` is structured
> so a real metal WS can be dropped in if you have one (e.g. an iTick token).


## Personalised AI (per-user)
The assistant adapts to each user instead of giving generic advice:
- **Trader profile** — computed from your trade journal (win rate, profit factor,
  leverage habits, direction bias, best/worst symbols, average R:R) plus behavioural
  **tendencies** it flags (e.g. trading without a stop, over-leveraging on losers).
  Shown on the Trades page and fed into every AI suggestion, which then caps leverage
  to your norm, prefers setups you do well, and steers you off your recurring mistakes.
- **News sentiment** — headlines are scored bullish/bearish with a finance lexicon and
  summarised for the AI to tilt (not override) its bias.
- **Market regime** — the scalp page classifies the tape (trending / ranging / volatile)
  as a lightweight stand-in for a GMM regime detector, and passes it to the scalp signal.

> These are pragmatic, dependency-free approximations of heavier research methods
> (RL/FLAG-Trader, GNNs, fine-tuned FinLLMs). They run instantly with no GPU/training,
> while capturing the same effects: personalisation, regime-aware sizing, sentiment and
> multi-signal confidence gating.


## How signals are made (engine-first, AI explains)
SmartPips does NOT ask the model to invent trades. A Python **strategy engine**
(`apps/strategy/engine.py`) decides buy/sell/wait from real indicators on real
candles, then the AI only writes the explanation:
```
candles -> Strategy Engine (EMA stack, VWAP, RSI, MACD, Stochastic, SMC) -> score+risk -> decision -> AI explanation
```
- **Multi-timeframe**: the trading TF must agree with higher TFs or it's "no trade".
- **VWAP + EMA9/50/200 + RSI + MACD + Stochastic** with transparent weighted scoring;
  confidence (high/medium/low) is computed in the backend, not guessed by the model.
- **Smart-Money / liquidity**: BOS, CHOCH, FVG and equal highs/lows from candles.
- **Risk manager**: structure-based stop, only emits a trade at Risk:Reward >= 2.
- **Economic-calendar guard**: blocks trades near high-impact USD events (set
  `ECONOMIC_CALENDAR_URL` to a JSON feed; inert until configured).
- **Backtest** (`/api/strategy/backtest/`): replays the rules over recent candles and
  reports win rate, profit factor, expectancy and max drawdown — shown on the Scalp page.
- **Candles**: set `TWELVEDATA_KEY` for real gold/silver OHLC; without it the engine
  falls back to tick-built candles (lower quality, flagged in the UI).
- **Sentiment**: news lexicon + crypto Fear & Greed index.

> Order-flow (bid/ask, volume delta) and a fine-tuned sentiment model need paid L2 /
> training data and aren't included; everything above runs on free sources.


## Users, multi-device login & scalp alerts
- **Multi-device login**: each login gets its own token, so signing in on your phone
  no longer kicks out your desktop session. Logout only ends the current device.
- **Admin panel** (`/admin`, visible to super-admins like `demo`): create users with
  email + password, grant/revoke admin, enable/disable or delete accounts. Each user
  has their own journal, conversations and trader profile.
- **Scalp push alerts (PWA, works on iPhone)**: a background `monitor_scalp` command
  watches gold/silver across timeframes and sends a Web-Push when a NEW engine setup
  appears (no spamming the same idea). Users enable it from the Scalp page.
  - iPhone: open the site, Share -> **Add to Home Screen**, open SmartPips from that
    icon, then tap *Enable scalp alerts* (iOS 16.4+ only allows push from installed PWAs).
  - Setup: `pip install pywebpush`, `python manage.py gen_vapid` -> put the keys in
    `.env`, restart, then run the monitor every minute via cron:
    `* * * * * cd /var/www/smartpips/backend && .venv/bin/python manage.py monitor_scalp`

## Deploying to a server
See **deploy/DEPLOY.md** for a full step-by-step guide (Ubuntu 24.04 + Nginx +
Gunicorn + PostgreSQL + Cloudflare for smartpips.ir).

## Tech
React 18 · Vite · Tailwind · React Router · Django 5 · DRF · SQLite/PostgreSQL · TradingView
