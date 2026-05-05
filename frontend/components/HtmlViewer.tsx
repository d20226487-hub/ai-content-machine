"use client";

import { useMemo, useState } from "react";

import { useT } from "@/lib/i18n-context";

type Mode = "preview" | "raw";

/** Hard cap on content the inline iframe will render. Above this we show a
 * placeholder with Copy + Open-in-window so a runaway 50MB cell can't OOM the
 * browser tab. Hand-tuned: ~1MB is a comfortable upper bound for a single
 * generated article. */
const MAX_INLINE_BYTES = 1_000_000;

interface Props {
  /** Generated content. May be raw text or HTML. */
  content: string;
  /** Optional title shown above. */
  title?: string;
  /** Tailwind height utility for the iframe (e.g. "h-96"). */
  height?: string;
}

/**
 * Renders model output inside a fully-sandboxed iframe.
 * The empty `sandbox` attribute disables scripts, popups, top-level navigation,
 * cookies, storage — anything that could harm the host app — even if the model
 * outputs malicious tags.
 */
export function HtmlViewer({ content, title, height = "h-96" }: Props) {
  const { t } = useT();
  const [mode, setMode] = useState<Mode>("preview");
  const oversize = content.length > MAX_INLINE_BYTES;

  const looksLikeHtml = useMemo(
    () => (oversize ? false : /<\/?[a-z][\s\S]*>/i.test(content)),
    [content, oversize],
  );

  // Wrap raw text in a <pre> so it renders predictably; pass HTML through unchanged.
  // Skip the costly srcDoc build entirely when oversized.
  const srcDoc = useMemo(() => {
    if (oversize) return "";
    const body = looksLikeHtml
      ? renderWpSelfClosingBlocks(content)
      : `<pre style="white-space:pre-wrap;word-wrap:break-word;font-family:ui-monospace,SFMono-Regular,monospace;font-size:13px;margin:0;">${escapeHtml(content)}</pre>`;
    return `<!doctype html><html><head><meta charset="utf-8"><style>
      :root { color-scheme: light dark; }
      html, body { margin: 0; padding: 16px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; line-height: 1.55; }
      body { color: #111; background: #fff; }
      @media (prefers-color-scheme: dark) {
        body { color: #f5f5f5; background: #0a0a0a; }
      }
      img { max-width: 100%; height: auto; }
      pre, code { background: rgba(127,127,127,0.12); padding: 0.1em 0.3em; border-radius: 4px; }
      pre { padding: 12px; overflow: auto; }
      a { color: #2563eb; }
      h1, h2, h3 { line-height: 1.25; }
      .wp-block-placeholder {
        margin: 10px 0;
        border: 1px dashed rgba(127,127,127,0.45);
        border-radius: 6px;
        background: rgba(127,127,127,0.05);
        overflow: hidden;
      }
      .wp-block-placeholder__head {
        font-family: ui-monospace, SFMono-Regular, monospace;
        font-size: 11px;
        font-weight: 600;
        background: rgba(127,127,127,0.12);
        padding: 4px 10px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: #444;
      }
      @media (prefers-color-scheme: dark) {
        .wp-block-placeholder__head { color: #d0d0d0; }
      }
      .wp-block-placeholder__data {
        margin: 0;
        padding: 8px 10px;
        font-family: ui-monospace, SFMono-Regular, monospace;
        font-size: 11px;
        line-height: 1.45;
        white-space: pre-wrap;
        word-break: break-word;
        color: #555;
        background: transparent;
        border-radius: 0;
      }
      @media (prefers-color-scheme: dark) {
        .wp-block-placeholder__data { color: #a8a8a8; }
      }
    </style></head><body>${body}</body></html>`;
  }, [content, looksLikeHtml, oversize]);

  function copy() {
    void navigator.clipboard.writeText(content);
  }

  /**
   * Open the generated content in a new window.
   *
   * The naive ``window.open("") + document.write(...)`` is a same-origin XSS
   * sink — the popup inherits the app's origin and ``localStorage``, so a
   * ``<script>`` tag in model output could exfiltrate the JWT (which lives in
   * ``localStorage``). Instead we host the content inside a fully-sandboxed
   * iframe served from a Blob URL: ``sandbox="allow-popups"`` (so internal
   * links still open in a new tab) but no scripts, no same-origin access, no
   * top-level navigation, no storage. Same protection as the inline iframe.
   */
  function openWindow() {
    const innerBody = /<\/?[a-z][\s\S]*>/i.test(content)
      ? renderWpSelfClosingBlocks(content)
      : `<pre style="white-space:pre-wrap;word-wrap:break-word;font-family:ui-monospace,SFMono-Regular,monospace;font-size:13px;margin:0;">${escapeHtml(content)}</pre>`;
    const innerDoc =
      `<!doctype html><html><head><meta charset="utf-8"><base target="_blank">` +
      `<style>html,body{margin:0;padding:16px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;line-height:1.55;}` +
      `img{max-width:100%;height:auto;}pre,code{background:rgba(127,127,127,0.12);padding:0.1em 0.3em;border-radius:4px;}` +
      `pre{padding:12px;overflow:auto;}a{color:#2563eb;}</style>` +
      `</head><body>${innerBody}</body></html>`;

    const innerBlob = new Blob([innerDoc], { type: "text/html" });
    const innerUrl = URL.createObjectURL(innerBlob);

    // Outer wrapper in the popup. The popup itself runs no scripts; the iframe
    // is sandboxed; the iframe document is served from a Blob URL whose origin
    // is opaque, so even if it tried, it can't read the parent or the app's
    // localStorage.
    const wrapper =
      `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(title ?? "Output")}</title>` +
      `<style>html,body{margin:0;padding:0;height:100%;background:#fff;}iframe{display:block;width:100%;height:100%;border:0;}</style>` +
      `</head><body><iframe sandbox="allow-popups allow-popups-to-escape-sandbox" src="${innerUrl}"></iframe></body></html>`;

    const wrapperBlob = new Blob([wrapper], { type: "text/html" });
    const wrapperUrl = URL.createObjectURL(wrapperBlob);

    const w = window.open(wrapperUrl, "_blank", "width=900,height=700,noopener");
    // Free the inner blob URL once the popup has had a chance to load it.
    // The wrapper URL is kept alive a touch longer for the same reason; both
    // are revoked together to avoid the popup losing its source mid-load.
    setTimeout(() => {
      URL.revokeObjectURL(innerUrl);
      URL.revokeObjectURL(wrapperUrl);
    }, 60_000);
    if (!w) {
      // Popup blocked — fall back to copying the content to the clipboard so
      // the user still has a way out. Better than silently losing the click.
      copy();
    }
  }

  return (
    <div className="rounded-lg border border-neutral-200 bg-white shadow-sm dark:border-neutral-800 dark:bg-neutral-900">
      <header className="flex items-center justify-between border-b border-neutral-200 px-4 py-2 dark:border-neutral-800">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
            {title ?? t("htmlViewer.title")}
          </h3>
          {looksLikeHtml && (
            <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">
              HTML
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-md border border-neutral-200 p-0.5 text-xs dark:border-neutral-700">
            <button
              type="button"
              onClick={() => setMode("preview")}
              className={
                "rounded px-2 py-0.5 font-medium " +
                (mode === "preview"
                  ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                  : "text-neutral-600 dark:text-neutral-400")
              }
            >
              {t("htmlViewer.preview")}
            </button>
            <button
              type="button"
              onClick={() => setMode("raw")}
              className={
                "rounded px-2 py-0.5 font-medium " +
                (mode === "raw"
                  ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                  : "text-neutral-600 dark:text-neutral-400")
              }
            >
              {t("htmlViewer.raw")}
            </button>
          </div>
          <button
            type="button"
            onClick={copy}
            className="rounded-md border border-neutral-300 px-2 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            {t("common.copy")}
          </button>
          <button
            type="button"
            onClick={openWindow}
            className="rounded-md border border-neutral-300 px-2 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            title={t("htmlViewer.openWindow")}
          >
            {t("common.openArrow")}
          </button>
        </div>
      </header>

      {oversize ? (
        <div
          className={`flex flex-col items-center justify-center gap-2 p-6 text-center text-sm text-neutral-700 dark:text-neutral-300 ${height}`}
        >
          <p className="font-medium">{t("htmlViewer.tooLarge")}</p>
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            {formatBytes(content.length)} —
            {" "}
            <button
              type="button"
              onClick={openWindow}
              className="underline hover:text-neutral-900 dark:hover:text-neutral-100"
            >
              {t("htmlViewer.openInWindow")}
            </button>
            {" "}{t("library.empty.or")}{" "}
            <button
              type="button"
              onClick={copy}
              className="underline hover:text-neutral-900 dark:hover:text-neutral-100"
            >
              {t("htmlViewer.copyAction")}
            </button>
            .
          </p>
        </div>
      ) : mode === "preview" ? (
        <iframe
          title={title ?? t("single.generatedContent")}
          sandbox=""
          srcDoc={srcDoc}
          className={`block w-full ${height} bg-white dark:bg-neutral-950`}
        />
      ) : (
        <pre className={`overflow-auto whitespace-pre-wrap break-words p-4 font-mono text-xs text-neutral-800 dark:text-neutral-200 ${height}`}>
          {content}
        </pre>
      )}
    </div>
  );
}

// Matches an HTML comment in isolation (non-greedy stops at the first `-->`).
// We process comments one at a time so a self-closing block's regex can't
// greedily span past unrelated wrapping comments to find a far-away `/-->`.
const HTML_COMMENT_RE = /<!--[\s\S]*?-->/g;

// Inside a single, isolated comment: matches a self-closing Gutenberg block
// like `<!-- wp:acf/demo {…} /-->` or `<!-- wp:foo /-->`.
const WP_SELFCLOSE_INNER_RE =
  /^<!--\s+wp:([\w/-]+)((?:\s+\{[\s\S]*\})?)\s+\/-->$/;

/**
 * Replace self-closing WordPress Gutenberg block comments with visible
 * placeholder boxes that show the block name + its attribute JSON.
 *
 * Wrapping blocks (`<!-- wp:foo --> … <!-- /wp:foo -->`) are left alone — their
 * inner HTML already renders. Only self-closing blocks (which produce zero
 * visible output without the WP runtime) need a placeholder.
 */
function renderWpSelfClosingBlocks(html: string): string {
  return html.replace(HTML_COMMENT_RE, (comment) => {
    const m = comment.match(WP_SELFCLOSE_INNER_RE);
    if (!m) return comment; // wrapping open/close, or non-WP comment — leave as-is
    const name = m[1];
    const attrs = (m[2] || "").trim();
    let pretty = "";
    if (attrs) {
      try {
        pretty = JSON.stringify(JSON.parse(attrs), null, 2);
      } catch {
        pretty = attrs;
      }
    }
    const head = `<div class="wp-block-placeholder__head">wp:${escapeHtml(name)}</div>`;
    const dataBlock = pretty
      ? `<pre class="wp-block-placeholder__data">${escapeHtml(pretty)}</pre>`
      : "";
    return `<div class="wp-block-placeholder">${head}${dataBlock}</div>`;
  });
}

function escapeHtml(s: string): string {
  return s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
