// Tiny fetch wrapper. In dev, Vite proxies /api -> http://localhost:8000
const BASE = "/api";
const TOKEN_KEY = "smartpips_token";

let onUnauthorized = null;
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

let refreshPromise = null;
export async function refreshSession(expiredToken = null) {
  if (!refreshPromise) {
    const renew = async () => {
      // Web Locks serializes rotation across tabs sharing the same cookie.
      const current = localStorage.getItem(TOKEN_KEY);
      if (expiredToken && current && current !== expiredToken) return current;
      const bootstrap = await fetch(`${BASE}/auth/refresh/`, {
        credentials: "same-origin", cache: "no-store",
      });
      if (!bootstrap.ok) {
        const err = new Error("Session bootstrap failed.");
        err.status = bootstrap.status; throw err;
      }
      const boot = await bootstrap.json();
      const csrf = boot.csrf_token || document.cookie.split("; ").find((s) => s.startsWith("csrftoken="))?.split("=")[1];
      const res = await fetch(`${BASE}/auth/refresh/`, {
        method: "POST", credentials: "same-origin",
        headers: { "X-CSRFToken": decodeURIComponent(csrf || "") },
      });
      if (!res.ok) {
        const err = new Error("Session refresh failed."); err.status = res.status; throw err;
      }
      const data = await res.json();
      // A late refresh must not overwrite a newer explicit login or logout.
      const latest = localStorage.getItem(TOKEN_KEY);
      if (expiredToken && latest !== expiredToken) {
        if (latest) return latest;
        const err = new Error("Session changed."); err.status = 409; throw err;
      }
      localStorage.setItem(TOKEN_KEY, data.token);
      window.dispatchEvent(new CustomEvent("smartpips-token", { detail: data.token }));
      return data.token;
    };
    refreshPromise = (navigator.locks
      ? navigator.locks.request("smartpips-refresh", renew) : renew())
      .finally(() => { refreshPromise = null; });
  }
  return refreshPromise;
}

async function request(path, options = {}, retried = false) {
  const token = localStorage.getItem(TOKEN_KEY);
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token && !["/auth/login/", "/auth/register/"].includes(path)) headers["Authorization"] = `Token ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  if (res.status === 401 && !["/auth/login/", "/auth/register/"].includes(path)) {
    const latest = localStorage.getItem(TOKEN_KEY);
    // Requests started before a successful login must not log that login out.
    if (!retried && latest && latest !== token) return request(path, options, true);
    if (!retried) {
      try { await refreshSession(token); }
      catch (err) {
        const current = localStorage.getItem(TOKEN_KEY);
        if (current && current !== token) return request(path, options, true);
        // Network/5xx/CSRF failures must not erase an otherwise valid session.
        if (err.status === 401 && current === token && onUnauthorized) onUnauthorized();
        throw err;
      }
      return request(path, options, true);
    }
    if (onUnauthorized) onUnauthorized();
    const err = new Error("Session expired. Please sign in again.");
    err.status = 401; throw err;
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.error || data.detail || JSON.stringify(data);
      // surface the margin numbers inline so the user sees WHY, not just "error"
      if (data.needMargin != null && data.available != null) {
        detail += ` (need ${data.needMargin} / have ${data.available} USDT)`;
      }
    } catch { /* ignore */ }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  get: (p) => request(p),
  post: (p, body) => request(p, { method: "POST", body: JSON.stringify(body || {}) }),
  patch: (p, body) => request(p, { method: "PATCH", body: JSON.stringify(body) }),
  put: (p, body) => request(p, { method: "PUT", body: JSON.stringify(body) }),
  del: (p) => request(p, { method: "DELETE" }),
};

export const authApi = {
  login: (username, password) => api.post("/auth/login/", { username, password }),
  register: (username, password) => api.post("/auth/register/", { username, password }),
  logout: () => api.post("/auth/logout/", {}),
  me: () => api.get("/auth/me/"),
  // Anonymous read: tells /register whether sign-ups are currently open.
  // The backend enforces the same flag, so this is only for the UI.
  publicConfig: () => api.get("/auth/config/"),
};

export const marketApi = {
  calendar: (symbol) => api.get(`/market/calendar/?symbol=${encodeURIComponent(symbol)}`),
  candles: (symbol, timeframe) => api.get(`/market/candles/?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`),
  quotes: () => api.get("/market/assets/quotes/"),
  assets: () => api.get("/market/assets/"),
  createAsset: (data) => api.post("/market/assets/", data),
  updateAsset: (id, data) => api.patch(`/market/assets/${id}/`, data),
  deleteAsset: (id) => api.del(`/market/assets/${id}/`),
  metal: (symbol) => api.get(`/market/metal/?symbol=${encodeURIComponent(symbol)}`),
};

export const alertsApi = {
  vapid: () => api.get("/alerts/vapid/"),
  subscribe: (sub) => api.post("/alerts/subscribe/", sub),
  unsubscribe: (data) => api.post("/alerts/unsubscribe/", data),
  status: () => api.get("/alerts/status/"),
  test: () => api.post("/alerts/test/", {}),
  watchlist: () => api.get("/alerts/watchlist/"),
  watchAdd: (symbol, minScore) => api.post("/alerts/watchlist/", { symbol, min_score: minScore }),
  watchRemove: (symbol) => api.del(`/alerts/watchlist/${encodeURIComponent(symbol)}/`),

  // ---- notification centre (internal rows, independent of browser push) ----
  notifications: (params = {}) => {
    const q = new URLSearchParams();
    if (params.category) q.set("category", params.category);
    if (params.unread) q.set("unread", "1");
    if (params.limit) q.set("limit", params.limit);
    const qs = q.toString();
    return api.get(`/alerts/notifications/${qs ? `?${qs}` : ""}`);
  },
  unreadCount: () => api.get("/alerts/notifications/unread-count/"),
  markRead: (id, read = true) => api.post(`/alerts/notifications/${id}/read/`, { read }),
  markAllRead: () => api.post("/alerts/notifications/read-all/", {}),
  removeNotification: (id) => api.del(`/alerts/notifications/${id}/`),
  clearNotifications: (scope = "read") => api.post("/alerts/notifications/clear/", { scope }),

  // ---- user-defined position alert rules ----
  rules: () => api.get("/alerts/rules/"),
  ruleOptions: () => api.get("/alerts/rules/options/"),
  createRule: (data) => api.post("/alerts/rules/", data),
  updateRule: (id, data) => api.patch(`/alerts/rules/${id}/`, data),
  removeRule: (id) => api.del(`/alerts/rules/${id}/`),
  toggleRule: (id) => api.post(`/alerts/rules/${id}/toggle/`, {}),
  // auto:true marks a background poll, which the server throttles so the panel
  // can keep alerts alive without hammering the market feed.
  evaluateNow: ({ auto = false } = {}) => api.post("/alerts/evaluate/", { auto }),
};

export const prefsApi = {
  myAccess: () => api.get("/prefs/market_access/"),
  allAccess: () => api.get("/prefs/market_access/all/"),
  setUserAccess: (id, data) => api.patch(`/prefs/market_access/${id}/`, data),
  myLimits: () => api.get("/prefs/risk_limits/"),
  allLimits: () => api.get("/prefs/risk_limits/all/"),
  setUserLimits: (id, data) => api.patch(`/prefs/risk_limits/${id}/`, data),
};

export const adminApi = {
  users: () => api.get("/auth/users/"),
  createUser: (data) => api.post("/auth/users/", data),
  updateUser: (id, data) => api.patch(`/auth/users/${id}/`, data),
  deleteUser: (id) => api.del(`/auth/users/${id}/`),
  // System switches. Reading needs staff; writing needs a super admin.
  settings: () => api.get("/auth/settings/"),
  updateSettings: (data) => api.patch("/auth/settings/", data),
  // Super-admin only. Sends ONLY the fields provided, so saving a new
  // username can never blank the password (and vice versa).
  changeCredentials: (id, { username, password } = {}) => {
    const body = {};
    if (username) body.username = username;
    if (password) body.password = password;
    return api.patch(`/auth/users/${id}/`, body);
  },
  // Super-admin only. Wipes trades/alerts/watchlist/limits for one user so
  // they start over. Irreversible — Admin.jsx makes you type the username.
  resetUser: (id) => api.post(`/auth/users/${id}/reset/`, {}),
};

export const ctraderApi = {
  selectAccount: (account_id) => api.post("/ctrader/use_manual/", { account_id }),
  status: () => api.get("/ctrader/status/"),
  connect: () => api.get("/ctrader/connect/"),
};

export const mt5Api = {
  account: () => api.get("/mt5/account/"),
  placeOrder: (data) => api.post("/mt5/order/", data),
  myOrders: () => api.get("/mt5/orders/"),
};

export const lbankApi = {
  status: () => api.get("/lbank/status/"),
  balance: () => api.get("/lbank/balance/"),
  orders: (symbol) => api.get(`/lbank/orders/?symbol=${encodeURIComponent(symbol)}`),
  openOrders: (symbol) => api.get(`/lbank/open_orders/?symbol=${encodeURIComponent(symbol)}`),
  trades: (symbol) => api.get(`/lbank/trades/?symbol=${encodeURIComponent(symbol)}`),
  placeOrder: (data) => api.post("/lbank/order/", data),
  cancelOrder: (data) => api.post("/lbank/cancel/", data),
  debugSignatures: () => api.get("/lbank/debug_signatures/"),
  futuresMarket: () => api.get("/lbank/futures/market/"),
  futuresAccount: () => api.get("/lbank/futures/account/"),
  futuresOrderbook: (symbol, depth = 16) =>
    api.get(`/lbank/futures/orderbook/?symbol=${encodeURIComponent(symbol)}&depth=${depth}`),
};

// Health + log reading (super-admin). Backed by config/health.py.
export const systemApi = {
  health: () => api.get("/health/"),
  healthDeep: () => api.get("/health/deep/"),
  logs: ({ lines = 200, level = "", q = "" } = {}) => {
    const p = new URLSearchParams({ lines: String(lines) });
    if (level) p.set("level", level);
    if (q) p.set("q", q);
    return api.get(`/logs/?${p.toString()}`);
  },
  logsTest: () => api.post("/logs/test/", {}),
};

export const bitunixApi = {
  status: () => api.get("/bitunix/status/"),
  selfTest: () => api.get("/bitunix/self_test/"),
  account: () => api.get("/bitunix/account/"),
  positions: (mode = "real") => api.get(`/bitunix/positions/?mode=${mode}`),
  orders: (symbol) => api.get(`/bitunix/orders/${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ""}`),
  placeOrder: (data) => api.post("/bitunix/order/", data),
  closePosition: (data) => api.post("/bitunix/close/", data),
  cancelOrders: (data) => api.post("/bitunix/cancel/", data),
  setLeverage: (data) => api.post("/bitunix/leverage/", data),
  setMarginMode: (data) => api.post("/bitunix/margin_mode/", data),
  depth: (symbol, depth = 16) =>
    api.get(`/bitunix/depth/?symbol=${encodeURIComponent(symbol)}&depth=${depth}`),
  ticker: (symbol) => api.get(`/bitunix/ticker/?symbol=${encodeURIComponent(symbol)}`),
  klines: (symbol, interval = "15m", limit = 300) =>
    api.get(`/bitunix/klines/?symbol=${encodeURIComponent(symbol)}`
      + `&interval=${encodeURIComponent(interval)}&limit=${limit}`),
};

export const scalpApi = {
  signal: (symbol, price, timeframe, tickSeries, balance, riskPct, mode, explain = true, prepareExplanation = false) =>
    api.post("/chat/scalp/", { symbol, price, timeframe, tick_series: tickSeries,
      balance, risk_pct: riskPct, mode, explain, prepare_explanation: prepareExplanation }),
  explain: (token) => api.post("/chat/scalp/explain/", { explanation_token: token }),
};

export const sourcesApi = {
  list: () => api.get("/sources/"),
  create: (data) => api.post("/sources/", data),
  update: (id, data) => api.patch(`/sources/${id}/`, data),
  remove: (id) => api.del(`/sources/${id}/`),
};

export const aiApi = {
  list: () => api.get("/ai/providers/"),
  create: (data) => api.post("/ai/providers/", data),
  update: (id, data) => api.patch(`/ai/providers/${id}/`, data),
  remove: (id) => api.del(`/ai/providers/${id}/`),
  activate: (id) => api.post(`/ai/providers/${id}/activate/`, {}),
  test: (id) => api.post(`/ai/providers/${id}/test/`, {}),
};

export const chatApi = {
  conversations: () => api.get("/chat/conversations/"),
  conversation: (id) => api.get(`/chat/conversations/${id}/`),
  remove: (id) => api.del(`/chat/conversations/${id}/`),
  send: (message, conversationId, livePrices) =>
    api.post("/chat/send/", {
      message,
      conversation_id: conversationId,
      live_prices: livePrices || {},
    }),
};

function strategyChanged(data) {
  localStorage.setItem("smartpips-strategy-changed", String(Date.now()));
  window.dispatchEvent(new Event("smartpips-strategy-changed"));
  return data;
}
export const strategyApi = {
  indicators: () => api.get("/strategy/indicators/"),
  createIndicator: (data) => api.post("/strategy/indicators/", data),
  updateIndicator: (id, data) => api.patch(`/strategy/indicators/${id}/`, data),
  removeIndicator: (id) => api.del(`/strategy/indicators/${id}/`),
  channels: () => api.get("/strategy/telegram/"),
  createChannel: (data) => api.post("/strategy/telegram/", data),
  updateChannel: (id, data) => api.patch(`/strategy/telegram/${id}/`, data),
  removeChannel: (id) => api.del(`/strategy/telegram/${id}/`),
  previewChannel: (id) => api.post(`/strategy/telegram/${id}/preview/`, {}),
  backtest: (symbol, timeframe, tickSeries, opts = {}) =>
    api.post(`/strategy/backtest/`, { symbol, timeframe, tick_series: tickSeries || [],
      ...(opts.mode ? { mode: opts.mode } : {}), ...(opts.bars ? { bars: opts.bars } : {}) }),

  // ---- configurable strategies (presets + user-built) ----
  // These sit on top of the existing engine; the engine endpoints above are
  // untouched.
  vocabulary: () => api.get("/strategy/vocabulary/"),
  strategies: (includeArchived) =>
    api.get(`/strategy/strategies/${includeArchived ? "?include_archived=1" : ""}`),
  strategy: (id) => api.get(`/strategy/strategies/${id}/`),
  createStrategy: (data) => api.post("/strategy/strategies/", data),
  updateStrategy: (id, data) => api.patch(`/strategy/strategies/${id}/`, data).then(strategyChanged),
  removeStrategy: (id) => api.del(`/strategy/strategies/${id}/`),
  strategyVersions: (id) => api.get(`/strategy/strategies/${id}/versions/`),
  cloneStrategy: (id) => api.post(`/strategy/strategies/${id}/clone/`, {}),
  activateStrategy: (id) => api.post(`/strategy/strategies/${id}/activate/`, {}).then(strategyChanged),
  deactivateStrategy: (id) => api.post(`/strategy/strategies/${id}/deactivate/`, {}).then(strategyChanged),
  strategyRisk: (id) => api.get(`/strategy/strategies/${id}/risk/`),
  runStrategyBacktest: (id, body) =>
    api.post(`/strategy/strategies/${id}/backtest/`, body || {}),
  strategyAnalytics: (params = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v) q.set(k, v);
    });
    const qs = q.toString();
    return api.get(`/strategy/strategies/analytics/${qs ? `?${qs}` : ""}`);
  },
};

export const tradesApi = {
  analytics: (query = "") => api.get(`/trades/analytics/${query ? `?${query}` : ""}`),
  auditTimeline: (id) => api.get(`/trades/${id}/audit_timeline/`),
  list: () => api.get("/trades/"),
  create: (data) => api.post("/trades/", data),
  update: (id, data) => api.patch(`/trades/${id}/`, data),
  remove: (id) => api.del(`/trades/${id}/`),
  close: (id, exitPrice) => api.post(`/trades/${id}/close/`, { exit_price: exitPrice }),
  stats: () => api.get("/trades/stats/"),
  profile: () => api.get("/trades/profile/"),
  journal: () => api.get("/trades/journal/"),
  autoClose: () => api.post("/trades/auto_close/", {}),
  exitAdvice: () => api.get("/trades/exit_advice/"),
  marginStatus: (balance) => api.get(`/trades/margin_status/?balance=${encodeURIComponent(balance || 0)}`),
};
