import { createContext, useContext, useEffect, useState } from "react";
import { authApi, setUnauthorizedHandler } from "../api/client";

const AuthContext = createContext(null);
const TOKEN_KEY = "smartpips_token";
const USER_KEY = "smartpips_user";

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [username, setUsername] = useState(() => localStorage.getItem(USER_KEY));
  const [ready, setReady] = useState(false);

  function persist(tok, user) {
    if (tok) {
      localStorage.setItem(TOKEN_KEY, tok);
      localStorage.setItem(USER_KEY, user || "");
    } else {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    }
    setToken(tok || null);
    setUsername(user || null);
  }

  // Verify the stored token on load; expired tokens (>24h) are cleared.
  useEffect(() => {
    setUnauthorizedHandler(() => persist(null, null));
    async function verify() {
      if (token) {
        try {
          await authApi.me();
        } catch {
          persist(null, null);
        }
      }
      setReady(true);
    }
    verify();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function login(u, p) {
    const data = await authApi.login(u, p);
    persist(data.token, data.username);
    return data;
  }
  async function register(u, p) {
    const data = await authApi.register(u, p);
    persist(data.token, data.username);
    return data;
  }
  async function logout() {
    try { await authApi.logout(); } catch { /* ignore */ }
    persist(null, null);
  }

  return (
    <AuthContext.Provider
      value={{ token, username, ready, isAuthed: !!token, login, register, logout }}
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
