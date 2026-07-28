"use client";

import { useEffect, useMemo, useRef, useState } from "react";

export interface SearchableOption {
  id: number;
  name: string;
}

/**
 * A lightweight type-to-search single-select over an in-memory option list.
 *
 * Used where a plain <select> gets unwieldy (many users / domains). The parent
 * owns the selected id (or "" = none); options are provided fully and filtered
 * client-side. For very large lists the visible results are capped and a hint
 * nudges the user to refine.
 */
export function SearchableSelect({
  value,
  onChange,
  options,
  allLabel,
  placeholder,
  className,
  maxVisible = 100,
}: {
  value: number | "";
  onChange: (v: number | "") => void;
  options: SearchableOption[];
  allLabel: string;
  placeholder?: string;
  className?: string;
  maxVisible?: number;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const wrapRef = useRef<HTMLDivElement>(null);

  const selectedLabel =
    value === "" ? "" : options.find((o) => o.id === value)?.name ?? "";

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const base = q
      ? options.filter((o) => o.name.toLowerCase().includes(q))
      : options;
    return { rows: base.slice(0, maxVisible), total: base.length };
  }, [query, options, maxVisible]);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const inputValue = open ? query : selectedLabel;
  const pick = (v: number | "") => {
    onChange(v);
    setOpen(false);
    setQuery("");
  };

  return (
    <div ref={wrapRef} className="relative">
      <input
        type="text"
        value={inputValue}
        placeholder={placeholder ?? allLabel}
        onFocus={() => {
          setOpen(true);
          setQuery("");
        }}
        onChange={(e) => {
          setOpen(true);
          setQuery(e.target.value);
        }}
        className={className}
      />
      {open && (
        <div className="absolute z-30 mt-1 max-h-72 w-56 overflow-auto rounded-md border border-neutral-300 bg-white py-1 text-sm shadow-lg dark:border-neutral-700 dark:bg-neutral-900">
          <button
            type="button"
            onClick={() => pick("")}
            className={
              "block w-full px-3 py-1.5 text-left hover:bg-neutral-100 dark:hover:bg-neutral-800 " +
              (value === "" ? "bg-neutral-100 font-medium dark:bg-neutral-800" : "")
            }
          >
            {allLabel}
          </button>
          {filtered.rows.map((o) => (
            <button
              key={o.id}
              type="button"
              onClick={() => pick(o.id)}
              className={
                "block w-full truncate px-3 py-1.5 text-left hover:bg-neutral-100 dark:hover:bg-neutral-800 " +
                (o.id === value ? "bg-neutral-100 font-medium dark:bg-neutral-800" : "")
              }
            >
              {o.name}
            </button>
          ))}
          {filtered.total > filtered.rows.length && (
            <div className="border-t border-neutral-200 px-3 py-1.5 text-[11px] text-neutral-500 dark:border-neutral-800 dark:text-neutral-400">
              {filtered.rows.length} / {filtered.total}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
