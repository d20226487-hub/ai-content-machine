/**
 * Small avatar+name chip for "created by" / "owner" attribution.
 *
 * Used on the /prompts and /library cards to make ownership prominent without
 * stealing focus from the resource title. The avatar circle uses a stable
 * hash-derived color so the same person looks the same everywhere they
 * appear, which is faster to scan than reading names.
 */
"use client";

import { useT } from "@/lib/i18n-context";

interface Props {
  name: string;
  /** Tooltip text — defaults to the name. */
  title?: string;
  /** Visual size. Default "sm". */
  size?: "sm" | "md";
  /** Hide the name and show only the avatar circle. */
  avatarOnly?: boolean;
}

const PALETTE = [
  ["bg-blue-100 text-blue-800 ring-blue-200/60", "dark:bg-blue-900/40 dark:text-blue-200 dark:ring-blue-800/60"],
  ["bg-emerald-100 text-emerald-800 ring-emerald-200/60", "dark:bg-emerald-900/40 dark:text-emerald-200 dark:ring-emerald-800/60"],
  ["bg-violet-100 text-violet-800 ring-violet-200/60", "dark:bg-violet-900/40 dark:text-violet-200 dark:ring-violet-800/60"],
  ["bg-amber-100 text-amber-800 ring-amber-200/60", "dark:bg-amber-900/40 dark:text-amber-200 dark:ring-amber-800/60"],
  ["bg-rose-100 text-rose-800 ring-rose-200/60", "dark:bg-rose-900/40 dark:text-rose-200 dark:ring-rose-800/60"],
  ["bg-cyan-100 text-cyan-800 ring-cyan-200/60", "dark:bg-cyan-900/40 dark:text-cyan-200 dark:ring-cyan-800/60"],
  ["bg-fuchsia-100 text-fuchsia-800 ring-fuchsia-200/60", "dark:bg-fuchsia-900/40 dark:text-fuchsia-200 dark:ring-fuchsia-800/60"],
  ["bg-lime-100 text-lime-800 ring-lime-200/60", "dark:bg-lime-900/40 dark:text-lime-200 dark:ring-lime-800/60"],
];

function hashCode(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function UserChip({ name, title, size = "sm", avatarOnly = false }: Props) {
  const { t } = useT();
  const [light, dark] = PALETTE[hashCode(name) % PALETTE.length];
  const initials = initialsOf(name);

  const dot =
    size === "md" ? "h-6 w-6 text-[10px]" : "h-5 w-5 text-[9px]";
  const text = size === "md" ? "text-xs" : "text-[11px]";

  return (
    <span
      className="inline-flex items-center gap-1.5"
      title={title ?? t("userChip.tooltip", { name })}
    >
      <span
        className={`inline-flex shrink-0 items-center justify-center rounded-full font-semibold ring-1 ${dot} ${light} ${dark}`}
        aria-hidden
      >
        {initials}
      </span>
      {!avatarOnly && (
        <span className={`truncate font-medium text-neutral-700 dark:text-neutral-300 ${text}`}>
          {name}
        </span>
      )}
    </span>
  );
}
