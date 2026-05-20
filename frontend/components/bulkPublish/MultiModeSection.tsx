"use client";

import { useT } from "@/lib/i18n-context";
import type { BulkColumn } from "@/lib/types";

/**
 * Multi-mode targets: three column references (domain, profile, language)
 * pulled from the bulk table itself.
 *
 *   - Domain column   — required. Each row's cell value resolves to a
 *                       domain by name.
 *   - Profile column  — optional. WP-only concept; if a row's domain is
 *                       Custom or the cell is empty, the domain's default
 *                       profile is used.
 *   - Language column — optional. Drives per-row language for WP
 *                       Polylang/WPML routing and for the body's lang
 *                       field on Custom CMS. Strict: empty cell fails
 *                       the row.
 */
export function MultiModeSection({
  domainColumnId,
  onDomainColumnIdChange,
  profileColumnId,
  onProfileColumnIdChange,
  languageColumnId,
  onLanguageColumnIdChange,
  columns,
}: {
  domainColumnId: number | "";
  onDomainColumnIdChange: (v: number | "") => void;
  profileColumnId: number | "";
  onProfileColumnIdChange: (v: number | "") => void;
  languageColumnId: number | "";
  onLanguageColumnIdChange: (v: number | "") => void;
  columns: BulkColumn[];
}) {
  const { t } = useT();
  return (
    <div className="grid grid-cols-2 gap-3">
      <Field label={t("bulkPub.fieldDomainColumn")}>
        <select
          value={domainColumnId}
          onChange={(e) =>
            onDomainColumnIdChange(e.target.value ? Number(e.target.value) : "")
          }
          className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        >
          <option value="">{t("bulkPub.pickColumn")}</option>
          {columns.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label={t("bulkPub.fieldProfileColumn")}>
        <select
          value={profileColumnId}
          onChange={(e) =>
            onProfileColumnIdChange(e.target.value ? Number(e.target.value) : "")
          }
          className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        >
          <option value="">{t("bulkPub.profileColumnDefault")}</option>
          {columns.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <p className="mt-1 text-[11px] text-neutral-500 dark:text-neutral-400">
          {t("bulkPub.profileColumnHint")}
        </p>
      </Field>
      <Field label={t("bulkPub.fieldLanguageColumn")}>
        <select
          value={languageColumnId}
          onChange={(e) =>
            onLanguageColumnIdChange(e.target.value ? Number(e.target.value) : "")
          }
          className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        >
          <option value="">{t("bulkPub.languageColumnDefault")}</option>
          {columns.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <p className="mt-1 text-[11px] text-neutral-500 dark:text-neutral-400">
          {t("bulkPub.languageColumnHint")}
        </p>
      </Field>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {label}
      </span>
      {children}
    </label>
  );
}
