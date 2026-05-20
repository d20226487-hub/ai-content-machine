"use client";

import { CmsTypeSegmented } from "@/components/bulkPublish/CmsTypeSegmented";
import { DomainCombobox } from "@/components/bulkPublish/DomainCombobox";
import { useT } from "@/lib/i18n-context";
import type {
  CmsType,
  Domain,
  DomainPickerItem,
} from "@/lib/domains";

import { Field } from "./Field";

/**
 * Target-side controls for the single-publish modal: CMS type segmented
 * control + search-as-you-type domain picker + (optional) per-publish
 * language picker for multilingual sites.
 *
 * Mirrors the BulkPublishModal's single-mode shape so users moving
 * between Single and Bulk publishing don't have to relearn the picker.
 * Reuses the existing CmsTypeSegmented + DomainCombobox primitives from
 * `bulkPublish/` rather than duplicating them — the boundary between
 * the two modals' sub-component folders is structural, not enforced.
 */
export function TargetPicker({
  cmsType,
  onCmsTypeChange,
  domainId,
  selectedLabel,
  onDomainPicked,
  onPickerResults,
  selected,
  language,
  onLanguageChange,
}: {
  cmsType: CmsType;
  onCmsTypeChange: (v: CmsType) => void;
  domainId: number | null;
  selectedLabel: string | null;
  onDomainPicked: (item: DomainPickerItem) => void;
  onPickerResults: (items: DomainPickerItem[]) => void;
  selected: Domain | null;
  language: string | null;
  onLanguageChange: (lang: string) => void;
}) {
  const { t } = useT();
  const langOptions = selected?.languages ?? [];
  const showLangPicker = langOptions.length > 1;

  return (
    <div className="space-y-3">
      <CmsTypeSegmented value={cmsType} onChange={onCmsTypeChange} />
      <div className="grid grid-cols-2 gap-3">
        <Field label={t("pubMod.fieldDomain")}>
          <DomainCombobox
            value={domainId}
            valueLabel={selectedLabel}
            onChange={onDomainPicked}
            onResults={onPickerResults}
            cmsType={cmsType}
          />
        </Field>
        {showLangPicker && (
          <Field label={t("pubMod.fieldLanguage")}>
            <select
              value={language ?? ""}
              onChange={(e) => onLanguageChange(e.target.value)}
              className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            >
              {langOptions.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </Field>
        )}
      </div>
    </div>
  );
}
