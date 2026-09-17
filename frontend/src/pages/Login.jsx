import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
import { useI18n } from "../i18n/index.jsx";
import { useAuth } from "../auth/AuthContext.jsx";
import { authApi } from "../api/client.js";
import AuthAside from "../site/visuals/AuthAside.jsx";
import { resolvePostAuthTarget } from "../auth/redirect.js";

/**
 * Login / register.
 *
 * Redesigned to sit in the same visual world as the public site rather than
 * looking like a panel dialog that escaped: a two-column composition with the
 * form on one side and a live product visual on the other.
 *
 * Deliberately kept intact from the old implementation:
 *   • the auth calls and error handling,
 *   • every existing i18n key, so no translation work is stranded,
 *   • the post-login redirect to /app (or back to wherever the user was sent
 *     from by the Protected route).
 *
 * The route itself decides the initial mode, so /register opens on the sign-up
 * form instead of making the user hunt for the toggle.
 */

const EASE = [0.2, 0.7, 0.3, 1];

export default function Login() {
  const { t, lang, toggle, isRTL } = useI18n();
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const reduced = useReducedMotion();

  // After signing in, land in the trading panel. The Protected route may have
  // stashed the page the user was originally after; resolvePostAuthTarget keeps
  // it only when it actually points into /app, so arriving here from the public
  // site (or from /login itself) can never bounce the user back out.
  const from = resolvePostAuthTarget(location.state?.from);
  const wantsRegister = location.pathname === "/register";

  const [mode, setMode] = useState(wantsRegister ? "register" : "login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  // Whether sign-ups are open, as reported by the server. `null` = not asked
  // yet, which is why the register form stays hidden until the answer arrives
  // instead of flashing a form that may be about to be refused.
  const [registrationOpen, setRegistrationOpen] = useState(null);

  useEffect(() => {
    if (!wantsRegister) return;
    let cancelled = false;
    authApi
      .publicConfig()
      .then((cfg) => {
        if (!cancelled) setRegistrationOpen(cfg.registration_enabled !== false);
      })
      // If the check itself fails we let the form render: the backend rejects
      // the POST anyway, so the worst case is a clear error instead of an
      // unusable page caused by an unrelated network blip.
      .catch(() => {
        if (!cancelled) setRegistrationOpen(true);
      });
    return () => {
      cancelled = true;
    };
  }, [wantsRegister]);

  // Keep the form in sync if the user navigates between /login and /register.
  useEffect(() => {
    setMode(wantsRegister ? "register" : "login");
    setError(null);
  }, [wantsRegister]);

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

  const isLogin = mode === "login";
  // Only ever gate the sign-up form. Existing users must keep signing in while
  // registration is closed.
  const registrationBlocked = !isLogin && registrationOpen === false;
  const checkingRegistration = !isLogin && registrationOpen === null;

  return (
    <div
      className="relative min-h-screen bg-sp-void text-sp-t1 antialiased"
      dir={isRTL ? "rtl" : "ltr"}
    >
      {/* Decorative layer.

          This wrapper is the fix for the mobile horizontal-scroll bug: the
          bloom below is a fixed 640px circle offset past the inline-end edge.
          On a 390px viewport that is ~370px of element sticking out of the
          document, which the browser resolves by widening the scrollable area.
          Clipping it at an absolutely-positioned, inset-0 container removes the
          overflow at its source — the page itself keeps its normal overflow
          behaviour, so this is not an `overflow-x-hidden` band-aid on <body>. */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div
          className="absolute -top-32 end-[-15%] h-[420px] w-[420px] rounded-full sm:h-[640px] sm:w-[640px]"
          style={{
            background:
              "radial-gradient(circle, rgba(240,184,11,0.09) 0%, rgba(240,184,11,0.025) 42%, transparent 70%)",
          }}
        />
        <div className="sx-grid sx-grid-mask absolute inset-0 opacity-30" />
      </div>

      {/* Top bar: back to site + language. */}
      <header className="relative z-10 mx-auto flex max-w-site items-center justify-between px-5 py-6 sm:px-8">
        <Link
          to="/"
          className="group flex items-center gap-2.5"
          aria-label="SmartPips"
        >
          <img
            src="/logo-icon.png"
            alt=""
            className="h-9 w-9 rounded-[9px] object-cover ring-1 ring-signal/25 transition-all duration-300 group-hover:ring-signal/50"
          />
          <span className="text-[15px] font-semibold tracking-tight text-sp-t1">
            Smart<span className="text-signal">Pips</span>
          </span>
        </Link>

        <div className="flex items-center gap-2">
          <Link
            to="/"
            className="hidden rounded-full px-3 py-1.5 text-[13px] text-sp-t3 transition-colors hover:text-sp-t1 sm:block"
          >
            {isRTL ? "\u0628\u0627\u0632\u06af\u0634\u062a \u0628\u0647 \u0633\u0627\u06cc\u062a" : "Back to site"}
          </Link>
          <button
            type="button"
            onClick={toggle}
            className="rounded-full border border-white/10 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-sp-t2 transition-colors duration-300 hover:border-signal/40 hover:text-signal"
            aria-label="Switch language"
          >
            {lang === "fa" ? "EN" : "\u0641\u0627"}
          </button>
        </div>
      </header>

      {/* Two columns on desktop; the visual is dropped entirely on mobile
          rather than shrunk into a decorative strip. */}
      <main className="relative z-10 mx-auto grid max-w-site items-center gap-12 px-5 pb-20 pt-6 sm:px-8 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)] lg:gap-20 lg:pt-10">
        {/* ------------------------------------------------------------ form */}
        <motion.div
          initial={reduced ? false : { opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: EASE }}
          className="w-full"
        >
          {/* The full lockup, at a restrained size. The old page showed it at
              176px wide directly above a card containing the same brand again,
              which read as duplicated rather than confident. */}
          <img
            src="/logo-full.png"
            alt="SmartPips — AI Trading Assistant"
            className="mb-9 h-auto w-36 drop-shadow-[0_8px_24px_rgba(0,0,0,0.6)]"
          />

          <h1 className="site-display text-[2rem] leading-[1.1] text-sp-t1 sm:text-[2.4rem]">
            {isLogin ? t("login_title") : t("register_title")}
          </h1>
          <p className="mt-3 text-[14px] leading-relaxed text-sp-t3">{t("session_note")}</p>

          {registrationBlocked ? (
            <div className="mt-8 space-y-5">
              <p
                className="rounded-xl border border-signal/25 bg-signal/[0.06] px-4 py-3.5 text-[13.5px] leading-relaxed text-sp-t2"
                role="status"
              >
                {t("registration_disabled")}
              </p>
              <Link
                to="/login"
                className="block w-full rounded-xl bg-signal px-5 py-3.5 text-center text-[14.5px] font-semibold text-sp-void transition-all duration-300 hover:bg-signal-soft"
              >
                {t("sign_in")}
              </Link>
            </div>
          ) : (
          <form onSubmit={submit} className="mt-8 space-y-5">
            <div>
              <label
                htmlFor="sp-username"
                className="mb-2 block font-mono text-[10px] uppercase tracking-[0.18em] text-sp-t4"
              >
                {t("username")}
              </label>
              <input
                id="sp-username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                dir="ltr"
                className="w-full rounded-xl border border-sp-line bg-sp-s1/70 px-4 py-3 text-[15px] text-sp-t1 outline-none transition-all duration-200 placeholder:text-sp-t4 focus:border-signal/45 focus:bg-sp-s2/70 focus:ring-1 focus:ring-signal/20"
              />
            </div>

            <div>
              <label
                htmlFor="sp-password"
                className="mb-2 block font-mono text-[10px] uppercase tracking-[0.18em] text-sp-t4"
              >
                {t("password")}
              </label>
              <div className="relative">
                <input
                  id="sp-password"
                  type={showPass ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={isLogin ? "current-password" : "new-password"}
                  dir="ltr"
                  className="w-full rounded-xl border border-sp-line bg-sp-s1/70 px-4 py-3 pe-12 text-[15px] text-sp-t1 outline-none transition-all duration-200 focus:border-signal/45 focus:bg-sp-s2/70 focus:ring-1 focus:ring-signal/20"
                />
                {/* A show/pass toggle is a small thing that removes a real
                    source of failed logins on mobile keyboards. */}
                <button
                  type="button"
                  onClick={() => setShowPass((v) => !v)}
                  className="absolute end-3 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-sp-t4 transition-colors hover:text-sp-t2"
                  aria-label={showPass ? "Hide password" : "Show password"}
                >
                  <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7">
                    {showPass ? (
                      <>
                        <path d="M3 3l18 18" strokeLinecap="round" />
                        <path d="M10.6 10.7a2 2 0 002.8 2.8M9.4 5.5A9.6 9.6 0 0112 5.2c4.5 0 8 3.4 9 6.8-.4 1.2-1.2 2.5-2.3 3.6M6.2 7.3C4.4 8.6 3.4 10.4 3 12c1 3.4 4.5 6.8 9 6.8 1 0 1.9-.2 2.8-.5" strokeLinecap="round" />
                      </>
                    ) : (
                      <>
                        <path d="M3 12c1-3.4 4.5-6.8 9-6.8s8 3.4 9 6.8c-1 3.4-4.5 6.8-9 6.8S4 15.4 3 12z" />
                        <circle cx="12" cy="12" r="2.6" />
                      </>
                    )}
                  </svg>
                </button>
              </div>
            </div>

            {error && (
              <motion.p
                initial={reduced ? false : { opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                className="rounded-xl border border-sp-neg/30 bg-sp-neg/[0.08] px-3.5 py-2.5 text-[13px] text-sp-neg"
                role="alert"
              >
                {error}
              </motion.p>
            )}

            <button
              type="submit"
              disabled={busy || checkingRegistration}
              className="group relative w-full overflow-hidden rounded-xl bg-signal px-5 py-3.5 text-[14.5px] font-semibold text-sp-void transition-all duration-300 hover:bg-signal-soft disabled:cursor-not-allowed disabled:opacity-60"
            >
              <span className="relative">
                {busy ? "\u2026" : isLogin ? t("sign_in") : t("sign_up")}
              </span>
            </button>
          </form>
          )}

          {/* Mode switch. Uses Link so the URL matches the form the user is
              looking at — which also makes /register shareable. */}
          <div className="mt-6 text-center text-[13.5px] text-sp-t3">
            {isLogin ? (
              <>
                {t("no_account")}{" "}
                <Link
                  to="/register"
                  className="font-medium text-signal transition-colors hover:text-signal-soft"
                >
                  {t("sign_up")}
                </Link>
              </>
            ) : (
              <>
                {t("have_account")}{" "}
                <Link
                  to="/login"
                  className="font-medium text-signal transition-colors hover:text-signal-soft"
                >
                  {t("sign_in")}
                </Link>
              </>
            )}
          </div>
        </motion.div>

        {/* ---------------------------------------------------------- visual */}
        <motion.div
          className="hidden lg:block"
          initial={reduced ? false : { opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.9, delay: 0.15, ease: EASE }}
        >
          <AuthAside isRTL={isRTL} />
        </motion.div>
      </main>
    </div>
  );
}
