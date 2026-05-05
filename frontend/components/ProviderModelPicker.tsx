"use client";

import type { EnabledProvider } from "@/lib/types";

interface Props {
  providers: EnabledProvider[];
  providerCode: string | null;
  model: string | null;
  onProviderChange: (code: string | null) => void;
  onModelChange: (model: string | null) => void;
  /** When true, the "use workspace default" empty option is shown. */
  allowDefault?: boolean;
  className?: string;
  size?: "sm" | "md";
}

/**
 * Reusable Provider + Model dropdown pair.
 *
 * Providers without an API key are rendered as disabled options labeled
 * "(no API key)" so the user can see the full list of *enabled* providers
 * and understand why some are not selectable.
 */
export function ProviderModelPicker({
  providers,
  providerCode,
  model,
  onProviderChange,
  onModelChange,
  allowDefault = false,
  className = "",
  size = "md",
}: Props) {
  const selected = providers.find((p) => p.code === providerCode);
  const text = size === "sm" ? "text-xs" : "text-sm";
  const inputClass =
    "mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 " +
    text +
    " focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-900";

  if (providers.length === 0) {
    return (
      <p className={"rounded-md bg-amber-50 px-3 py-2 " + text + " text-amber-800 dark:bg-amber-950/40 dark:text-amber-300 " + className}>
        No provider enabled. Configure one in Settings.
      </p>
    );
  }

  return (
    <div className={"grid gap-3 sm:grid-cols-2 " + className}>
      <label className={"block " + text + " font-medium text-neutral-700 dark:text-neutral-300"}>
        Provider
        <select
          value={providerCode ?? ""}
          onChange={(e) => onProviderChange(e.target.value || null)}
          className={inputClass}
        >
          {allowDefault && (
            <option value="">— Use workspace default —</option>
          )}
          {providers.map((p) => (
            <option
              key={p.code}
              value={p.code}
              disabled={!p.has_api_key}
            >
              {p.display_name}
              {!p.has_api_key && " (no API key)"}
            </option>
          ))}
        </select>
        {selected && !selected.has_api_key && (
          <p className="mt-1 text-[11px] text-amber-700 dark:text-amber-400">
            This provider has no API key in Settings — it can&apos;t generate yet.
          </p>
        )}
      </label>
      <label className={"block " + text + " font-medium text-neutral-700 dark:text-neutral-300"}>
        Model
        <select
          value={model ?? ""}
          onChange={(e) => onModelChange(e.target.value || null)}
          disabled={!selected}
          className={inputClass}
        >
          {allowDefault && <option value="">(use provider default)</option>}
          {(selected?.available_models?.length
            ? selected.available_models
            : selected?.default_model
              ? [selected.default_model]
              : []
          ).map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
