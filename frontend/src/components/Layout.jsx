import { useState } from "react";
import { NavLink } from "react-router-dom";
import { useI18n } from "../i18n/index.jsx";
import { useAuth } from "../auth/AuthContext.jsx";

export default function Layout({ children }) {
  const { t, lang, toggle, isRTL } = useI18n();
  const { username, logout } = useAuth();
  const [open, setOpen] = useState(false); // mobile drawer

  const NAV = [
    { to: "/", label: t("nav_dashboard"), end: true, icon: GridIcon },
    { to: "/chat", label: t("nav_chat"), icon: ChatIcon },
    { to: "/trades", label: t("nav_trades"), icon: JournalIcon },
    { to: "/sources", label: t("nav_sources"), icon: GlobeIcon },
    { to: "/ai", label: t("nav_ai"), icon: ChipIcon },
  ];

  const Sidebar = (
    <div className="h-full flex flex-col bg-ink-800 border-ink-500">
      <div className="px-5 py-5 border-b border-ink-500">
        <div className="flex items-center gap-2.5">
          <span className="h-8 w-8 rounded-lg bg-gradient-to-br from-gold to-gold-soft grid place-items-center text-ink-900 font-bold shadow-lg shadow-gold/20">S</span>
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
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition ${
                isActive ? "bg-ink-600 text-gold-soft" : "text-mist-300 hover:text-mist-100 hover:bg-ink-700"
              }`
            }
          >
            <item.icon />
            {item.label}
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
        <p className="text-[11px] leading-relaxed text-mist-500 px-1">{t("disclaimer_short")}</p>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen flex bg-ink-900" dir={isRTL ? "rtl" : "ltr"}>
      {/* desktop sidebar */}
      <aside className={`hidden md:block w-60 shrink-0 ${isRTL ? "border-l" : "border-r"} border-ink-500`}>
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

      <main className="flex-1 min-w-0 flex flex-col">
        {/* mobile top bar */}
        <div className="md:hidden flex items-center justify-between px-4 py-3 border-b border-ink-500 bg-ink-800">
          <button onClick={() => setOpen(true)} className="text-mist-100 p-1" aria-label="Menu">
            <MenuIcon />
          </button>
          <span className="font-semibold text-mist-100">{t("appName")}</span>
          <button onClick={toggle} className="text-gold-soft text-sm font-medium">
            {lang === "fa" ? "EN" : "فا"}
          </button>
        </div>
        {children}
      </main>
    </div>
  );
}

export function PageHeader({ title, subtitle, right }) {
  return (
    <header className="flex items-center justify-between gap-3 px-4 md:px-6 py-4 border-b border-ink-500 bg-ink-800/60 backdrop-blur sticky top-0 z-10">
      <div className="min-w-0">
        <h1 className="text-lg font-semibold text-mist-100 truncate">{title}</h1>
        {subtitle && <p className="text-sm text-mist-500 truncate">{subtitle}</p>}
      </div>
      {right}
    </header>
  );
}

function GridIcon() { return (<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>); }
function ChatIcon() { return (<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>); }
function JournalIcon() { return (<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/><path d="M9 7h7M9 11h7"/></svg>); }
function GlobeIcon() { return (<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/></svg>); }
function ChipIcon() { return (<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3"/></svg>); }
function MenuIcon() { return (<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 6h18M3 12h18M3 18h18"/></svg>); }
function LogoutIcon() { return (<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/></svg>); }
