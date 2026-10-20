import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useI18n } from "../i18n/index.jsx";
import { useAuth } from "../auth/AuthContext.jsx";
import { useCopy } from "./copy.js";
import { Container, GoldButton } from "./primitives.jsx";
import { EASE } from "./motion.jsx";

/**
 * Chrome for every public page: navbar, footer, scroll progress.
 *
 * The navbar has two states. At the top of the page it is fully transparent so
 * the hero runs edge to edge behind it. Past ~40px it detaches into a floating
 * glass pill, inset from the edges and blurred. The transition is a change of
 * layout rather than just colour, which is what makes it read as deliberate
 * product design instead of a generic sticky header.
 */

const SECTIONS = [
  { key: "features", to: "/features", hash: "#features" },
  { key: "ai", to: "/ai", hash: "#ai" },
  { key: "scalp", to: "/scalp", hash: "#scalp" },
  { key: "how", to: "/how-it-works", hash: "#how-it-works" },
  { key: "pricing", to: "/pricing", hash: "#pricing" },
];

function Logo({ onClick }) {
  return (
    <Link
      to="/"
      onClick={onClick}
      className="group flex items-center gap-2.5"
      aria-label="SmartPips home"
    >
      {/* The real SmartPips mark, not a lettermark stand-in. A hairline gold
          ring keeps it reading as an intentional badge against the black
          rather than a pasted-on PNG. */}
      <img
        src="/logo-icon.png"
        alt=""
        width={32}
        height={32}
        className="h-8 w-8 rounded-[8px] object-cover ring-1 ring-signal/25 transition-all duration-300 group-hover:ring-signal/55"
      />
      <span className="text-[15px] font-semibold tracking-tight text-sp-t1">
        Smart<span className="text-signal">Pips</span>
      </span>
    </Link>
  );
}

/** Scroll-linked progress hairline pinned to the very top of the viewport. */
function ScrollProgress() {
  const [pct, setPct] = useState(0);

  useEffect(() => {
    let raf = 0;
    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const max = document.documentElement.scrollHeight - window.innerHeight;
        setPct(max > 0 ? (window.scrollY / max) * 100 : 0);
      });
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <div className="fixed inset-x-0 top-0 z-[60] h-px" aria-hidden>
      <div
        className="h-full origin-start bg-gradient-to-r from-signal/0 via-signal to-signal/0"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function LanguageToggle({ compact = false }) {
  const { lang, toggle } = useI18n();
  return (
    <button
      type="button"
      onClick={toggle}
      className={`rounded-full border border-white/10 font-mono text-[10px] uppercase
        tracking-[0.12em] text-sp-t2 transition-colors duration-300
        hover:border-signal/40 hover:text-signal ${compact ? "px-2.5 py-1" : "px-3 py-1.5"}`}
      aria-label="Switch language"
    >
      {lang === "fa" ? "EN" : "\u0641\u0627"}
    </button>
  );
}

export default function SiteLayout() {
  const c = useCopy();
  // AuthProvider wraps the whole app in main.jsx, so this is always available.
  // It is used only to choose between "Login" and "Open App" in the navbar.
  const { isAuthed } = useAuth();
  const reduced = useReducedMotion();
  const location = useLocation();
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  // Detach the navbar shortly after the page starts moving.
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Close the mobile sheet on navigation, and lock body scroll while it is open.
  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    document.body.style.overflow = menuOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [menuOpen]);

  // Anchor links only make sense on the landing page itself.
  const onLanding = location.pathname === "/";

  return (
    <div className="min-h-screen bg-sp-void text-sp-t1 antialiased">
      <ScrollProgress />

      {/* ---------------- navbar ---------------- */}
      <div
        className={`fixed inset-x-0 z-50 transition-all duration-500 ${
          scrolled ? "top-3 px-3 sm:px-5" : "top-0 px-0"
        }`}
        style={{ transitionTimingFunction: "cubic-bezier(0.2,0.7,0.3,1)" }}
      >
        <nav
          className={`mx-auto flex items-center gap-4 transition-all duration-500 ${
            scrolled
              ? "max-w-[1080px] rounded-2xl border border-white/[0.07] bg-sp-s1/75 px-4 py-2.5 shadow-[0_10px_40px_-16px_rgba(0,0,0,0.9)] backdrop-blur-xl sm:px-5"
              : "max-w-site border border-transparent px-5 py-5 sm:px-8"
          }`}
          style={{ transitionTimingFunction: "cubic-bezier(0.2,0.7,0.3,1)" }}
        >
          <Logo />

          {/* centre links */}
          <div className="mx-auto hidden items-center gap-1 lg:flex">
            {SECTIONS.map((s) =>
              onLanding ? (
                <a
                  key={s.key}
                  href={s.hash}
                  className="rounded-lg px-3 py-1.5 text-[13px] text-sp-t2
                    transition-colors duration-300 hover:text-sp-t1"
                >
                  {c.nav[s.key]}
                </a>
              ) : (
                <NavLink
                  key={s.key}
                  to={s.to}
                  className={({ isActive }) =>
                    `rounded-lg px-3 py-1.5 text-[13px] transition-colors duration-300 ${
                      isActive ? "text-signal" : "text-sp-t2 hover:text-sp-t1"
                    }`
                  }
                >
                  {c.nav[s.key]}
                </NavLink>
              ),
            )}
          </div>

          {/* right cluster */}
          <div className="ms-auto flex items-center gap-2 lg:ms-0">
            <LanguageToggle compact={scrolled} />

            <Link
              to={isAuthed ? "/app" : "/login"}
              className="hidden rounded-full px-3 py-1.5 text-[13px] text-sp-t2
                transition-colors duration-300 hover:text-sp-t1 sm:block"
            >
              {isAuthed ? c.nav.openApp : c.nav.login}
            </Link>

            <GoldButton to="/register" size="sm" className="hidden sm:inline-flex">
              {c.nav.start}
            </GoldButton>

            {/* mobile trigger */}
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              className="grid h-9 w-9 place-items-center rounded-lg border border-white/10
                text-sp-t2 transition-colors hover:text-sp-t1 lg:hidden"
              aria-label={menuOpen ? c.nav.close : c.nav.menu}
              aria-expanded={menuOpen}
            >
              <svg
                viewBox="0 0 24 24"
                className="h-4 w-4"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
              >
                {menuOpen ? (
                  <path d="M6 6l12 12M18 6L6 18" />
                ) : (
                  <path d="M4 7h16M4 12h16M4 17h16" />
                )}
              </svg>
            </button>
          </div>
        </nav>
      </div>

      {/* ---------------- mobile sheet ---------------- */}
      <AnimatePresence>
        {menuOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="fixed inset-0 z-40 bg-sp-void/95 backdrop-blur-xl lg:hidden"
          >
            <div className="flex h-full flex-col justify-center px-8">
              {SECTIONS.map((s, i) => (
                <motion.div
                  key={s.key}
                  initial={reduced ? false : { opacity: 0, y: 18 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.06 + i * 0.05, duration: 0.4, ease: EASE }}
                >
                  <Link
                    to={s.to}
                    onClick={() => setMenuOpen(false)}
                    className="block border-b border-white/[0.06] py-4 text-2xl
                      font-semibold text-sp-t1"
                  >
                    {c.nav[s.key]}
                  </Link>
                </motion.div>
              ))}

              <motion.div
                initial={reduced ? false : { opacity: 0, y: 18 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.36, duration: 0.4, ease: EASE }}
                className="mt-8 flex flex-col gap-3"
              >
                <GoldButton to={isAuthed ? "/app" : "/register"} size="lg">
                  {isAuthed ? c.nav.openApp : c.nav.start}
                </GoldButton>
                {!isAuthed && (
                  <Link
                    to="/login"
                    className="rounded-full border border-white/10 px-5 py-3
                      text-center text-sm text-sp-t2"
                  >
                    {c.nav.login}
                  </Link>
                )}
              </motion.div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ---------------- page ---------------- */}
      <main>
        <Outlet />
      </main>

      {/* ---------------- footer ---------------- */}
      <footer className="border-t border-white/[0.06] bg-sp-void">
        <Container size="wide">
          <div className="grid gap-10 py-14 sm:grid-cols-2 lg:grid-cols-[1.6fr_1fr_1fr_1fr]">
            <div>
              <Logo />
              <p className="mt-4 max-w-xs text-sm leading-relaxed text-sp-t4">
                {c.footer.tagline}
              </p>
            </div>

            {[
              {
                title: c.footer.product,
                links: [
                  [c.nav.features, "/features"],
                  [c.nav.ai, "/ai"],
                  [c.nav.scalp, "/scalp"],
                  [c.nav.pricing, "/pricing"],
                ],
              },
              {
                title: c.footer.company,
                links: [
                  ["About", "/about"],
                  ["Contact", "/contact"],
                ],
              },
              {
                title: c.footer.resources,
                links: [
                  [c.nav.how, "/how-it-works"],
                  ["FAQ", "/faq"],
                ],
              },
            ].map((col) => (
              <div key={col.title}>
                <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-sp-t4">
                  {col.title}
                </div>
                <ul className="mt-4 space-y-2.5">
                  {col.links.map(([label, to]) => (
                    <li key={to}>
                      <Link
                        to={to}
                        className="text-sm text-sp-t2 transition-colors duration-300 hover:text-signal"
                      >
                        {label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <div className="border-t border-white/[0.06] py-6">
            <p className="text-xs leading-relaxed text-sp-t4">{c.footer.risk}</p>
            <p className="mt-3 text-xs text-sp-t4">
              © {new Date().getFullYear()} SmartPips. {c.footer.rights}
            </p>
          </div>
        </Container>
      </footer>
    </div>
  );
}
