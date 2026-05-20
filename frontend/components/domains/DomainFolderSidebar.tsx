"use client";

import { useMemo, useState } from "react";

import { useT } from "@/lib/i18n-context";
import type { DomainFolder, FolderScope } from "@/lib/domains";

/**
 * Folder tree sidebar for the /publish/domains redesign.
 *
 * Renders three special pseudo-rows at the top:
 *   - "All domains" (FolderScope = "all")     — ignores folder placement
 *   - "Root"        (FolderScope = "root")    — domains with no folder
 * …followed by the tree assembled from `folders` (flat list with
 * parent_id, rebuilt into nested children client-side).
 *
 * Selection is the parent's `selected: FolderScope`. We never store the
 * selection internally — the parent owns it and pushes URL state at
 * the same time, so deep-linking (`/publish/domains?folder=N`) and
 * back/forward navigation work without sidebar surgery.
 *
 * Expand/collapse state is local because it has no business living in
 * the URL — refreshing the page shouldn't collapse the user's tree.
 * Defaults to "all expanded" so a fresh visit shows the whole shape.
 *
 * Each row supports:
 *   - click row body          → select folder
 *   - "+"  on hover           → add subfolder (prompt for name)
 *   - "✎"  on hover           → rename (inline prompt)
 *   - "🗑"  on hover (folder)  → delete (error-tolerant; backend refuses
 *                                non-empty with a clear message)
 *
 * Counts (`domain_count`, `subfolder_count`) only render when the
 * parent fetched the list with `with_counts=true`. The picker-style
 * cheap variant works too — counts just stay hidden.
 */
export function DomainFolderSidebar({
  folders,
  selected,
  onSelect,
  onCreate,
  onRename,
  onDelete,
  reloading,
}: {
  folders: DomainFolder[];
  selected: FolderScope;
  onSelect: (scope: FolderScope) => void;
  onCreate: (parentId: number | null) => void;
  onRename: (folder: DomainFolder) => void;
  onDelete: (folder: DomainFolder) => void;
  reloading?: boolean;
}) {
  const { t } = useT();

  // Build a parent_id → children[] map once per `folders` change. Then
  // render recursively starting from null (top-level). Single pass over
  // the list, O(N).
  const children = useMemo(() => {
    const map = new Map<number | null, DomainFolder[]>();
    for (const f of folders) {
      const key = f.parent_id;
      const arr = map.get(key) ?? [];
      arr.push(f);
      map.set(key, arr);
    }
    // Sort each siblings list by name for stable layout.
    for (const arr of map.values()) arr.sort((a, b) => a.name.localeCompare(b.name));
    return map;
  }, [folders]);

  // Per-folder expand state. Default expanded (user can collapse).
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  function toggle(id: number) {
    setCollapsed((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <aside className="w-64 shrink-0 border-r border-neutral-200 pr-3 dark:border-neutral-800">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
          {t("domainFolders.heading")}
        </h2>
        <button
          type="button"
          onClick={() => onCreate(null)}
          title={t("domainFolders.newTopLevel")}
          className="rounded p-1 text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
        >
          +
        </button>
      </div>

      {/* Pseudo-rows for the two scopes that aren't folders. */}
      <ul className="space-y-0.5 text-sm">
        <li>
          <button
            type="button"
            onClick={() => onSelect("all")}
            className={
              "block w-full rounded px-2 py-1 text-left " +
              (selected === "all"
                ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                : "text-neutral-700 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800")
            }
          >
            {t("domainFolders.allDomains")}
          </button>
        </li>
        <li>
          <button
            type="button"
            onClick={() => onSelect("root")}
            className={
              "block w-full rounded px-2 py-1 text-left " +
              (selected === "root"
                ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                : "text-neutral-700 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800")
            }
          >
            {t("domainFolders.root")}
          </button>
        </li>
      </ul>

      {reloading && (
        <p className="mt-2 text-[11px] text-neutral-400">
          {t("common.loading")}
        </p>
      )}

      <ul className="mt-3 space-y-0.5 text-sm">
        {(children.get(null) ?? []).map((f) => (
          <TreeNode
            key={f.id}
            folder={f}
            depth={0}
            childrenMap={children}
            collapsed={collapsed}
            onToggle={toggle}
            selected={selected}
            onSelect={onSelect}
            onCreate={onCreate}
            onRename={onRename}
            onDelete={onDelete}
          />
        ))}
        {folders.length === 0 && !reloading && (
          <li className="px-2 text-[11px] text-neutral-500 dark:text-neutral-400">
            {t("domainFolders.emptyHint")}
          </li>
        )}
      </ul>
    </aside>
  );
}

function TreeNode({
  folder,
  depth,
  childrenMap,
  collapsed,
  onToggle,
  selected,
  onSelect,
  onCreate,
  onRename,
  onDelete,
}: {
  folder: DomainFolder;
  depth: number;
  childrenMap: Map<number | null, DomainFolder[]>;
  collapsed: Set<number>;
  onToggle: (id: number) => void;
  selected: FolderScope;
  onSelect: (scope: FolderScope) => void;
  onCreate: (parentId: number | null) => void;
  onRename: (folder: DomainFolder) => void;
  onDelete: (folder: DomainFolder) => void;
}) {
  const kids = childrenMap.get(folder.id) ?? [];
  const isSelected = selected === folder.id;
  const isCollapsed = collapsed.has(folder.id);
  const showCount =
    typeof folder.domain_count === "number" && folder.domain_count > 0;

  return (
    <li>
      <div
        className={
          "group flex items-center gap-1 rounded px-1.5 py-1 " +
          (isSelected
            ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
            : "text-neutral-700 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800")
        }
        style={{ paddingLeft: 6 + depth * 12 }}
      >
        {kids.length > 0 ? (
          <button
            type="button"
            onClick={() => onToggle(folder.id)}
            className="shrink-0 px-1 text-[10px] text-neutral-500"
            aria-label={isCollapsed ? "expand" : "collapse"}
          >
            {isCollapsed ? "▸" : "▾"}
          </button>
        ) : (
          <span className="inline-block w-[14px]" />
        )}
        <button
          type="button"
          onClick={() => onSelect(folder.id)}
          className="flex-1 truncate text-left"
          title={folder.name}
        >
          {folder.name}
          {showCount && (
            <span
              className={
                "ml-1 text-[10px] " +
                (isSelected
                  ? "text-white/70 dark:text-neutral-900/70"
                  : "text-neutral-500")
              }
            >
              ({folder.domain_count})
            </span>
          )}
        </button>
        {/* Row actions — only visible on hover. Buttons keep the same
            color treatment whether the row is selected or not, with the
            inverted on-selected variant handled by Tailwind selectors. */}
        <div className="hidden shrink-0 gap-0.5 group-hover:flex">
          <IconButton
            label="+"
            title={"+ subfolder"}
            onClick={() => onCreate(folder.id)}
            selected={isSelected}
          />
          <IconButton
            label="✎"
            title="Rename"
            onClick={() => onRename(folder)}
            selected={isSelected}
          />
          <IconButton
            label="🗑"
            title="Delete"
            onClick={() => onDelete(folder)}
            selected={isSelected}
          />
        </div>
      </div>
      {kids.length > 0 && !isCollapsed && (
        <ul className="space-y-0.5">
          {kids.map((c) => (
            <TreeNode
              key={c.id}
              folder={c}
              depth={depth + 1}
              childrenMap={childrenMap}
              collapsed={collapsed}
              onToggle={onToggle}
              selected={selected}
              onSelect={onSelect}
              onCreate={onCreate}
              onRename={onRename}
              onDelete={onDelete}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

function IconButton({
  label,
  title,
  onClick,
  selected,
}: {
  label: string;
  title: string;
  onClick: () => void;
  selected: boolean;
}) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      title={title}
      className={
        "rounded px-1 text-[11px] " +
        (selected
          ? "text-white/80 hover:bg-white/15 dark:text-neutral-900/80 dark:hover:bg-neutral-900/15"
          : "text-neutral-500 hover:bg-neutral-200 dark:hover:bg-neutral-700")
      }
    >
      {label}
    </button>
  );
}
