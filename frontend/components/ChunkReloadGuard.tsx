/**
 * Catches Next.js webpack chunk-load failures and reloads the page so
 * the browser fetches the fresh chunks.
 *
 * Why an inline string instead of a React component: when the layout's
 * own chunk fails to load (the worst case — what the user actually
 * hits), React never mounts and a useEffect-based handler never
 * registers. An inline `<script>` in `<head>` runs during HTML
 * parsing, before any module load, so it catches even the boot-time
 * failures that knocked out React in the first place.
 *
 * Triggers:
 *   1. `error` events whose source is a `<script>` tag or whose
 *      `error.name === "ChunkLoadError"`. Webpack labels failed chunk
 *      fetches with that name; the browser-level error event fires
 *      for any `<script src=…>` that 404s or times out.
 *   2. `unhandledrejection` for promises that rejected with a
 *      chunk-load error (lazy imports, Next.js dynamic).
 *
 * Circuit breaker: a sessionStorage timestamp prevents reload loops if
 * the build is genuinely broken — two failures within 8 seconds and
 * we surface the error instead of cycling the user.
 *
 * Pending navigation: a plain reload re-renders the page the user is ON,
 * which silently drops whatever navigation was in flight. When the failing
 * chunk was the destination of a `router.push` — the usual case, since that
 * push is what fetches the chunk — recovering to the CURRENT url strands the
 * result the caller just saved (see lib/pendingNav.ts). So if a fresh
 * pending-navigation marker exists, recover to that destination instead. The
 * marker is consumed here, so a second failure falls back to a plain reload
 * rather than bouncing between routes.
 */
import { PENDING_NAV_KEY, PENDING_NAV_TTL_MS } from "@/lib/pendingNav";

export const chunkReloadScript = `
(function() {
  if (typeof window === "undefined") return;
  var RELOAD_KEY = "acm_chunk_reload_at";
  var COOLDOWN_MS = 8000;

  function isChunkLoadError(err) {
    if (!err) return false;
    if (err.name === "ChunkLoadError") return true;
    var msg = err.message || String(err);
    return /Loading chunk [\\w\\-\\/\\.\\(\\)]+ failed/i.test(msg)
        || /ChunkLoadError/i.test(msg)
        || /Loading CSS chunk/i.test(msg);
  }

  function recover(reason) {
    try {
      var now = Date.now();
      var last = Number(sessionStorage.getItem(RELOAD_KEY) || "0");
      if (now - last < COOLDOWN_MS) {
        console.warn("[ChunkReloadGuard] suppressing reload (recent retry)", reason);
        return;
      }
      sessionStorage.setItem(RELOAD_KEY, String(now));

      // Resume an interrupted navigation, if one was marked recently. Consumed
      // unconditionally so a repeat failure can't ping-pong between routes.
      var dest = "";
      try {
        var raw = sessionStorage.getItem("${PENDING_NAV_KEY}");
        if (raw) {
          sessionStorage.removeItem("${PENDING_NAV_KEY}");
          var pn = JSON.parse(raw);
          if (pn && pn.url && (now - Number(pn.at || 0)) < ${PENDING_NAV_TTL_MS}) {
            dest = String(pn.url);
          }
        }
      } catch (e) { /* malformed marker - fall through to a plain reload */ }

      if (dest) {
        console.warn("[ChunkReloadGuard] chunk load failed - resuming nav to", dest, reason);
        window.location.replace(dest);
        return;
      }
      console.warn("[ChunkReloadGuard] chunk load failed - reloading", reason);
      window.location.reload();
    } catch (e) {
      console.error("[ChunkReloadGuard] recovery failed", e);
    }
  }

  window.addEventListener("error", function(e) {
    // Resource-level error (script/link tag failed to load): e.target
    // is the failing element, e.error is usually null.
    if (e && e.target && e.target !== window) {
      var t = e.target;
      var src = t && (t.src || t.href) || "";
      if (/\\/_next\\/static\\/chunks\\//.test(src)) {
        recover("script tag failed: " + src);
        return;
      }
    }
    if (isChunkLoadError(e && e.error) || isChunkLoadError(e)) {
      recover("error event: " + (e && e.message));
    }
  }, true); // capture phase — resource errors don't bubble

  window.addEventListener("unhandledrejection", function(e) {
    if (isChunkLoadError(e && e.reason)) {
      recover("unhandled rejection: " + (e.reason && e.reason.message));
    }
  });
})();
`;
