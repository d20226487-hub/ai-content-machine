"use client";

/**
 * Single-publish modal's label wrapper. Mirrors the equivalent in
 * `components/bulkPublish/` — small enough that duplicating it across
 * the two modals is cheaper than threading an extra import.
 */
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {label}
      </span>
      {children}
      {hint && (
        <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">{hint}</p>
      )}
    </label>
  );
}
