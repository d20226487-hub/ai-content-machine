"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useT } from "@/lib/i18n-context";
import {
  listDomainsPicker,
  type CmsType,
  type DomainPickerItem,
} from "@/lib/domains";

/**
 * Search-as-you-type domain picker, backed by ``GET /domains/picker``.
 *
 * Purpose: replace the unfiltered ``<select>`` dropdown that loaded every
 * domain on mount. With thousands of sites, that approach was about to
 * become unusable (1–2 KB per row × 5k rows × every modal open = multi-MB
 * payloads, multi-second renders, scroll-stuck dropdowns).
 *
 * Behavior:
 *   - On mount and on `cmsType` change, fetches the first page of
 *     results (50 by default) with no query.
 *   - On typed input, debounces 200 ms then refetches.
 *   - On selection, calls onChange(item) and closes the popover.
 *   - Click-outside closes the popover.
 *   - Results without credentials are shown but visually muted and
 *     non-selectable — the user can see they exist but can't pick them
 *     until creds are added.
 *
 * The parent owns the selected id + label. We never store a "current
 * selection" internally; everything visible is either a fresh fetch or
 * the parent's value passed in via `valueLabel`. Keeps the round-trip
 * with the parent's full-domain-fetch effect simple.
 */
export function DomainCombobox({
  value,
  valueLabel,
  onChange,
  onResults,
  cmsType,
  placeholder,
  disabled,
}: {
  /** Currently-selected domain id, or null. */
  value: number | null;
  /** Human-readable label for the current selection, shown in the input
   *  when the popover is closed. Parent owns this because the selected
   *  domain isn't necessarily in the current page of results. */
  valueLabel: string | null;
  /** Called after the user picks an item from the dropdown. */
  onChange: (item: DomainPickerItem) => void;
  /** Optional callback that fires every time a fresh page of results
   *  arrives. The bulk publish modal uses this to auto-pick the first
   *  credentialled domain on initial load. */
  onResults?: (items: DomainPickerItem[]) => void;
  cmsType: CmsType;
  placeholder?: string;
  disabled?: boolean;
}) {
  const { t } = useT();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<DomainPickerItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [total, setTotal] = useState(0);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Single source of truth for "do a fetch with these args". Memoized so
  // the debounced query effect can call it without re-creating per render.
  // Latest-wins guard: every call tags itself with a fresh token; only
  // the most recent token gets to overwrite state, so a fast-typing user
  // never sees stale results pop in after their newer query resolved.
  const fetchTokenRef = useRef(0);
  const onResultsRef = useRef(onResults);
  onResultsRef.current = onResults;
  const doFetch = useCallback(
    async (q: string, ct: CmsType) => {
      const token = ++fetchTokenRef.current;
      setLoading(true);
      setError(null);
      try {
        const resp = await listDomainsPicker({
          q,
          cms_type: ct,
          page: 1,
          page_size: 50,
        });
        if (token !== fetchTokenRef.current) return; // stale
        setResults(resp.items);
        setTotal(resp.total);
        onResultsRef.current?.(resp.items);
      } catch (e) {
        if (token !== fetchTokenRef.current) return;
        setError(e instanceof Error ? e.message : t("domainCombo.loadFailed"));
      } finally {
        if (token === fetchTokenRef.current) setLoading(false);
      }
    },
    [t],
  );

  // Initial + cmsType-change fetch. Reset the query when cmsType flips so
  // the new list isn't accidentally filtered by a leftover search.
  useEffect(() => {
    setQuery("");
    doFetch("", cmsType);
  }, [cmsType, doFetch]);

  // Debounced re-fetch on user typing. 200 ms is below the comfortable
  // perception threshold for "instant" feedback but high enough to
  // collapse rapid keystrokes into one request.
  useEffect(() => {
    // Initial mount already triggered a fetch via the cmsType effect.
    if (query === "") return;
    const handle = window.setTimeout(() => {
      doFetch(query, cmsType);
    }, 200);
    return () => window.clearTimeout(handle);
  }, [query, cmsType, doFetch]);

  // Click-outside → close popover.
  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  // What to show in the closed input: the parent's label, or empty.
  // When the popover is open we let the user type freely (query field).
  const inputValue = open ? query : (valueLabel ?? "");

  const hasResults = results.length > 0;
  const placeholderText = placeholder ?? t("domainCombo.placeholder");

  // Pre-resolve the "no domains for this type" copy — surfaces when the
  // server returns zero rows for the current cmsType filter with no
  // active query. Different from "no matches" (q set, 0 results).
  const emptyMessage = useMemo(() => {
    if (loading) return t("domainCombo.loading");
    if (query.trim()) return t("domainCombo.noMatches", { q: query.trim() });
    return t("domainCombo.noDomainsForType");
  }, [loading, query, t]);

  return (
    <div ref={wrapRef} className="relative">
      <input
        type="text"
        value={inputValue}
        placeholder={placeholderText}
        disabled={disabled}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          // Opening the popover when the user starts typing is implicit —
          // a focused-but-closed input would be confusing.
          if (!open) setOpen(true);
          setQuery(e.target.value);
        }}
        className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
      />
      {open && (
        <div className="absolute z-30 mt-1 max-h-72 w-full overflow-auto rounded-md border border-neutral-300 bg-white py-1 text-sm shadow-lg dark:border-neutral-700 dark:bg-neutral-900">
          {error && (
            <div className="px-3 py-2 text-xs text-red-700 dark:text-red-300">
              {error}
            </div>
          )}
          {!error && !hasResults && (
            <div className="px-3 py-2 text-xs text-neutral-500 dark:text-neutral-400">
              {emptyMessage}
            </div>
          )}
          {!error &&
            hasResults &&
            results.map((it) => {
              const isSelected = it.id === value;
              const disabledRow = !it.has_credentials;
              return (
                <button
                  key={it.id}
                  type="button"
                  disabled={disabledRow}
                  onClick={() => {
                    onChange(it);
                    setOpen(false);
                    setQuery("");
                  }}
                  className={
                    "flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left " +
                    (disabledRow
                      ? "cursor-not-allowed opacity-50"
                      : "hover:bg-neutral-100 dark:hover:bg-neutral-800") +
                    (isSelected
                      ? " bg-neutral-100 font-medium dark:bg-neutral-800"
                      : "")
                  }
                >
                  <span className="truncate">{it.name}</span>
                  <span className="shrink-0 text-[10px] uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                    {disabledRow ? t("domainCombo.noCreds") : ""}
                  </span>
                </button>
              );
            })}
          {!error && hasResults && total > results.length && (
            <div className="border-t border-neutral-200 px-3 py-1.5 text-[11px] text-neutral-500 dark:border-neutral-800 dark:text-neutral-400">
              {t("domainCombo.refineHint", {
                shown: results.length,
                total,
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
