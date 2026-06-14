import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useI18n } from "../i18n/index.jsx";
import { useAuth } from "../auth/AuthContext.jsx";
import { Button, Field, Input } from "../components/ui.jsx";

export default function Login() {
  const { t, lang, toggle, isRTL } = useI18n();
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from?.pathname || "/";

  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") await login(username, password);
      else await register(username, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen grid place-items-center bg-ink-900 px-4" dir={isRTL ? "rtl" : "ltr"}>
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2.5">
            <span className="h-9 w-9 rounded-lg bg-gold grid place-items-center text-ink-900 font-bold text-lg">S</span>
            <span className="text-mist-100 font-semibold text-lg">{t("appName")}</span>
          </div>
          <button onClick={toggle} className="text-gold-soft text-sm font-medium">
            {lang === "fa" ? "EN" : "فا"}
          </button>
        </div>

        <div className="bg-ink-700 border border-ink-500 rounded-2xl shadow-panel p-6">
          <h1 className="text-lg font-semibold text-mist-100 mb-1">
            {mode === "login" ? t("login_title") : t("register_title")}
          </h1>
          <p className="text-xs text-mist-500 mb-5">{t("session_note")}</p>

          <form onSubmit={submit} className="space-y-4">
            <Field label={t("username")}>
              <Input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
            </Field>
            <Field label={t("password")}>
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
            </Field>

            {error && (
              <p className="text-down text-sm bg-down/10 border border-down/30 rounded-lg px-3 py-2">{error}</p>
            )}

            <Button type="submit" disabled={busy} className="w-full">
              {busy ? "…" : mode === "login" ? t("sign_in") : t("sign_up")}
            </Button>
          </form>

          <div className="mt-4 text-center text-sm text-mist-500">
            {mode === "login" ? (
              <>
                {t("no_account")}{" "}
                <button onClick={() => { setMode("register"); setError(null); }} className="text-gold-soft hover:underline">
                  {t("sign_up")}
                </button>
              </>
            ) : (
              <>
                {t("have_account")}{" "}
                <button onClick={() => { setMode("login"); setError(null); }} className="text-gold-soft hover:underline">
                  {t("sign_in")}
                </button>
              </>
            )}
          </div>
        </div>

        <p className="text-center text-xs text-mist-500 mt-4">{t("demo_hint")}</p>
      </div>
    </div>
  );
}
