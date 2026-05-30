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
 */
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
