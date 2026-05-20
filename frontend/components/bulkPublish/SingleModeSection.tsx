"use client";

import { useT } from "@/lib/i18n-context";
import { DomainCombobox } from "@/components/bulkPublish/DomainCombobox";
import type {
  CmsType,
  Domain,
  DomainPickerItem,
  PublishProfile,
} from "@/lib/domains";
import type { BulkColumn } from "@/lib/types";

/**
 * Single-mode targets: which domain, which profile (WP), which language,
 * optional per-row language column.
 *
 * Rendered when the parent's `mode === "single"`. The domain picker is a
 * search-as-you-type combobox (backed by the lite picker endpoint) — the
 * parent owns the value + selected label and reacts to selection by
 * fetching the full Domain. CMS-type comes from the segmented control
 * upstream so the combobox can pre-filter server-side.
 *
 * Profile picker shows only when the selected domain is WP and has at
 * least one profile. Language picker + language column picker show only
 * when the selected domain advertises >1 language (for monolingual sites
 * the controls would just be noise).
 */
export function SingleModeSection({
  cmsTypeFilter,
  domainId,
  selectedLabel,
  onDomainPicked,
  onPickerResults,
  selected,
  wpProfiles,
  profileName,
  onProfileNameChange,
  language,
  onLanguageChange,
  languageColumnId,
  onLanguageColumnIdChange,
  columns,
}: {
  cmsTypeFilter: CmsType;
  domainId: number | null;
  selectedLabel: string | null;
  onDomainPicked: (item: DomainPickerItem) => void;
  onPickerResults: (items: DomainPickerItem[]) => void;
  selected: Domain | null;
  wpProfiles: PublishProfile[];
  profileName: string | null;
  onProfileNameChange: (name: string) => void;
  language: string | null;
  onLanguageChange: (lang: string) => void;
  languageColumnId: number | "";
  onLanguageColumnIdChange: (v: number | "") => void;
  columns: BulkColumn[];
}) {
  const { t } = useT();
  const showProfile =
    selected?.cms_type === "wordpress" && wpProfiles.length > 0;
  const showLanguagePickers = selected != null && selected.languages.length > 1;

  return (
    <div className="grid grid-cols-2 gap-3">
      <Field label={t("bulkPub.fieldDomain")}>
        <DomainCombobox
          value={domainId}
          valueLabel={selectedLabel}
          onChange={onDomainPicked}
          onResults={onPickerResults}
          cmsType={cmsTypeFilter}
        />
      </Field>

      {showProfile && (
        <Field label={t("bulkPub.fieldPostType")}>
          <select
            value={profileName ?? ""}
            onChange={(e) => onProfileNameChange(e.target.value)}
            disabled={wpProfiles.length === 1}
            className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm disabled:opacity-70 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
          >
            {wpProfiles.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name} — {p.post_type}
              </option>
            ))}
          </select>
        </Field>
      )}

      {showLanguagePickers && (
        <Field label={t("bulkPub.fieldLanguage")}>
          <select
            value={language ?? ""}
            onChange={(e) => onLanguageChange(e.target.value)}
            className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
          >
            {selected!.languages.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </Field>
      )}

      {/* Optional per-row language column. Single mode only renders this
          for multilingual domains — for a single-language site this is
          just clutter. When set, the run-level Language picker above
          becomes the fallback display; the actual language per row comes
          from the cell. Same strict semantics as multi-mode: empty cell
          fails the row, unknown value fails the row. */}
      {showLanguagePickers && (
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
      )}
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
