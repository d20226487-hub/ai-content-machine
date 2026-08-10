/**
 * Pending-navigation marker — lets ChunkReloadGuard resume a navigation it
 * had to interrupt.
 *
 * The problem it solves: flows that produce an expensive result (a paid
 * generation) save it to sessionStorage and then `router.push` to an output
 * page. That push has to fetch the destination's JS chunk. After a rebuild —
 * a production deploy, or a dev recompile while the tab sat open — the chunk
 * URL the page holds is gone, so the fetch 404s and ChunkReloadGuard reloads.
 * A plain `location.reload()` reloads the page the user is ON (the form), so
 * the result is stranded in sessionStorage and the run looks like it silently
 * did nothing — and they pay again to redo it.
 *
 * So: mark the intended destination immediately before navigating. If the
 * guard has to recover, it lands on that destination instead of the form and
 * the result shows up as intended. The marker is consumed once, and expires,
 * so a stale entry can never hijack an unrelated navigation later.
 *
 * The key is interpolated into the guard's inline script, so the two can't
 * drift apart.
 */
export const PENDING_NAV_KEY = "acm_pending_nav";

/** How long a marker stays valid. Generous — the gap between marking and the
 *  push is milliseconds; this only guards against a marker that was never
 *  consumed nor cleared. */
export const PENDING_NAV_TTL_MS = 60_000;

/** Record where we're about to navigate. Call right before `router.push`. */
export function markPendingNav(url: string): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(
      PENDING_NAV_KEY,
      JSON.stringify({ url, at: Date.now() }),
    );
  } catch {
    /* sessionStorage disabled/full — recovery is best-effort, never fatal */
  }
}

/** Drop the marker. Call on the destination page once it has mounted, so a
 *  successful navigation leaves nothing behind. */
export function clearPendingNav(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(PENDING_NAV_KEY);
  } catch {
    /* ignore */
  }
}
