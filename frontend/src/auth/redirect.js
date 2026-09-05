/**
 * Where should the user land after signing in or registering?
 *
 * The Protected route stashes the location it bounced the user away from in
 * `navigate(..., { state: { from: location } })`. That value is *almost* the
 * right answer, but not quite:
 *
 *   - It can be a public page ("/", "/pricing", …) if the user reached /login
 *     from the marketing site. Sending them back there after authenticating
 *     is the single most confusing outcome — they just signed in and land on
 *     the sales page.
 *   - It can be "/login" or "/register" themselves, which would loop.
 *   - It is user-influenced (it survives in history state), so it should not
 *     be treated as trusted input for an off-site redirect.
 *
 * Rule: only ever return a path inside the trading panel. Anything else
 * collapses to the panel root.
 */

export const PANEL_ROOT = "/app";

/**
 * True only for same-origin paths under /app. Rejects protocol-relative
 * ("//evil.com") and absolute ("https://evil.com") values, which would
 * otherwise be an open-redirect through history state.
 */
export function isPanelPath(pathname) {
  if (typeof pathname !== "string") return false;
  if (!pathname.startsWith("/")) return false;
  if (pathname.startsWith("//")) return false;
  return pathname === PANEL_ROOT || pathname.startsWith(`${PANEL_ROOT}/`);
}

/**
 * Resolve the post-authentication destination.
 *
 * @param {object|null} from - the `location` object stored by Protected.
 * @returns {string} a path that is always inside the panel.
 *
 * Preserves search and hash so a deep link like
 *   /app/scalp?symbol=SUIUSDT:PERP&tf=5m&quick=1
 * survives the login round-trip intact — which is exactly the push-notification
 * case: tapping an alert while logged out must still open that chart.
 */
export function resolvePostAuthTarget(from) {
  const pathname = from?.pathname;
  if (!isPanelPath(pathname)) return PANEL_ROOT;
  return `${pathname}${from.search || ""}${from.hash || ""}`;
}
