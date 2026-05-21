"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  listDomainsPicker,
  type DomainPickerItem,
} from "@/lib/domains";

/**
 * Multi-select Custom CMS domain picker.
 *
 * UX: a button that opens a popover with a search input + a scrollable
 * checkbox list. User ticks any number of domains, clicks "Apply" (or
 * Enter), the popover closes and `onChange(items)` fires with the
 * picked DomainPickerItem objects. The parent decides how to render the
 * resulting chip list — this component only handles the picking flow.
 *
 * Why a separate component (vs. extending the existing single-select
 * `DomainCombobox`): the combobox's interaction model is built around
 * onChange-closes-the-popover. Multi-select needs the popover to stay
 * open across multiple ticks, plus a "tick this one" doesn't commit
 * until Apply. Forking the file is cleaner than threading a `mode`
 * prop through every codepath of the existing one.
 *
 * `value` is the parent's current set of picked DomainPickerItems —
 * tick state is derived from it on every render (the popover is just
 * a view onto the parent's state).
 */
export function MultiDomainPicker({
  value,
  onChange,
  cmsType = "custom",
  pageSize = 50,
}: {
  value: DomainPickerItem[];
  onChange: (next: DomainPickerItem[]) => void;
  cmsType?: "wordpress" | "custom";
  pageSize?: number;
}) {
  const { t } = useT();
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<DomainPickerItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Working set inside the popover — separate from `value` so Cancel
  // restores the previous picks. Mirrors value when the popover opens.
  const [working, setWorking] = useState<DomainPickerItem[]>(value);
  useEffect(() => {
    if (open) setWorking(value);
  }, [open, value]);

  // Debounced search — same pattern as DomainCombobox so backend load
  // stays modest even on a fast typer.
  const searchToken = useRef(0);
  const debouncedFetch = useCallback(
    (q: string) => {
      const token = ++searchToken.current;
      setLoading(true);
      listDomainsPicker({ q: q || undefined, cms_type: cmsType, page_size: pageSize })
        .then((r) => {
          if (token !== searchToken.current) return;
          setItems(r.items);
          setLoadError(null);
        })
        .catch((e) => {
          if (token !== searchToken.current) return;
          setLoadError(e instanceof ApiError ? e.message : String(e));
        })
        .finally(() => {
          if (token === searchToken.current) setLoading(false);
        });
    },
    [cmsType, pageSize],
  );

  // Initial load when the popover opens; subsequent reloads only when
  // the search query changes (debounced).
  useEffect(() => {
    if (!open) return;
    const handle = setTimeout(() => debouncedFetch(query), 200);
    return () => clearTimeout(handle);
  }, [open, query, debouncedFetch]);

  // Click-outside closes the popover (commits or cancels? — we keep the
  // existing combobox convention: outside-click acts as Cancel, so the
  // user must explicitly hit Apply to commit a selection. Prevents the
  // accidental-commit problem of click-outside-saves.).
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    }
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [open]);

  const workingById = useMemo(
    () => new Set(working.map((d) => d.id)),
    [working],
  );

  function toggle(item: DomainPickerItem) {
    setWorking((cur) =>
      cur.some((d) => d.id === item.id)
        ? cur.filter((d) => d.id !== item.id)
        : [...cur, item],
    );
  }

  function apply() {
    onChange(working);
    setOpen(false);
  }

  function cancel() {
    setOpen(false);
  }

  return (
    <div ref={wrapRef} className="relative inline-block w-full">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-left text-sm hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100 dark:hover:bg-neutral-800"
      >
        {value.length > 0
          ? t("multiPicker.openWithCount", { count: value.length })
          : t("multiPicker.openEmpty")}
        <span aria-hidden className="float-right text-neutral-400">
          ▾
        </span>
      </button>

      {open && (
        <div className="absolute z-30 mt-1 w-full overflow-hidden rounded-md border border-neutral-300 bg-white shadow-lg dark:border-neutral-700 dark:bg-neutral-900">
          <input
            autoFocus
            placeholder={t("multiPicker.searchPlaceholder")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="block w-full border-b border-neutral-200 px-3 py-2 text-sm focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
          />
          <div className="max-h-72 overflow-auto py-1 text-sm">
            {loading && (
              <p className="px-3 py-2 text-xs text-neutral-500 dark:text-neutral-400">
                {t("multiPicker.loading")}
              </p>
            )}
            {loadError && (
              <p className="px-3 py-2 text-xs text-red-700 dark:text-red-300">
                {loadError}
              </p>
            )}
            {!loading && !loadError && items.length === 0 && (
              <p className="px-3 py-2 text-xs text-neutral-500 dark:text-neutral-400">
                {t("multiPicker.empty")}
              </p>
            )}
            {items.map((d) => {
              const ticked = workingById.has(d.id);
              const disabled = !d.has_credentials;
              return (
                <label
                  key={d.id}
                  className={
                    "flex cursor-pointer items-center gap-2 px-3 py-1.5 hover:bg-neutral-50 dark:hover:bg-neutral-800 " +
                    (disabled ? "cursor-not-allowed opacity-50" : "")
                  }
                >
                  <input
                    type="checkbox"
                    disabled={disabled}
                    checked={ticked}
                    onChange={() => toggle(d)}
                    className="h-4 w-4"
                  />
                  <span className="flex-1 truncate">{d.name}</span>
                  {!d.has_credentials && (
                    <span className="text-[10px] uppercase tracking-wide text-neutral-400">
                      {t("multiPicker.noCreds")}
                    </span>
                  )}
                </label>
              );
            })}
          </div>
          <div className="flex items-center justify-between gap-2 border-t border-neutral-200 px-3 py-2 dark:border-neutral-800">
            <span className="text-[11px] text-neutral-500 dark:text-neutral-400">
              {t("multiPicker.tickedCount", { count: working.length })}
            </span>
            <div className="space-x-2">
              <button
                type="button"
                onClick={cancel}
                className="rounded-md px-2 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800"
              >
                {t("multiPicker.cancel")}
              </button>
              <button
                type="button"
                onClick={apply}
                className="rounded-md bg-blue-600 px-2 py-1 text-xs font-medium text-white hover:bg-blue-700 dark:bg-blue-500"
              >
                {t("multiPicker.apply")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
