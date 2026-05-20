"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Modal } from "@/components/Modal";
import { CustomCmsForm } from "@/components/publishToDomain/CustomCmsForm";
import { ResultPanel } from "@/components/publishToDomain/ResultPanel";
import { TargetPicker } from "@/components/publishToDomain/TargetPicker";
import { WordPressForm } from "@/components/publishToDomain/WordPressForm";
import { collectPlaceholders } from "@/components/publishToDomain/placeholders";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  DEFAULT_WP_FIELDS,
  getDomain,
  listDomainsPicker,
  type CmsType,
  type Domain,
  type DomainPickerItem,
  type PublishProfile,
} from "@/lib/domains";
import { getPublishJob, publishSingle, type PublishJobDetail } from "@/lib/publish";

interface Props {
  initialTitle?: string;
  initialContent: string;
  initialSlugSuggestion?: string;
  sourceRef?: Record<string, unknown> | null;
  onClose: () => void;
}

function profilesOf(d: Domain): PublishProfile[] {
  const saved = d.publish_config?.profiles;
  if (saved && saved.length > 0) return saved;
  // Domain has no profiles configured — fall back to a single Default
  // profile with the standard WP field set so legacy domains still work.
  return [{ name: "Default", post_type: "posts", fields: DEFAULT_WP_FIELDS }];
}

/**
 * "Publish to a single domain" modal — surfaced from the Single (Create)
 * mode after generating content.
 *
 * Phase A symmetry with BulkPublishModal:
 *   - CMS-type segmented control at the top so the domain picker stays
 *     filtered server-side. Default seeded from the first credentialled
 *     domain on load.
 *   - DomainCombobox replaces the unfiltered <select> — the modal no
 *     longer loads every site on mount, so a 5k-site fleet doesn't pay
 *     the multi-MB payload tax just to publish one post.
 *   - Heavy `Domain` record fetched on demand via `getDomain(id)` only
 *     after a pick lands; the lite picker rows are enough to populate
 *     the input label.
 *
 * State stays here (orchestrator); rendering lives in
 * `components/publishToDomain/*`.
 */
export function PublishToDomainModal({
  initialTitle,
  initialContent,
  initialSlugSuggestion,
  sourceRef,
  onClose,
}: Props) {
  const { t } = useT();

  // CMS-type segmented control — drives both the form panels rendered
  // below AND the combobox's server-side filter.
  const [cmsType, setCmsType] = useState<CmsType>("wordpress");

  // Picker state. domainId is the source of truth; selectedLabel keeps
  // the combobox input populated while the heavy Domain fetch is in
  // flight after a pick (sub-50ms locally but a real round-trip in prod).
  const [domainId, setDomainId] = useState<number | null>(null);
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null);
  const [selected, setSelected] = useState<Domain | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Publish-form state.
  const [profileName, setProfileName] = useState<string | null>(null);
  const [language, setLanguage] = useState<string | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});

  // Publish flow state.
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PublishJobDetail | null>(null);

  // Discovery on mount: seed the CMS-type segmented control to whatever
  // the first credentialled domain happens to be (picker is ordered
  // credentialled-first). Avoids the papercut of an all-Custom fleet
  // landing on WP-by-default with an empty combobox.
  useEffect(() => {
    listDomainsPicker({ page_size: 1 })
      .then((r) => {
        if (r.items.length > 0) {
          setCmsType(r.items[0].cms_type);
        }
      })
      .catch((err) =>
        setLoadError(
          err instanceof ApiError ? err.message : t("pubMod.failedLoadDomains"),
        ),
      );
  }, [t]);

  // First-page-of-results callback: auto-pick the first credentialled
  // domain when the parent currently has nothing selected. Fires after
  // each CMS-type flip too (the combobox refetches with the new filter).
  const onPickerResults = useCallback(
    (items: DomainPickerItem[]) => {
      if (domainId != null) return;
      const pick = items.find((d) => d.has_credentials) ?? items[0] ?? null;
      if (!pick) return;
      setDomainId(pick.id);
      setSelectedLabel(pick.name);
    },
    [domainId],
  );

  // Latest-wins token so a slow Domain fetch can't clobber a newer pick.
  const fullDomainTokenRef = useRef(0);
  useEffect(() => {
    if (domainId == null) {
      setSelected(null);
      return;
    }
    const token = ++fullDomainTokenRef.current;
    getDomain(domainId)
      .then((d) => {
        if (token !== fullDomainTokenRef.current) return;
        setSelected(d);
        setSelectedLabel(d.name);
      })
      .catch((err) => {
        if (token !== fullDomainTokenRef.current) return;
        setLoadError(
          err instanceof ApiError ? err.message : t("pubMod.failedLoadDomains"),
        );
      });
  }, [domainId, t]);

  // Flipping the CMS-type control invalidates the current selection: a
  // WP domain isn't a valid target for the Custom panel and vice versa.
  // Clear everything; the combobox auto-picks the first credentialled
  // match in the new type via `onPickerResults`.
  function onCmsTypeChange(next: CmsType) {
    if (next === cmsType) return;
    setCmsType(next);
    setDomainId(null);
    setSelected(null);
    setSelectedLabel(null);
  }

  function onDomainPicked(item: DomainPickerItem) {
    setDomainId(item.id);
    setSelectedLabel(item.name);
  }

  // WP profile derivation + default-pick on domain change.
  const wpProfiles: PublishProfile[] = useMemo(
    () => (selected?.cms_type === "wordpress" ? profilesOf(selected) : []),
    [selected],
  );
  const activeProfile: PublishProfile | null = useMemo(() => {
    if (selected?.cms_type !== "wordpress") return null;
    if (wpProfiles.length === 0) return null;
    return wpProfiles.find((p) => p.name === profileName) ?? wpProfiles[0];
  }, [selected, wpProfiles, profileName]);

  useEffect(() => {
    if (selected?.cms_type === "wordpress" && wpProfiles.length > 0) {
      setProfileName((cur) =>
        cur && wpProfiles.some((p) => p.name === cur) ? cur : wpProfiles[0].name,
      );
    } else {
      setProfileName(null);
    }
  }, [selected, wpProfiles]);

  // Seed the form values from the active profile / Custom placeholders,
  // pre-filling title + content + slug from the props the parent passed in.
  useEffect(() => {
    if (!selected) {
      setValues({});
      setLanguage(null);
      return;
    }
    setLanguage(selected.languages[0] ?? "en");

    const next: Record<string, string> = {};
    if (selected.cms_type === "wordpress") {
      const fields = activeProfile?.fields ?? DEFAULT_WP_FIELDS;
      for (const f of fields) {
        if (f.key === "title" && initialTitle) next[f.key] = initialTitle;
        else if (f.key === "content") next[f.key] = initialContent;
        else if (f.key === "slug" && initialSlugSuggestion) {
          next[f.key] = initialSlugSuggestion;
        } else if (f.key === "status") {
          next[f.key] = (f.options ?? ["publish"])[0] ?? "publish";
        } else next[f.key] = "";
      }
    } else if (selected.cms_type === "custom") {
      const placeholders = collectPlaceholders(selected.custom_config?.body_template);
      for (const ph of placeholders) {
        if (ph === "title" && initialTitle) next[ph] = initialTitle;
        else if (ph === "content") next[ph] = initialContent;
        else if (ph === "slug" && initialSlugSuggestion) {
          next[ph] = initialSlugSuggestion;
        } else if (ph === "language") {
          // Language is sent separately via the language picker. Skip.
          continue;
        } else next[ph] = "";
      }
    }
    setValues(next);
  }, [selected, activeProfile, initialTitle, initialContent, initialSlugSuggestion]);

  function setField(key: string, v: string) {
    setValues((m) => ({ ...m, [key]: v }));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selected) return;
    setError(null);
    setBusy(true);
    try {
      // /publish/single queues the job and returns immediately. Poll
      // until terminal ('posted' / 'failed') with a 5-minute deadline.
      const initial = await publishSingle({
        domain_id: selected.id,
        language: language || null,
        profile_name: profileName,
        fields: values,
        source_ref: sourceRef ?? null,
      });
      setResult(initial);

      let job = initial;
      const deadline = Date.now() + 5 * 60 * 1000;
      while (job.status === "queued" || job.status === "posting") {
        if (Date.now() > deadline) break;
        await new Promise((r) => setTimeout(r, 1000));
        job = await getPublishJob(initial.id);
        setResult(job);
      }

      if (job.status !== "posted") {
        setError(job.error ?? t("pubMod.publishFailed"));
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("pubMod.publishFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose} size="max-w-2xl">
      <form onSubmit={onSubmit} className="space-y-4">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          {t("pubMod.title")}
        </h2>

        {loadError && (
          <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
            {loadError}
          </div>
        )}

        <TargetPicker
          cmsType={cmsType}
          onCmsTypeChange={onCmsTypeChange}
          domainId={domainId}
          selectedLabel={selectedLabel}
          onDomainPicked={onDomainPicked}
          onPickerResults={onPickerResults}
          selected={selected}
          language={language}
          onLanguageChange={setLanguage}
        />

        {selected?.cms_type === "wordpress" && (
          <WordPressForm
            selected={selected}
            wpProfiles={wpProfiles}
            profileName={profileName}
            onProfileNameChange={setProfileName}
            activeProfile={activeProfile}
            values={values}
            onFieldChange={setField}
          />
        )}

        {selected?.cms_type === "custom" && (
          <CustomCmsForm values={values} onFieldChange={setField} />
        )}

        <ResultPanel error={error} result={result} />

        <div className="flex justify-end gap-2 border-t border-neutral-200 pt-3 dark:border-neutral-800">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            {result?.status === "posted" ? t("common.close") : t("common.cancel")}
          </button>
          {result?.status !== "posted" && (
            <button
              type="submit"
              disabled={busy || !selected || !selected.has_credentials}
              className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900"
            >
              {busy ? t("pubMod.publishing") : t("pubMod.publish")}
            </button>
          )}
        </div>
      </form>
    </Modal>
  );
}
