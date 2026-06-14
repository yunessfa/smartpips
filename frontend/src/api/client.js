// Tiny fetch wrapper. In dev, Vite proxies /api -> http://localhost:8000
const BASE = "/api";
const TOKEN_KEY = "smartpips_token";

let onUnauthorized = null;
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

async function request(path, options = {}) {
  const token = localStorage.getItem(TOKEN_KEY);
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Token ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    if (onUnauthorized) onUnauthorized();
    throw new Error("Session expired. Please sign in again.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.error || data.detail || JSON.stringify(data);
    } catch { /* ignore */ }
    throw new Error(detail);
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
};

export const marketApi = {
  quotes: () => api.get("/market/assets/quotes/"),
  assets: () => api.get("/market/assets/"),
  createAsset: (data) => api.post("/market/assets/", data),
  updateAsset: (id, data) => api.patch(`/market/assets/${id}/`, data),
  deleteAsset: (id) => api.del(`/market/assets/${id}/`),
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
  send: (message, conversationId) =>
    api.post("/chat/send/", { message, conversation_id: conversationId }),
};

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
};

export const tradesApi = {
  list: () => api.get("/trades/"),
  create: (data) => api.post("/trades/", data),
  update: (id, data) => api.patch(`/trades/${id}/`, data),
  remove: (id) => api.del(`/trades/${id}/`),
  close: (id, exitPrice) => api.post(`/trades/${id}/close/`, { exit_price: exitPrice }),
  stats: () => api.get("/trades/stats/"),
};
