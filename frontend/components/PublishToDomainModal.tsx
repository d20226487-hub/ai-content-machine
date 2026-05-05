"use client";

import { useEffect, useMemo, useState } from "react";

import { Modal } from "@/components/Modal";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  DEFAULT_WP_FIELDS,
  listDomains,
  type Domain,
  type PublishProfile,
  type WpField,
} from "@/lib/domains";

function profilesOf(d: Domain): PublishProfile[] {
  const saved = d.publish_config?.profiles;
  if (saved && saved.length > 0) return saved;
  // Domain has no profiles configured — fall back to a single Default profile
  // with the standard WP field set so legacy domains still work.
  return [{ name: "Default", post_type: "posts", fields: DEFAULT_WP_FIELDS }];
}
import { getPublishJob, publishSingle, type PublishJobDetail } from "@/lib/publish";

interface Props {
  initialTitle?: string;
  initialContent: string;
  initialSlugSuggestion?: string;
  sourceRef?: Record<string, unknown> | null;
  onClose: () => void;
}

export function PublishToDomainModal({
  initialTitle,
  initialContent,
  initialSlugSuggestion,
  sourceRef,
  onClose,
}: Props) {
  const { t } = useT();
  const [domains, setDomains] = useState<Domain[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [domainId, setDomainId] = useState<number | null>(null);
  const [profileName, setProfileName] = useState<string | null>(null);
  const [language, setLanguage] = useState<string | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PublishJobDetail | null>(null);

  useEffect(() => {
    listDomains()
      .then((list) => {
        setDomains(list);
        // Pre-select first domain that has credentials.
        const first = list.find((d) => d.has_credentials) ?? list[0];
        if (first) setDomainId(first.id);
      })
      .catch((err) =>
        setLoadError(err instanceof ApiError ? err.message : t("pubMod.failedLoadDomains")),
      );
  }, [t]);

  const selected = useMemo(
    () => (domainId != null ? domains?.find((d) => d.id === domainId) ?? null : null),
    [domainId, domains],
  );

  const wpProfiles: PublishProfile[] = useMemo(
    () => (selected?.cms_type === "wordpress" ? profilesOf(selected) : []),
    [selected],
  );
  const activeProfile: PublishProfile | null = useMemo(() => {
    if (selected?.cms_type !== "wordpress") return null;
    if (wpProfiles.length === 0) return null;
    return (
      wpProfiles.find((p) => p.name === profileName) ?? wpProfiles[0]
    );
  }, [selected, wpProfiles, profileName]);

  // When the picked domain changes, default the profile to the first one.
  useEffect(() => {
    if (selected?.cms_type === "wordpress" && wpProfiles.length > 0) {
      setProfileName((cur) =>
        cur && wpProfiles.some((p) => p.name === cur) ? cur : wpProfiles[0].name,
      );
    } else {
      setProfileName(null);
    }
  }, [selected, wpProfiles]);

  // When the picked domain or profile changes, seed the form values.
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
        else if (f.key === "slug" && initialSlugSuggestion) next[f.key] = initialSlugSuggestion;
        else if (f.key === "status") next[f.key] = (f.options ?? ["publish"])[0] ?? "publish";
        else next[f.key] = "";
      }
    } else if (selected.cms_type === "custom") {
      const placeholders = collectPlaceholders(selected.custom_config?.body_template);
      for (const ph of placeholders) {
        if (ph === "title" && initialTitle) next[ph] = initialTitle;
        else if (ph === "content") next[ph] = initialContent;
        else if (ph === "slug" && initialSlugSuggestion) next[ph] = initialSlugSuggestion;
        else if (ph === "language") continue; // language is sent separately
        else next[ph] = "";
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
      // The endpoint now queues the publish and returns immediately with a
      // job in 'queued' / 'posting' state. Poll until it reaches a terminal
      // state ('posted' / 'failed').
      const initial = await publishSingle({
        domain_id: selected.id,
        language: language || null,
        profile_name: profileName,
        fields: values,
        source_ref: sourceRef ?? null,
      });
      setResult(initial);

      let job = initial;
      const deadline = Date.now() + 5 * 60 * 1000; // 5-min cap
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

  const langOptions = selected?.languages ?? [];
  const showLangPicker = langOptions.length > 1;

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

        {domains !== null && domains.length === 0 && (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            {t("pubMod.noneConnected")}
          </p>
        )}

        {domains && domains.length > 0 && (
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("pubMod.fieldDomain")}>
              <select
                value={domainId ?? ""}
                onChange={(e) => setDomainId(Number(e.target.value))}
                className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              >
                {domains.map((d) => (
                  <option key={d.id} value={d.id} disabled={!d.has_credentials}>
                    {d.name} ({d.cms_type}){!d.has_credentials ? t("pubMod.noCreds") : ""}
                  </option>
                ))}
              </select>
            </Field>
            {showLangPicker && (
              <Field label={t("pubMod.fieldLanguage")}>
                <select
                  value={language ?? ""}
                  onChange={(e) => setLanguage(e.target.value)}
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
        )}

        {selected && selected.cms_type === "wordpress" && (
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
                  onChange={(e) => setProfileName(e.target.value)}
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
                onChange={(v) => setField(f.key, v)}
              />
            ))}
          </div>
        )}

        {selected && selected.cms_type === "custom" && (
          <div className="space-y-3 border-t border-neutral-200 pt-3 dark:border-neutral-800">
            {Object.keys(values).map((key) => (
              <Field key={key} label={key}>
                {key === "content" ? (
                  <textarea
                    value={values[key]}
                    onChange={(e) => setField(key, e.target.value)}
                    rows={8}
                    className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm font-mono dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                  />
                ) : (
                  <input
                    value={values[key]}
                    onChange={(e) => setField(key, e.target.value)}
                    className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                  />
                )}
              </Field>
            ))}
          </div>
        )}

        {error && (
          <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
            {error}
          </div>
        )}

        {result && result.status === "posted" && (
          <div className="rounded-md bg-green-50 px-3 py-2 text-sm text-green-800 dark:bg-green-950/40 dark:text-green-300">
            {t("pubMod.published")}
            {result.cms_post_url && (
              <>
                {" "}
                <a
                  href={result.cms_post_url}
                  target="_blank"
                  rel="noreferrer"
                  className="underline"
                >
                  {t("pubMod.viewPost")}
                </a>
              </>
            )}
          </div>
        )}

        {result?.warnings && result.warnings.length > 0 && (
          <div className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
            <p className="font-medium">{t("pubMod.warnings")}</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs">
              {result.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        )}

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

function Field({
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

const PLACEHOLDER_RE = /\{\{\s*([A-Za-z_][\w\.\- ]*?)\s*\}\}/g;

function collectPlaceholders(node: unknown, out: Set<string> = new Set()): string[] {
  if (typeof node === "string") {
    let m: RegExpExecArray | null;
    while ((m = PLACEHOLDER_RE.exec(node)) !== null) {
      out.add(m[1].trim());
    }
  } else if (Array.isArray(node)) {
    node.forEach((x) => collectPlaceholders(x, out));
  } else if (node && typeof node === "object") {
    Object.values(node as Record<string, unknown>).forEach((v) =>
      collectPlaceholders(v, out),
    );
  }
  return Array.from(out);
}
