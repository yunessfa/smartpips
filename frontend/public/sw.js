/* SmartPips service worker — handles Web Push (works on installed iOS PWAs, 16.4+). */

/* Bump this when the file changes so browsers pick up the new worker. */
const SW_VERSION = "v18";

/**
 * Public routes served by the marketing site. Everything else belongs to the
 * trading panel, which lives under /app.
 *
 * Kept in sync with the public routes in src/App.jsx.
 */
const PUBLIC_PATHS = [
  "/",
  "/about",
  "/features",
  "/ai",
  "/scalp-engine",
  "/smart-exit",
  "/how-it-works",
  "/pricing",
  "/faq",
  "/contact",
  "/login",
  "/register",
];

/**
 * Normalise a push deep link to the panel.
 *
 * The panel used to be mounted at the root, so links were emitted as
 * "/scalp?symbol=...". Once the public website took over the root path those
 * links started resolving to the marketing site (or to the catch-all redirect)
 * instead of the chart.
 *
 * The server now emits "/app/..." directly, but notifications already sitting
 * in a user's tray still carry the old path — and those payloads cannot be
 * rewritten retroactively. So we repair them here, at click time. This also
 * means a stale service worker paired with a fixed backend, or vice versa,
 * still lands the user on the right screen.
 */
function normalizePanelUrl(raw) {
  let url = typeof raw === "string" && raw ? raw : "/app/scalp";

  // Absolute URLs from the same origin are reduced to a path; foreign origins
  // are handed back untouched.
  if (/^https?:\/\//i.test(url)) {
    try {
      const parsed = new URL(url);
      if (parsed.origin !== self.location.origin) return url;
      url = parsed.pathname + parsed.search + parsed.hash;
    } catch (e) {
      return url;
    }
  }

  if (url.charAt(0) !== "/") url = "/" + url;

  // Already correct.
  if (url === "/app" || url.indexOf("/app/") === 0 || url.indexOf("/app?") === 0) {
    return url;
  }

  // A genuine public page: leave it alone.
  const pathOnly = url.split("?")[0].split("#")[0].replace(/\/+$/, "") || "/";
  if (PUBLIC_PATHS.indexOf(pathOnly) !== -1) return url;

  // Anything else is a panel route emitted before the /app prefix existed.
  return "/app" + url;
}

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { title: "SmartPips", body: event.data ? event.data.text() : "" };
  }
  const title = data.title || "SmartPips";
  const options = {
    body: data.body || "",
    icon: "/logo-icon.png",
    badge: "/logo-icon.png",
    // Normalised on the way in as well as on click, so the stored URL is
    // already correct for any future handler.
    data: { url: normalizePanelUrl(data.url) },
    vibrate: [80, 40, 80],
    tag: data.symbol ? `${data.symbol}-${data.timeframe}` : "smartpips",
    renotify: true,
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = normalizePanelUrl(event.notification.data && event.notification.data.url);

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        if ("focus" in client) {
          // navigate() can reject if the client is in an unexpected state;
          // focusing anyway is better than swallowing the click entirely.
          try {
            client.navigate(target);
          } catch (e) {
            /* ignore */
          }
          return client.focus();
        }
      }
      if (self.clients.openWindow) return self.clients.openWindow(target);
      return undefined;
    }),
  );
});
