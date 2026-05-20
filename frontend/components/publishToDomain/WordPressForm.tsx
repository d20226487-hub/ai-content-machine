"use client";

import { useT } from "@/lib/i18n-context";
import {
  DEFAULT_WP_FIELDS,
  type Domain,
  type PublishProfile,
  type WpField,
} from "@/lib/domains";

import { Field } from "./Field";

/**
 * WordPress-specific publish form for the single-publish modal.
 *
 * Layout:
 *   - "No publish_config" hint when the selected domain has never had
 *     profiles configured (legacy domains still work via DEFAULT_WP_FIELDS,
 *     but the user should know they're publishing through the implicit
 *     default schema, not something they curated themselves).
 *   - Profile picker — only shown when the domain has >=1 saved profile.
 *     Disabled when there's exactly one (it'd be a no-op control).
 *   - One input per field in the active profile, dispatched by type.
 */
export function WordPressForm({
  selected,
  wpProfiles,
  profileName,
  onProfileNameChange,
  activeProfile,
  values,
  onFieldChange,
}: {
  selected: Domain;
  wpProfiles: PublishProfile[];
  profileName: string | null;
  onProfileNameChange: (name: string) => void;
  activeProfile: PublishProfile | null;
  values: Record<string, string>;
  onFieldChange: (key: string, value: string) => void;
}) {
  const { t } = useT();
  return (
    <div className="space-y-3 border-t border-neutral-200 pt-3 dark:border-neutral-800">
      {!selected.publish_config && (
        <p className="rounded-md bg-blue-50 px-3 py-2 text-xs text-blue-800 dark:bg-blue-950/40 dark:text-blue-300">
          {t("pubMod.noFormConfigured")}
        </p>
      )}

      {wpProfiles.length > 0 && (
        <Field label={t("pubMod.fieldPostType")}>
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

      {(activeProfile?.fields ?? DEFAULT_WP_FIELDS).map((f) => (
        <WpFormInput
          key={f.key}
          field={f}
          value={values[f.key] ?? ""}
          onChange={(v) => onFieldChange(f.key, v)}
        />
      ))}
    </div>
  );
}

function WpFormInput({
  field,
  value,
  onChange,
}: {
  field: WpField;
  value: string;
  onChange: (v: string) => void;
}) {
  const { t } = useT();
  const labelText = field.label + (field.required ? ` ${t("pubMod.required")}` : "");
  if (field.type === "textarea") {
    return (
      <Field label={labelText}>
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={8}
          required={field.required}
          className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm font-mono dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        />
      </Field>
    );
  }
  if (field.type === "select") {
    return (
      <Field label={labelText}>
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required={field.required}
          className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        >
          {(field.options ?? []).map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </Field>
    );
  }
  // text / taxonomy_ids / media_url all render as text inputs in v1.
  return (
    <Field
      label={labelText}
      hint={
        field.type === "taxonomy_ids"
          ? t("pubMod.taxonomyHint", { tax: field.taxonomy ?? "taxonomy" })
          : field.type === "media_url"
            ? t("pubMod.mediaHint")
            : undefined
      }
    >
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={field.required}
        className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
      />
    </Field>
  );
}
