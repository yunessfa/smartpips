import { useCallback, useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { useI18n } from "../i18n/index.jsx";
import { useAuth } from "../auth/AuthContext.jsx";
import { alertsApi } from "../api/client.js";

// Strategy library / builder. Kept in the "More" sheet on phones rather than
// the bottom bar: it is a configuration surface, not something you reach for
// mid-trade.
function TargetIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px] shrink-0" fill="none"
      stroke="currentColor" strokeWidth="1.7">
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
}

export default function Layout({ children }) {
  const { t, lang, toggle, isRTL } = useI18n();
  const { username, isAdmin, logout } = useAuth();
  const [open, setOpen] = useState(false); // mobile drawer
  const [moreOpen, setMoreOpen] = useState(false); // mobile "More" sheet
  const [unread, setUnread] = useState(0);

  // Unread badge. Polled slowly rather than pushed: the count is cheap and a
  // socket for one integer is not worth the moving parts. The custom event
  // lets the notifications page refresh it instantly after an action.
  const refreshUnread = useCallback(async () => {
    try {
      const res = await alertsApi.unreadCount();
      setUnread(res?.unread || 0);
    } catch {
      /* never let a badge break the shell */
    }
  }, []);

  useEffect(() => {
    refreshUnread();
    const id = setInterval(refreshUnread, 60000);
    window.addEventListener("sp-notifications-changed", refreshUnread);
    return () => {
      clearInterval(id);
      window.removeEventListener("sp-notifications-changed", refreshUnread);
    };
  }, [refreshUnread]);

  // Drive the alert engine from the open panel.
  //
  // Position/PnL rules were only ever evaluated by the `check_alerts` cron job,
  // so on an install where that cron is not set up no trading alert could ever
  // appear and the feature looked dead. While the panel is open we ask the
  // server to run this user's rules every 45s (auto=1, server-throttled to one
  // real pass per 20s) and refresh the badge when something fires. The cron job
  // is still the driver for users who are not looking at the panel.
  useEffect(() => {
    let stopped = false;

    async function tick() {
      if (document.hidden) return; // don't poll a background tab
      try {
        const res = await alertsApi.evaluateNow({ auto: true });
        if (!stopped && res?.fired) {
          refreshUnread();
          window.dispatchEvent(new Event("sp-notifications-changed"));
        }
      } catch {
        /* the badge and the panel must survive a failed evaluation pass */
      }
    }

    tick();
    const id = setInterval(tick, 45000);
    return () => {
      stopped = true;
      clearInterval(id);
    };
  }, [refreshUnread]);

  const NAV = [
    // The panel moved under /app; the public marketing site now owns the root.
    { to: "/app", label: t("nav_dashboard"), end: true, icon: GridIcon },
    { to: "/app/chat", label: t("nav_chat"), icon: ChatIcon },
    { to: "/app/scalp", label: t("nav_scalp"), icon: BoltIcon },
    { to: "/app/bitunix", label: t("nav_bitunix"), icon: CandleIcon },
    { to: "/app/trades", label: t("nav_trades"), icon: JournalIcon },
    { to: "/app/strategies", label: t("nav_strategies"), icon: TargetIcon },
    { to: "/app/notifications", label: t("nav_notifications"), icon: BellIcon, badge: unread },
    { to: "/app/sources", label: t("nav_sources"), icon: GlobeIcon },
    { to: "/app/ai", label: t("nav_ai"), icon: ChipIcon },
    ...(isAdmin ? [{ to: "/app/admin", label: t("nav_admin"), icon: UsersIcon },
                   { to: "/app/logs", label: t("nav_logs"), icon: LogIcon }] : []),
  ];

  // Mobile bottom bar shows four trading-critical destinations plus a "More"
  // sheet. Slicing the nav to five buttons used to hide whatever came after
  // it, so any page added later became unreachable on a phone.
  const PRIMARY = [NAV[0], NAV[2], NAV[3], NAV[4]];
  const REST = NAV.filter((item) => !PRIMARY.includes(item));

  const Sidebar = (
    <div className="h-full flex flex-col bg-ink-800 border-ink-500">
      <div className="px-5 py-5 border-b border-ink-500">
        <div className="flex items-center gap-2.5">
          <img src="/logo-icon.png" alt="SmartPips" className="h-9 w-9 rounded-lg object-cover shadow-lg shadow-gold/20" />
          <div>
            <p className="text-mist-100 font-semibold leading-tight">{t("appName")}</p>
            <p className="text-mist-500 text-xs">{t("tagline")}</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            onClick={() => setOpen(false)}
            className={({ isActive }) =>
              `relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition ${
                isActive
                  ? "bg-gold/10 text-gold-soft"
                  : "text-mist-300 hover:text-mist-100 hover:bg-ink-700"
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span className={`absolute ${isRTL ? "right-0" : "left-0"} top-1/2 -translate-y-1/2 h-5 w-1 rounded-full bg-gold transition-opacity ${isActive ? "opacity-100" : "opacity-0"}`} />
                <item.icon />
                <span className="min-w-0 flex-1 truncate">{item.label}</span>
                {item.badge > 0 && (
                  <span className="shrink-0 rounded-full bg-gold px-1.5 py-0.5 text-[10px] font-semibold leading-none text-ink-900 tnum">
                    {item.badge > 99 ? "99+" : item.badge}
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="px-3 py-3 border-t border-ink-500 space-y-2">
        <button
          onClick={toggle}
          className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm text-mist-300 hover:bg-ink-700"
        >
          <span>{t("language")}</span>
          <span className="font-medium text-gold-soft">{lang === "fa" ? "EN" : "فا"}</span>
        </button>
        {username && (
          <button
            onClick={logout}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-mist-300 hover:bg-ink-700"
          >
            <LogoutIcon /> {t("logout")} <span className="text-mist-500">· {username}</span>
          </button>
        )}
      </div>
    </div>
  );

  return (
    <div className="h-screen overflow-hidden flex bg-ink-900" dir={isRTL ? "rtl" : "ltr"}>
      {/* desktop sidebar */}
      <aside className={`hidden md:flex flex-col h-screen w-60 shrink-0 ${isRTL ? "border-l" : "border-r"} border-ink-500`}>
        {Sidebar}
      </aside>

      {/* mobile drawer */}
      {open && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setOpen(false)} />
          <aside className={`absolute top-0 ${isRTL ? "right-0" : "left-0"} h-full w-64 shadow-2xl`}>
            {Sidebar}
          </aside>
        </div>
      )}

      <main className="flex-1 min-w-0 min-h-0 flex flex-col">
        {/* mobile top bar */}
        <div className="md:hidden flex items-center justify-between px-4 py-2.5 border-b border-ink-500 bg-ink-800 shrink-0">
          <button onClick={() => setOpen(true)} className="text-mist-100 p-1" aria-label="Menu">
            <MenuIcon />
          </button>
          <span className="font-semibold text-mist-100">{t("appName")}</span>
          <button onClick={toggle} className="text-gold-soft text-sm font-medium">
            {lang === "fa" ? "EN" : "فا"}
          </button>
        </div>
        <div className="flex-1 min-h-0 flex flex-col pb-tabbar md:pb-0">{children}</div>

        {/* mobile bottom tab bar — exchange-app style */}
        {moreOpen && (
          <div className="md:hidden fixed inset-0 z-40" role="dialog" aria-modal="true">
            <div className="absolute inset-0 bg-black/60" onClick={() => setMoreOpen(false)} />
            <div className="absolute inset-x-0 bottom-0 pb-tabbar bg-ink-800 border-t border-ink-500 rounded-t-2xl shadow-2xl">
              <div className="flex items-center justify-between px-4 pt-3 pb-2">
                <span className="text-sm font-semibold text-mist-100">{t("nav_more")}</span>
                <button onClick={() => setMoreOpen(false)} className="text-mist-500 text-sm px-2 py-1">
                  {t("cancel")}
                </button>
              </div>
              <div className="grid grid-cols-3 gap-2 px-3 pb-3">
                {REST.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    onClick={() => setMoreOpen(false)}
                    className={({ isActive }) =>
                      `flex flex-col items-center gap-1.5 rounded-xl px-2 py-3 text-[11px] font-medium transition ${
                        isActive ? "bg-gold/10 text-gold-soft" : "text-mist-300 bg-ink-700/60"
                      }`
                    }
                  >
                    <span className="relative">
                      <item.icon />
                      {item.badge > 0 && (
                        <span className="absolute -end-1.5 -top-1 h-2 w-2 rounded-full bg-gold" />
                      )}
                    </span>
                    <span className="w-full truncate text-center">{item.label}</span>
                  </NavLink>
                ))}
              </div>
              {username && (
                <div className="border-t border-ink-500 px-3 py-2">
                  <button
                    onClick={() => {
                      setMoreOpen(false);
                      logout();
                    }}
                    className="w-full flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm text-mist-300"
                  >
                    <LogoutIcon /> {t("logout")} <span className="text-mist-500 truncate">· {username}</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        <nav className="md:hidden fixed bottom-0 inset-x-0 z-30 bg-ink-800/95 backdrop-blur border-t border-ink-500 tabbar-safe">
          <div className="grid grid-cols-5">
            {PRIMARY.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end}
                onClick={() => setMoreOpen(false)}
                className={({ isActive }) =>
                  `flex min-w-0 flex-col items-center gap-0.5 py-2 text-[10px] font-medium transition ${
                    isActive ? "text-gold-soft" : "text-mist-500"
                  }`
                }>
                <item.icon />
                <span className="w-full truncate px-1 text-center">{item.label}</span>
              </NavLink>
            ))}
            <button
              onClick={() => setMoreOpen((v) => !v)}
              aria-expanded={moreOpen}
              className={`flex min-w-0 flex-col items-center gap-0.5 py-2 text-[10px] font-medium transition ${
                moreOpen ? "text-gold-soft" : "text-mist-500"
              }`}
            >
              <MoreIcon />
              <span className="w-full truncate px-1 text-center">{t("nav_more")}</span>
            </button>
          </div>
        </nav>
      </main>
    </div>
  );
}

export function PageHeader({ title, subtitle, right }) {
  return (
    <header className="flex items-center justify-between gap-3 px-4 md:px-6 py-4 border-b border-ink-500 glass sticky top-0 z-10 shrink-0">
      <div className="min-w-0">
        <h1 className="text-lg font-semibold text-mist-100 truncate">{title}</h1>
        {subtitle && <p className="text-sm text-mist-500 truncate">{subtitle}</p>}
      </div>
      {right}
    </header>
  );
}

function MoreIcon() { return (<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="5" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1.4" fill="currentColor" stroke="none"/></svg>); }
function BellIcon() { return (<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/></svg>); }
function GridIcon() { return (<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>); }
function ChatIcon() { return (<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>); }
function JournalIcon() { return (<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/><path d="M9 7h7M9 11h7"/></svg>); }
function CandleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M8 6v12M8 3v3m0 12v3M16 9v9M16 6v3m0 9v3" strokeLinecap="round" />
      <rect x="6" y="8" width="4" height="7" rx="1" fill="currentColor" stroke="none" opacity="0.85" />
      <rect x="14" y="11" width="4" height="5" rx="1" fill="currentColor" stroke="none" opacity="0.5" />
    </svg>
  );
}

function BoltIcon() { return (<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>); }
function UsersIcon() { return (<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>); }
function GlobeIcon() { return (<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/></svg>); }
function ChipIcon() { return (<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3"/></svg>); }
function LogIcon() { return (<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M4 4h11l5 5v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z"/><path d="M14 4v5h5M8 13h8M8 17h5"/></svg>); }
function MenuIcon() { return (<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 6h18M3 12h18M3 18h18"/></svg>); }
function LogoutIcon() { return (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/></svg>); }
