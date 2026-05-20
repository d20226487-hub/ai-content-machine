"use client";

import { useT } from "@/lib/i18n-context";
import type { DomainFolder, FolderScope } from "@/lib/domains";

/**
 * Path indicator that mirrors the sidebar selection: ``All › Projects ›
 * Casino``. Each segment is clickable so the user can hop up to an
 * ancestor without scrolling the sidebar tree.
 *
 * The path is computed by walking up `parent_id` from the selected
 * folder. We could memoize this but it's cheap (≤ a handful of hops)
 * and the parent already re-renders on selection change.
 */
export function DomainBreadcrumb({
  folders,
  selected,
  onSelect,
}: {
  folders: DomainFolder[];
  selected: FolderScope;
  onSelect: (scope: FolderScope) => void;
}) {
  const { t } = useT();
  const byId = new Map(folders.map((f) => [f.id, f] as const));

  // Build the path: each segment is either a FolderScope (clickable)
  // plus a label. For "all" and "root" the path is just a single
  // segment; for a folder id we walk up the parent chain.
  const segments: { scope: FolderScope; label: string }[] = [];

  if (selected === "all") {
    segments.push({ scope: "all", label: t("domainFolders.allDomains") });
  } else if (selected === "root") {
    segments.push({ scope: "all", label: t("domainFolders.allDomains") });
    segments.push({ scope: "root", label: t("domainFolders.root") });
  } else {
    // Walk up. Collect names in reverse, then reverse for display.
    segments.push({ scope: "all", label: t("domainFolders.allDomains") });
    const chain: DomainFolder[] = [];
    let cursor: number | null = selected;
    const seen = new Set<number>();
    while (cursor !== null) {
      if (seen.has(cursor)) break; // defense in depth — DB shouldn't allow cycles
      seen.add(cursor);
      const f = byId.get(cursor);
      if (!f) break;
      chain.push(f);
      cursor = f.parent_id;
    }
    for (const f of chain.reverse()) {
      segments.push({ scope: f.id, label: f.name });
    }
  }

  return (
    <nav className="mb-3 flex items-center gap-1 text-sm text-neutral-600 dark:text-neutral-400">
      {segments.map((s, i) => {
        const isLast = i === segments.length - 1;
        return (
          <span key={`${i}-${typeof s.scope === "number" ? s.scope : s.scope}`} className="flex items-center gap-1">
            {i > 0 && <span className="text-neutral-400">›</span>}
            {isLast ? (
              <span className="font-medium text-neutral-900 dark:text-neutral-100">
                {s.label}
              </span>
            ) : (
              <button
                type="button"
                onClick={() => onSelect(s.scope)}
                className="hover:text-neutral-900 hover:underline dark:hover:text-neutral-100"
              >
                {s.label}
              </button>
            )}
          </span>
        );
      })}
    </nav>
  );
}
