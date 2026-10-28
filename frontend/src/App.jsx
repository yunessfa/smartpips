import { useEffect, lazy, Suspense } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./auth/AuthContext.jsx";
import Layout from "./components/Layout.jsx";
import Login from "./pages/Login.jsx";
const Dashboard = lazy(() => import("./pages/Dashboard.jsx"));
const Chat = lazy(() => import("./pages/Chat.jsx"));
const Sources = lazy(() => import("./pages/Sources.jsx"));
const AISettings = lazy(() => import("./pages/AISettings.jsx"));
const Trades = lazy(() => import("./pages/Trades.jsx"));
const Scalp = lazy(() => import("./pages/Scalp.jsx"));
const Admin = lazy(() => import("./pages/Admin.jsx"));
const Bitunix = lazy(() => import("./pages/Bitunix.jsx"));
const Logs = lazy(() => import("./pages/Logs.jsx"));
const Notifications = lazy(() => import("./pages/Notifications.jsx"));
const Strategies = lazy(() => import("./pages/Strategies.jsx"));
import SiteLayout from "./site/SiteLayout.jsx";
import Landing from "./site/pages/Landing.jsx";
import { LivePriceProvider } from "./live/LivePrices.jsx";
// Secondary marketing pages load on demand so the first visit downloads less.
const FeaturesPage = lazy(() => import("./site/pages/Product.jsx").then((m) => ({ default: m.FeaturesPage })));
const AIPage = lazy(() => import("./site/pages/Product.jsx").then((m) => ({ default: m.AIPage })));
const ScalpPage = lazy(() => import("./site/pages/Product.jsx").then((m) => ({ default: m.ScalpPage })));
const ExitPage = lazy(() => import("./site/pages/Product.jsx").then((m) => ({ default: m.ExitPage })));
const AboutPage = lazy(() => import("./site/pages/Company.jsx").then((m) => ({ default: m.AboutPage })));
const HowPage = lazy(() => import("./site/pages/Company.jsx").then((m) => ({ default: m.HowPage })));
const PricingPage = lazy(() => import("./site/pages/Commerce.jsx").then((m) => ({ default: m.PricingPage })));
const FaqPage = lazy(() => import("./site/pages/Commerce.jsx").then((m) => ({ default: m.FaqPage })));
const ContactPage = lazy(() => import("./site/pages/Commerce.jsx").then((m) => ({ default: m.ContactPage })));

/**
 * Two completely separate surfaces share one router:
 *
 *   /       …  the public marketing site  (SiteLayout → its own chrome)
 *   /app/*  …  the trading terminal       (Protected → Layout, unchanged)
 *
 * The panel's internal structure is untouched — it simply moved one level
 * down. Anything that previously lived at "/x" now lives at "/app/x".
 */

function Protected({ children }) {
  const { isAuthed, ready } = useAuth();
  const location = useLocation();
  if (!ready) {
    return (
      <div className="min-h-screen grid place-items-center bg-ink-900 text-mist-500">
        <span className="h-6 w-6 rounded-full border-2 border-mist-500 border-t-transparent animate-spin" />
      </div>
    );
  }
  if (!isAuthed) return <Navigate to="/login" state={{ from: location }} replace />;
  return children;
}

/**
 * Restores the browser's default "jump to top on navigate" behaviour, which a
 * client-side router otherwise removes. Only applied to the public site — the
 * panel keeps scroll position between tabs on purpose.
 */
function ScrollToTop() {
  const { pathname } = useLocation();
  // Must be an effect, not a render-time call: scrolling during render is a
  // side effect React is allowed to run twice (StrictMode) or discard, and it
  // fired on every re-render rather than only on navigation.
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [pathname]);
  return null;
}

export default function App() {
  return (
    <Suspense fallback={<div role="status" className="p-6 text-mist-500">در حال بارگذاری…</div>}>
    <Routes>
      {/* ---------------- public site ---------------- */}
      <Route
        element={
          <>
            <ScrollToTop />
            <SiteLayout />
          </>
        }
      >
        <Route path="/" element={<Landing />} />

        <Route path="/about" element={<AboutPage />} />
        <Route path="/features" element={<FeaturesPage />} />
        <Route path="/ai" element={<AIPage />} />
        <Route path="/scalp" element={<ScalpPage />} />
        <Route path="/smart-exit" element={<ExitPage />} />
        <Route path="/how-it-works" element={<HowPage />} />
        <Route path="/pricing" element={<PricingPage />} />
        <Route path="/faq" element={<FaqPage />} />
        <Route path="/contact" element={<ContactPage />} />
      </Route>

      {/* ---------------- auth ---------------- */}
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Login />} />

      {/* ---------------- trading panel ---------------- */}
      <Route
        path="/app/*"
        element={
          <Protected>
            {/* Live price feeds (Binance WS, metals polling, private quotes)
                run only inside the panel — never for anonymous site visitors. */}
            <LivePriceProvider>
            <Layout>
              <Suspense fallback={<div role="status" className="flex-1 min-h-0 p-6 text-mist-500" data-page-loading>در حال بارگذاری صفحه…</div>}>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/chat" element={<Chat />} />
                <Route path="/trades" element={<Trades />} />
                <Route path="/scalp" element={<Scalp />} />
                <Route path="/bitunix" element={<Bitunix />} />
                <Route path="/admin" element={<Admin />} />
                <Route path="/logs" element={<Logs />} />
                <Route path="/sources" element={<Sources />} />
                <Route path="/ai" element={<AISettings />} />
                <Route path="/notifications" element={<Notifications />} />
                <Route path="/strategies" element={<Strategies />} />
                <Route path="*" element={<Navigate to="/app" replace />} />
              </Routes>
              </Suspense>
            </Layout>
            </LivePriceProvider>
          </Protected>
        }
      />

      {/* Unknown paths belong to the public site, not the panel. */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </Suspense>
  );
}
