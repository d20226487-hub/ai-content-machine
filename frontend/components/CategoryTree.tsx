"use client";

import { useMemo, useState } from "react";

import type { Category } from "@/lib/types";

interface TreeNode {
  category: Category;
  children: TreeNode[];
}

function buildTree(cats: Category[]): TreeNode[] {
  const byParent = new Map<number | null, Category[]>();
  for (const c of cats) {
    const arr = byParent.get(c.parent_id) ?? [];
    arr.push(c);
    byParent.set(c.parent_id, arr);
  }
  const build = (parentId: number | null): TreeNode[] => {
    const list = (byParent.get(parentId) ?? []).slice().sort((a, b) =>
      a.name.localeCompare(b.name),
    );
    return list.map((c) => ({ category: c, children: build(c.id) }));
  };
  return build(null);
}

interface RowCallbacks {
  selectedId: number | "all";
  onSelect: (id: number | "all") => void;
  onCreateChild: (parentId: number | null) => void;
  onRename: (cat: Category) => void;
  onDelete: (cat: Category) => void;
}

interface TreeProps extends RowCallbacks {
  categories: Category[];
}

export function CategoryTree(props: TreeProps) {
  const { categories, ...cbs } = props;
  const tree = useMemo(() => buildTree(categories), [categories]);

  return (
    <div>
      <button
        onClick={() => cbs.onSelect("all")}
        className={
          "flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm font-medium " +
          (cbs.selectedId === "all"
            ? "bg-neutral-100 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
            : "text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-800")
        }
      >
        <span>All prompts</span>
      </button>

      <div className="mt-2 flex items-center justify-between px-2">
        <span className="text-[11px] uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
          Folders
        </span>
        <button
          onClick={() => cbs.onCreateChild(null)}
          className="text-xs text-neutral-500 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-100"
          title="New top-level folder"
        >
          + New
        </button>
      </div>

      <ul className="mt-1">
        {tree.map((node) => (
          <TreeRow key={node.category.id} node={node} depth={0} {...cbs} />
        ))}
        {tree.length === 0 && (
          <li className="px-2 py-1.5 text-xs text-neutral-400 dark:text-neutral-500">No folders yet</li>
        )}
      </ul>
    </div>
  );
}

interface RowProps extends RowCallbacks {
  node: TreeNode;
  depth: number;
}

function TreeRow({
  node,
  depth,
  selectedId,
  onSelect,
  onCreateChild,
  onRename,
  onDelete,
}: RowProps) {
  const [open, setOpen] = useState(true);
  const [hover, setHover] = useState(false);
  const hasChildren = node.children.length > 0;
  const active = selectedId === node.category.id;

  return (
    <li>
      <div
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        className={
          "group flex items-center rounded-md text-sm " +
          (active ? "bg-neutral-100 dark:bg-neutral-800" : "hover:bg-neutral-50 dark:hover:bg-neutral-800")
        }
        style={{ paddingLeft: 8 + depth * 14 }}
      >
        <button
          onClick={() => setOpen((v) => !v)}
          className="px-1 text-neutral-400 dark:text-neutral-500"
          aria-label={open ? "Collapse" : "Expand"}
        >
          {hasChildren ? (open ? "▾" : "▸") : <span className="inline-block w-2" />}
        </button>
        <button
          onClick={() => onSelect(node.category.id)}
          className={
            "flex-1 truncate py-1 pr-2 text-left " +
            (active ? "font-medium text-neutral-900 dark:text-neutral-100" : "text-neutral-700 dark:text-neutral-300")
          }
        >
          {node.category.name}
        </button>
        {hover && (
          <div className="flex items-center pr-1 text-xs text-neutral-500 dark:text-neutral-400">
            <button
              onClick={() => onCreateChild(node.category.id)}
              className="px-1 hover:text-neutral-900 dark:hover:text-neutral-100"
              title="New subfolder"
            >
              +
            </button>
            <button
              onClick={() => onRename(node.category)}
              className="px-1 hover:text-neutral-900 dark:hover:text-neutral-100"
              title="Rename"
            >
              ✎
            </button>
            <button
              onClick={() => onDelete(node.category)}
              className="px-1 hover:text-red-600 dark:hover:text-red-400"
              title="Delete"
            >
              ×
            </button>
          </div>
        )}
      </div>
      {open && hasChildren && (
        <ul>
          {node.children.map((child) => (
            <TreeRow
              key={child.category.id}
              node={child}
              depth={depth + 1}
              selectedId={selectedId}
              onSelect={onSelect}
              onCreateChild={onCreateChild}
              onRename={onRename}
              onDelete={onDelete}
            />
          ))}
        </ul>
      )}
    </li>
  );
}
