import { createContext, useContext, useEffect, useState } from "react";
import { authApi, refreshSession, setUnauthorizedHandler } from "../api/client";

const AuthContext = createContext(null);
const TOKEN_KEY = "smartpips_token";
const USER_KEY = "smartpips_user";
const ADMIN_KEY = "smartpips_admin";
// Non-secret hint that this browser holds a refresh cookie (the cookie itself
// is HttpOnly and invisible to JS). Lets a visit with no access token in
// storage resume the session silently instead of showing the login form,
// without costing anonymous visitors two extra requests.
const HINT_KEY = "smartpips_has_session";

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [username, setUsername] = useState(() => localStorage.getItem(USER_KEY));
  const [isAdmin, setIsAdmin] = useState(() => localStorage.getItem(ADMIN_KEY) === "1");
  const [ready, setReady] = useState(false);

  function persist(tok, user, admin) {
    if (tok) {
      localStorage.setItem(HINT_KEY, "1");
      localStorage.setItem(TOKEN_KEY, tok);
      localStorage.setItem(USER_KEY, user || "");
      localStorage.setItem(ADMIN_KEY, admin ? "1" : "0");
    } else {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
      localStorage.removeItem(ADMIN_KEY);
    }
    setToken(tok || null);
    setUsername(user || null);
    setIsAdmin(!!admin);
  }

  useEffect(() => {
    setUnauthorizedHandler(() => persist(null, null, false));
    const onToken = (e) => setToken(e.detail);
    const onStorage = (e) => { if (e.key === TOKEN_KEY) setToken(e.newValue); };
    window.addEventListener("smartpips-token", onToken);
    window.addEventListener("storage", onStorage);
    async function verify() {
      if (!token && localStorage.getItem(HINT_KEY) === "1") {
        // Access token gone (expired and cleared, other tab, storage wipe) but
        // the 30-day refresh cookie may still be valid: resume silently.
        try {
          const fresh = await refreshSession();
          const me = await authApi.me();
          persist(fresh, me.username, me.is_admin);
        } catch (err) {
          if (err.status === 401) localStorage.removeItem(HINT_KEY);
        }
        setReady(true);
        return;
      }
      if (token) {
        try {
          const me = await authApi.me();
          setIsAdmin(!!me.is_admin);
          localStorage.setItem(ADMIN_KEY, me.is_admin ? "1" : "0");
        } catch (err) {
          if (err.status === 401 && localStorage.getItem(TOKEN_KEY) === token) persist(null, null, false);
        }
      }
      setReady(true);
    }
    verify();
    return () => {
      setUnauthorizedHandler(null);
      window.removeEventListener("smartpips-token", onToken);
      window.removeEventListener("storage", onStorage);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function login(u, p) {
    const data = await authApi.login(u, p);
    persist(data.token, data.username, data.is_admin);
    return data;
  }
  async function register(u, p) {
    const data = await authApi.register(u, p);
    persist(data.token, data.username, data.is_admin);
    return data;
  }
  async function logout() {
    try { await authApi.logout(); } catch { /* ignore */ }
    localStorage.removeItem(HINT_KEY);
    persist(null, null, false);
  }

  return (
    <AuthContext.Provider
      value={{ token, username, isAdmin, ready, isAuthed: !!token, login, register, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
