// Web Push helpers. On iPhone these work only when the site is installed to the
// Home Screen (Add to Home Screen) on iOS 16.4+ and opened from that icon.
import { alertsApi } from "../api/client.js";

export function pushSupported() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

// iOS only allows push from an installed PWA (standalone display mode).
export function isStandalone() {
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    window.navigator.standalone === true
  );
}

export function isIOS() {
  return /iphone|ipad|ipod/i.test(navigator.userAgent);
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

export async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return null;
  return navigator.serviceWorker.register("/sw.js");
}

export async function enablePush() {
  if (!pushSupported()) throw new Error("not_supported");
  if (isIOS() && !isStandalone()) throw new Error("ios_needs_install");

  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("permission_denied");

  const reg = await navigator.serviceWorker.ready;
  const { public_key: publicKey, configured } = await alertsApi.vapid();
  if (!configured || !publicKey) throw new Error("server_not_configured");

  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey),
    });
  }
  await alertsApi.subscribe(sub.toJSON());
  return true;
}

export async function disablePush() {
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) {
      await alertsApi.unsubscribe({ endpoint: sub.endpoint });
      await sub.unsubscribe();
    }
  } catch { /* ignore */ }
}
