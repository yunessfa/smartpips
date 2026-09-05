import { createContext, useContext, useEffect, useState } from "react";
import { authApi, setUnauthorizedHandler } from "../api/client";

const AuthContext = createContext(null);
const TOKEN_KEY = "smartpips_token";
const USER_KEY = "smartpips_user";
const ADMIN_KEY = "smartpips_admin";

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [username, setUsername] = useState(() => localStorage.getItem(USER_KEY));
  const [isAdmin, setIsAdmin] = useState(() => localStorage.getItem(ADMIN_KEY) === "1");
  const [ready, setReady] = useState(false);

  function persist(tok, user, admin) {
    if (tok) {
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
    async function verify() {
      if (token) {
        try {
          const me = await authApi.me();
          setIsAdmin(!!me.is_admin);
          localStorage.setItem(ADMIN_KEY, me.is_admin ? "1" : "0");
        } catch {
          persist(null, null, false);
        }
      }
      setReady(true);
    }
    verify();
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
