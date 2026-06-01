import type { ChangeSegment } from "@/lib/structureFormat";

/**
 * Renders a condensed single-pane structure/formatting diff: ``del`` = removed
 * (red strikethrough), ``add`` = added (green), ``equal`` = dimmed (the elided
 * runs already carry their ellipsis). Shared by the run page and the tool
 * page's preview.
 */
export function ChangeDiff({ segments }: { segments: ChangeSegment[] }) {
  return (
    <span className="block max-h-32 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">
      {segments.map((s, i) =>
        s.kind === "del" ? (
          <mark
            key={i}
            className="bg-red-50 text-red-600 line-through decoration-red-400/70 dark:bg-red-950/30 dark:text-red-400"
          >
            {s.text}
          </mark>
        ) : s.kind === "add" ? (
          <mark
            key={i}
            className="bg-green-50 font-semibold text-green-700 dark:bg-green-950/30 dark:text-green-300"
          >
            {s.text}
          </mark>
        ) : (
          <span key={i} className="text-neutral-400 dark:text-neutral-500">
            {s.text}
          </span>
        ),
      )}
    </span>
  );
}
