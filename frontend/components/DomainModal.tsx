"use client";

import { useEffect, useState } from "react";

import { Modal } from "@/components/Modal";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  clearMediaCache,
  createDomain,
  DEFAULT_WP_FIELDS,
  getMediaCacheCount,
  listWpTaxonomies,
  listWpTypes,
  updateDomain,
  type AuthType,
  type CmsType,
  type CustomConfig,
  type Domain,
  type DomainCreatePayload,
  type MultilingualPlugin,
  type PublishConfig,
  type PublishProfile,
  type WpField,
  type WpFieldType,
  type WpTypeInfo,
} from "@/lib/domains";

function defaultProfile(name = "Default"): PublishProfile {
  return {
    name,
    post_type: "posts",
    fields: DEFAULT_WP_FIELDS.map((f) => ({ ...f })),
  };
}

const DEFAULT_CUSTOM_BODY = `{
  "title": "{{title}}",
  "content": "{{content}}",
  "slug": "{{slug}}",
  "language": "{{language}}",
  "status": "{{status}}"
}`;

interface Props {
  domain?: Domain | null;
  onClose: () => void;
  onSaved: (d: Domain) => void;
}

export function DomainModal({ domain, onClose, onSaved }: Props) {
  const { t } = useT();
  const isEdit = !!domain;
  // Flips true the first time any input/select/textarea inside the form fires
  // an onChange (captured by the form-level handler below). Drives the
  // outside-click guard: pristine modal closes immediately, touched modal
  // pops the "discard?" strip. The form is too sprawling to snapshot every
  // field, so first-edit is a good-enough proxy for "user has work to lose".
  const [touched, setTouched] = useState(false);

  const [name, setName] = useState(domain?.name ?? "");
  const [baseUrl, setBaseUrl] = useState(domain?.base_url ?? "");
  const [cmsType, setCmsType] = useState<CmsType>(domain?.cms_type ?? "wordpress");
  const [authType, setAuthType] = useState<AuthType>(
    domain?.auth_type ?? "wp_app_password",
  );
  const [credentials, setCredentials] = useState("");
  // For api_key_header auth_type — credentials JSON {header,value}
  const [apiKeyHeader, setApiKeyHeader] = useState("X-API-Key");
  const [apiKeyValue, setApiKeyValue] = useState("");

  const [languagesText, setLanguagesText] = useState(
    (domain?.languages ?? ["en"]).join(", "),
  );
  const [multilingualPlugin, setMultilingualPlugin] = useState<MultilingualPlugin>(
    domain?.multilingual_plugin ?? "none",
  );

  const [endpointPath, setEndpointPath] = useState(
    domain?.custom_config?.endpoint_path ?? "/api/posts",
  );
  const [bodyTemplateText, setBodyTemplateText] = useState(
    domain?.custom_config?.body_template
      ? JSON.stringify(domain.custom_config.body_template, null, 2)
      : DEFAULT_CUSTOM_BODY,
  );
  const [responseIdPath, setResponseIdPath] = useState(
    domain?.custom_config?.response_id_path ?? "id",
  );
  const [responseUrlPath, setResponseUrlPath] = useState(
    domain?.custom_config?.response_url_path ?? "url",
  );

  // Rate-limit overrides — empty string in the UI means "inherit global default".
  function asText(v: number | null | undefined): string {
    return v == null ? "" : String(v);
  }
  const [rpmText, setRpmText] = useState(asText(domain?.requests_per_minute));
  const [maxConcText, setMaxConcText] = useState(asText(domain?.max_concurrency));
  const [delayText, setDelayText] = useState(asText(domain?.inter_request_delay_ms));
  const [retryText, setRetryText] = useState(asText(domain?.retry_max_attempts));
  const [backoffText, setBackoffText] = useState(asText(domain?.backoff_base_ms));
  const [jitterText, setJitterText] = useState(asText(domain?.backoff_jitter_ms));
  // Tri-state: null = inherit, true/false = override.
  const [respectRetry, setRespectRetry] = useState<boolean | null>(
    domain?.respect_retry_after ?? null,
  );

  // WP introspection (post types + taxonomies). Empty arrays mean either
  // discovery hasn't run yet or the site didn't return useful data; either way
  // the inputs degrade to free-text. Re-runs when an existing WP domain is
  // opened for editing.
  const [wpTypes, setWpTypes] = useState<WpTypeInfo[]>([]);
  const [wpTaxonomies, setWpTaxonomies] = useState<WpTypeInfo[]>([]);
  useEffect(() => {
    if (!isEdit || !domain || domain.cms_type !== "wordpress") return;
    listWpTypes(domain.id).then(setWpTypes).catch(() => undefined);
    listWpTaxonomies(domain.id).then(setWpTaxonomies).catch(() => undefined);
  }, [isEdit, domain]);

  const [mediaCacheCount, setMediaCacheCount] = useState<number | null>(null);
  const [clearingCache, setClearingCache] = useState(false);
  useEffect(() => {
    if (!isEdit || !domain || domain.cms_type !== "wordpress") return;
    getMediaCacheCount(domain.id)
      .then((r) => setMediaCacheCount(r.count))
      .catch(() => undefined);
  }, [isEdit, domain]);

  async function onClearMediaCache() {
    if (!domain) return;
    if (!confirm(t("domainMod.clearCacheConfirm"))) return;
    setClearingCache(true);
    try {
      const r = await clearMediaCache(domain.id);
      setMediaCacheCount(0);
      alert(t("domainMod.clearedCount", { count: r.deleted }));
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("domainMod.clearCacheFailed"));
    } finally {
      setClearingCache(false);
    }
  }

  // WP publish-form constructor state — profiles are independent recipes,
  // each with its own post_type + field list.
  const [profiles, setProfiles] = useState<PublishProfile[]>(() => {
    const seed = domain?.publish_config?.profiles;
    if (seed && seed.length > 0) {
      return seed.map((p) => ({
        name: p.name,
        post_type: p.post_type,
        fields: (p.fields ?? []).map((f) => ({ ...f })),
      }));
    }
    return [defaultProfile()];
  });
  const [activeProfileIdx, setActiveProfileIdx] = useState(0);

  const activeProfile = profiles[activeProfileIdx] ?? profiles[0];
  const activeFields = activeProfile?.fields ?? [];

  function patchActiveProfile(patch: Partial<PublishProfile>) {
    setProfiles((arr) =>
      arr.map((p, i) => (i === activeProfileIdx ? { ...p, ...patch } : p)),
    );
  }

  function patchWpField(idx: number, patch: Partial<WpField>) {
    setProfiles((arr) =>
      arr.map((p, i) =>
        i === activeProfileIdx
          ? {
              ...p,
              fields: p.fields.map((f, j) => (j === idx ? { ...f, ...patch } : f)),
            }
          : p,
      ),
    );
  }
  function removeWpField(idx: number) {
    setProfiles((arr) =>
      arr.map((p, i) =>
        i === activeProfileIdx
          ? { ...p, fields: p.fields.filter((_, j) => j !== idx) }
          : p,
      ),
    );
  }
  function addWpField() {
    setProfiles((arr) =>
      arr.map((p, i) =>
        i === activeProfileIdx
          ? {
              ...p,
              fields: [
                ...p.fields,
                { key: "", label: "", type: "text", is_meta: true, meta_key: "" },
              ],
            }
          : p,
      ),
    );
  }

  function addProfile() {
    setProfiles((arr) => {
      const taken = new Set(arr.map((p) => p.name));
      let n = 1;
      let name = "New profile";
      while (taken.has(name)) {
        n += 1;
        name = `New profile ${n}`;
      }
      return [...arr, defaultProfile(name)];
    });
    // jump to the new profile after the state has settled
    queueMicrotask(() => setActiveProfileIdx((idx) => profiles.length));
  }

  function removeProfile(idx: number) {
    if (profiles.length <= 1) return;
    setProfiles((arr) => arr.filter((_, i) => i !== idx));
    setActiveProfileIdx((cur) => (cur >= idx ? Math.max(0, cur - 1) : cur));
  }

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Snap auth_type valid for the chosen cms_type
    if (cmsType === "wordpress" && authType !== "wp_app_password") {
      setAuthType("wp_app_password");
    }
    if (cmsType === "custom" && authType === "wp_app_password") {
      setAuthType("bearer");
    }
  }, [cmsType, authType]);

  function buildPayload(): DomainCreatePayload | null {
    setError(null);

    const langs = languagesText
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    let creds: string | null = null;
    if (cmsType === "wordpress") {
      creds = credentials.trim() || null;
    } else if (cmsType === "custom") {
      if (authType === "bearer") {
        creds = credentials.trim() || null;
      } else if (authType === "api_key_header") {
        if (apiKeyHeader.trim() && apiKeyValue.trim()) {
          creds = JSON.stringify({
            header: apiKeyHeader.trim(),
            value: apiKeyValue.trim(),
          });
        } else if (apiKeyHeader.trim() || apiKeyValue.trim()) {
          setError(t("domainMod.bothApiKeyRequired"));
          return null;
        }
      }
    }

    let custom_config: CustomConfig | null = null;
    if (cmsType === "custom") {
      let parsedBody: Record<string, unknown> = {};
      try {
        parsedBody = JSON.parse(bodyTemplateText);
        if (typeof parsedBody !== "object" || parsedBody === null || Array.isArray(parsedBody)) {
          throw new Error(t("domainMod.bodyMustBeObject"));
        }
      } catch (e) {
        setError(
          e instanceof Error
            ? t("domainMod.invalidJson", { message: e.message })
            : t("domainMod.invalidJsonGeneric"),
        );
        return null;
      }
      custom_config = {
        endpoint_path: endpointPath.trim(),
        body_template: parsedBody,
        response_id_path: responseIdPath.trim() || null,
        response_url_path: responseUrlPath.trim() || null,
        test_endpoint_path: null,
      };
    }

    let publish_config: PublishConfig | null = null;
    if (cmsType === "wordpress") {
      const cleanedProfiles: PublishProfile[] = [];
      const seenNames = new Set<string>();
      for (const p of profiles) {
        const name = (p.name || "").trim() || "Default";
        if (seenNames.has(name)) {
          setError(t("domainMod.dupeProfile", { name }));
          return null;
        }
        seenNames.add(name);

        const cleanedFields = p.fields
          .map((f) => ({
            ...f,
            key: (f.key || "").trim(),
            label: (f.label || "").trim() || (f.key || "").trim(),
            meta_key: f.meta_key?.trim() || null,
            taxonomy: f.taxonomy?.trim() || null,
            options:
              f.type === "select"
                ? (f.options ?? []).map((o) => o.trim()).filter(Boolean)
                : null,
          }))
          .filter((f) => f.key);
        const dupKeys = cleanedFields
          .map((f) => f.key)
          .filter((k, i, a) => a.indexOf(k) !== i);
        if (dupKeys.length > 0) {
          setError(
            t("domainMod.dupeFieldKeys", { name, keys: [...new Set(dupKeys)].join(", ") }),
          );
          return null;
        }
        cleanedProfiles.push({
          name,
          post_type: (p.post_type || "").trim() || "posts",
          fields: cleanedFields,
        });
      }
      publish_config = { profiles: cleanedProfiles };
    }

    function parseNumOrNull(s: string): number | null {
      const t = s.trim();
      if (!t) return null;
      const n = Number(t);
      if (!Number.isFinite(n) || n < 0) return null;
      return n;
    }

    return {
      name: name.trim(),
      base_url: baseUrl.trim(),
      cms_type: cmsType,
      auth_type: authType,
      credentials: creds,
      languages: langs.length > 0 ? langs : ["en"],
      multilingual_plugin: cmsType === "wordpress" ? multilingualPlugin : "none",
      custom_config,
      publish_config,
      requests_per_minute: parseNumOrNull(rpmText),
      max_concurrency: parseNumOrNull(maxConcText),
      inter_request_delay_ms: parseNumOrNull(delayText),
      retry_max_attempts: parseNumOrNull(retryText),
      backoff_base_ms: parseNumOrNull(backoffText),
      backoff_jitter_ms: parseNumOrNull(jitterText),
      respect_retry_after: respectRetry,
    };
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload = buildPayload();
    if (!payload) return;

    setBusy(true);
    try {
      const saved = isEdit
        ? await updateDomain(domain!.id, payload)
        : await createDomain(payload);
      onSaved(saved);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("users.saveFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose} size="max-w-2xl" dirty={touched}>
      <form
        onSubmit={onSubmit}
        onChange={() => {
          if (!touched) setTouched(true);
        }}
        className="space-y-4"
      >
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          {isEdit ? t("domainMod.editTitle", { name: domain!.name }) : t("domainMod.addTitle")}
        </h2>

        <div className="grid grid-cols-2 gap-3">
          <Field label={t("domainMod.fieldName")}>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              placeholder="Site A"
            />
          </Field>
          <Field label={t("domainMod.fieldBaseUrl")}>
            <input
              required
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              placeholder="https://example.com"
            />
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label={t("domainMod.fieldCmsType")}>
            <select
              value={cmsType}
              onChange={(e) => setCmsType(e.target.value as CmsType)}
              className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              disabled={isEdit}
            >
              <option value="wordpress">{t("domainMod.cmsWordpress")}</option>
              <option value="custom">{t("domainMod.cmsCustom")}</option>
            </select>
          </Field>
          <Field label={t("domainMod.fieldLanguages")}>
            <input
              value={languagesText}
              onChange={(e) => setLanguagesText(e.target.value)}
              className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              placeholder="en, de, fr"
            />
          </Field>
        </div>

        {cmsType === "wordpress" && (
          <>
            <Field label={t("domainMod.fieldMultilingual")}>
              <select
                value={multilingualPlugin}
                onChange={(e) => setMultilingualPlugin(e.target.value as MultilingualPlugin)}
                className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              >
                <option value="none">{t("domainMod.pluginNone")}</option>
                <option value="polylang">{t("domainMod.pluginPolylang")}</option>
                <option value="wpml">{t("domainMod.pluginWpml")}</option>
              </select>
            </Field>
            <Field
              label={t("domainMod.fieldAppPassword")}
              hint={
                isEdit && domain?.has_credentials
                  ? t("domainMod.appPasswordHintEdit")
                  : undefined
              }
            >
              <input
                value={credentials}
                onChange={(e) => setCredentials(e.target.value)}
                className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm font-mono dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                placeholder="admin:abcd efgh ijkl mnop"
                autoComplete="off"
              />
            </Field>

            <div className="border-t border-neutral-200 pt-3 dark:border-neutral-800">
              <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
                {t("domainMod.publishForm")}
              </h3>
              <p className="mb-2 text-xs text-neutral-500 dark:text-neutral-400">
                {t("domainMod.publishFormHint")}
              </p>

              {/* Profile tabs */}
              <div className="mb-3 flex flex-wrap items-center gap-1 border-b border-neutral-200 dark:border-neutral-800">
                {profiles.map((p, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setActiveProfileIdx(i)}
                    className={
                      "-mb-px border-b-2 px-3 py-1.5 text-xs font-medium transition-colors " +
                      (i === activeProfileIdx
                        ? "border-neutral-900 text-neutral-900 dark:border-neutral-100 dark:text-neutral-100"
                        : "border-transparent text-neutral-500 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100")
                    }
                  >
                    {p.name || t("domainMod.unnamed")}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={addProfile}
                  className="ml-1 rounded-md border border-dashed border-neutral-300 px-2 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
                >
                  {t("domainMod.addProfile")}
                </button>
              </div>

              {/* Active profile editor */}
              {activeProfile && (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label={t("domainMod.fieldProfileName")}>
                      <input
                        value={activeProfile.name}
                        onChange={(e) => patchActiveProfile({ name: e.target.value })}
                        className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                        placeholder="Standard post"
                      />
                    </Field>
                    <Field
                      label={t("domainMod.fieldPostType")}
                      hint={
                        wpTypes.length > 0
                          ? t("domainMod.discoveredTypes", { count: wpTypes.length })
                          : isEdit
                            ? t("domainMod.discoveryFailed")
                            : undefined
                      }
                    >
                      <input
                        value={activeProfile.post_type}
                        onChange={(e) =>
                          patchActiveProfile({ post_type: e.target.value })
                        }
                        list={isEdit && wpTypes.length > 0 ? "wp-types-list" : undefined}
                        className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm font-mono dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                        placeholder="posts"
                      />
                      {isEdit && wpTypes.length > 0 && (
                        <datalist id="wp-types-list">
                          {wpTypes.map((t) => (
                            <option key={t.slug} value={t.slug}>
                              {t.name}
                            </option>
                          ))}
                        </datalist>
                      )}
                    </Field>
                  </div>

                  {profiles.length > 1 && (
                    <div className="mt-2">
                      <button
                        type="button"
                        onClick={() => removeProfile(activeProfileIdx)}
                        className="text-xs text-red-600 hover:underline dark:text-red-400"
                      >
                        {t("domainMod.deleteProfile")}
                      </button>
                    </div>
                  )}
                </>
              )}

              <div className="mt-3 space-y-2">
                {activeFields.map((f, idx) => (
                  <div
                    key={idx}
                    className="rounded-md border border-neutral-200 bg-neutral-50 p-2 dark:border-neutral-800 dark:bg-neutral-950"
                  >
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <input
                        value={f.key}
                        onChange={(e) => patchWpField(idx, { key: e.target.value })}
                        placeholder={t("domainMod.fieldKey")}
                        className="min-w-[120px] flex-1 rounded-md border border-neutral-300 bg-white px-2 py-1 font-mono dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                      />
                      <input
                        value={f.label}
                        onChange={(e) => patchWpField(idx, { label: e.target.value })}
                        placeholder={t("domainMod.fieldLabel")}
                        className="min-w-[120px] flex-1 rounded-md border border-neutral-300 bg-white px-2 py-1 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                      />
                      <select
                        value={f.type}
                        onChange={(e) => patchWpField(idx, { type: e.target.value as WpFieldType })}
                        className="min-w-[140px] shrink-0 rounded-md border border-neutral-300 bg-white px-2 py-1 pr-7 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                      >
                        <option value="text">{t("domainMod.typeText")}</option>
                        <option value="textarea">{t("domainMod.typeTextarea")}</option>
                        <option value="select">{t("domainMod.typeSelect")}</option>
                        <option value="taxonomy_ids">{t("domainMod.typeTaxonomy")}</option>
                        <option value="media_url">{t("domainMod.typeMedia")}</option>
                      </select>
                      <label className="flex shrink-0 items-center gap-1 whitespace-nowrap text-neutral-700 dark:text-neutral-300">
                        <input
                          type="checkbox"
                          checked={!!f.required}
                          onChange={(e) => patchWpField(idx, { required: e.target.checked })}
                        />
                        {t("domainMod.required")}
                      </label>
                      <label className="flex shrink-0 items-center gap-1 whitespace-nowrap text-neutral-700 dark:text-neutral-300">
                        <input
                          type="checkbox"
                          checked={!!f.is_meta}
                          onChange={(e) => patchWpField(idx, { is_meta: e.target.checked })}
                        />
                        {t("domainMod.meta")}
                      </label>
                      <button
                        type="button"
                        onClick={() => removeWpField(idx)}
                        aria-label={t("domainMod.removeField")}
                        title={t("domainMod.removeField")}
                        className="ml-auto shrink-0 rounded-md px-2 py-1 text-neutral-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40 dark:hover:text-red-400"
                      >
                        ×
                      </button>
                    </div>

                    {f.is_meta && (
                      <input
                        value={f.meta_key ?? ""}
                        onChange={(e) => patchWpField(idx, { meta_key: e.target.value })}
                        placeholder={t("domainMod.metaKeyPlaceholder")}
                        className="mt-2 block w-full rounded-md border border-neutral-300 bg-white px-2 py-1 text-xs font-mono dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                      />
                    )}
                    {f.type === "select" && (
                      <input
                        value={(f.options ?? []).join(", ")}
                        onChange={(e) =>
                          patchWpField(idx, {
                            options: e.target.value
                              .split(",")
                              .map((s) => s.trim())
                              .filter(Boolean),
                          })
                        }
                        placeholder={t("domainMod.optionsPlaceholder")}
                        className="mt-2 block w-full rounded-md border border-neutral-300 bg-white px-2 py-1 text-xs font-mono dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                      />
                    )}
                    {f.type === "taxonomy_ids" && (
                      <>
                        <input
                          value={f.taxonomy ?? ""}
                          onChange={(e) => patchWpField(idx, { taxonomy: e.target.value })}
                          placeholder={t("domainMod.taxonomyPlaceholder")}
                          list={isEdit && wpTaxonomies.length > 0 ? "wp-taxonomies-list" : undefined}
                          className="mt-2 block w-full rounded-md border border-neutral-300 bg-white px-2 py-1 text-xs font-mono dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                        />
                        {isEdit && wpTaxonomies.length > 0 && (
                          <datalist id="wp-taxonomies-list">
                            {wpTaxonomies.map((t) => (
                              <option key={t.slug} value={t.slug}>
                                {t.name}
                              </option>
                            ))}
                          </datalist>
                        )}
                      </>
                    )}
                  </div>
                ))}
                <button
                  type="button"
                  onClick={addWpField}
                  className="rounded-md border border-dashed border-neutral-300 px-3 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
                >
                  {t("domainMod.addField")}
                </button>
              </div>
            </div>
          </>
        )}

        {cmsType === "custom" && (
          <>
            <Field label={t("domainMod.fieldAuthType")}>
              <select
                value={authType}
                onChange={(e) => setAuthType(e.target.value as AuthType)}
                className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              >
                <option value="bearer">{t("domainMod.authBearer")}</option>
                <option value="api_key_header">{t("domainMod.authApiKey")}</option>
              </select>
            </Field>

            {authType === "bearer" && (
              <Field
                label={t("domainMod.fieldBearerToken")}
                hint={
                  isEdit && domain?.has_credentials
                    ? t("domainMod.bearerHintEdit")
                    : undefined
                }
              >
                <input
                  value={credentials}
                  onChange={(e) => setCredentials(e.target.value)}
                  className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm font-mono dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                  placeholder={t("domainMod.bearerPlaceholder")}
                  autoComplete="off"
                />
              </Field>
            )}

            {authType === "api_key_header" && (
              <div className="grid grid-cols-2 gap-3">
                <Field label={t("domainMod.fieldHeaderName")}>
                  <input
                    value={apiKeyHeader}
                    onChange={(e) => setApiKeyHeader(e.target.value)}
                    className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm font-mono dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                    placeholder="X-API-Key"
                  />
                </Field>
                <Field
                  label={t("domainMod.fieldHeaderValue")}
                  hint={
                    isEdit && domain?.has_credentials
                      ? t("domainMod.headerValueHintEdit")
                      : undefined
                  }
                >
                  <input
                    value={apiKeyValue}
                    onChange={(e) => setApiKeyValue(e.target.value)}
                    className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm font-mono dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                    placeholder={t("domainMod.headerValuePlaceholder")}
                    autoComplete="off"
                  />
                </Field>
              </div>
            )}

            <Field label={t("domainMod.fieldEndpointPath")}>
              <input
                value={endpointPath}
                onChange={(e) => setEndpointPath(e.target.value)}
                className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm font-mono dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                placeholder="/api/posts"
              />
            </Field>

            <Field label={t("domainMod.fieldBodyTemplate")}>
              <textarea
                value={bodyTemplateText}
                onChange={(e) => setBodyTemplateText(e.target.value)}
                rows={8}
                className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm font-mono dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                spellCheck={false}
              />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label={t("domainMod.fieldResponseIdPath")}>
                <input
                  value={responseIdPath}
                  onChange={(e) => setResponseIdPath(e.target.value)}
                  className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm font-mono dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                  placeholder="id"
                />
              </Field>
              <Field label={t("domainMod.fieldResponseUrlPath")}>
                <input
                  value={responseUrlPath}
                  onChange={(e) => setResponseUrlPath(e.target.value)}
                  className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm font-mono dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                  placeholder="url"
                />
              </Field>
            </div>
          </>
        )}

        {/* Rate limits (per-domain overrides). Empty = inherit global default. */}
        <div className="border-t border-neutral-200 pt-3 dark:border-neutral-800">
          <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
            {t("domainMod.rateLimits")}
          </h3>
          <p className="mb-2 text-xs text-neutral-500 dark:text-neutral-400">
            {t("domainMod.rateLimitsHint")}
          </p>
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("domainMod.rateRpm")}>
              <input
                type="number"
                min={0}
                value={rpmText}
                onChange={(e) => setRpmText(e.target.value)}
                placeholder={t("domainMod.inheritPlaceholder")}
                className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              />
            </Field>
            <Field label={t("domainMod.rateMaxConc")}>
              <input
                type="number"
                min={0}
                value={maxConcText}
                onChange={(e) => setMaxConcText(e.target.value)}
                placeholder={t("domainMod.inheritPlaceholder")}
                className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              />
            </Field>
            <Field label={t("domainMod.rateDelay")}>
              <input
                type="number"
                min={0}
                value={delayText}
                onChange={(e) => setDelayText(e.target.value)}
                placeholder={t("domainMod.inheritPlaceholder")}
                className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              />
            </Field>
            <Field label={t("domainMod.rateRetry")}>
              <input
                type="number"
                min={0}
                value={retryText}
                onChange={(e) => setRetryText(e.target.value)}
                placeholder={t("domainMod.inheritPlaceholder")}
                className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              />
            </Field>
            <Field label={t("domainMod.rateBackoff")}>
              <input
                type="number"
                min={0}
                value={backoffText}
                onChange={(e) => setBackoffText(e.target.value)}
                placeholder={t("domainMod.inheritPlaceholder")}
                className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              />
            </Field>
            <Field label={t("domainMod.rateJitter")}>
              <input
                type="number"
                min={0}
                value={jitterText}
                onChange={(e) => setJitterText(e.target.value)}
                placeholder={t("domainMod.inheritPlaceholder")}
                className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              />
            </Field>
          </div>
          <div className="mt-2">
            <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
              {t("domainMod.respectRetryAfter")}
            </span>
            <select
              value={respectRetry === null ? "" : respectRetry ? "yes" : "no"}
              onChange={(e) => {
                const v = e.target.value;
                setRespectRetry(v === "" ? null : v === "yes");
              }}
              className="block rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            >
              <option value="">{t("domainMod.inheritOption")}</option>
              <option value="yes">{t("domainMod.optYes")}</option>
              <option value="no">{t("domainMod.optNo")}</option>
            </select>
          </div>
        </div>

        {/* Media-upload cache (WP only) */}
        {isEdit && cmsType === "wordpress" && (
          <div className="border-t border-neutral-200 pt-3 dark:border-neutral-800">
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
              {t("domainMod.mediaCache")}
            </h3>
            <p className="mb-2 text-xs text-neutral-500 dark:text-neutral-400">
              {t("domainMod.mediaCacheHint")}
            </p>
            <div className="flex items-center gap-3 text-xs">
              <span className="text-neutral-700 dark:text-neutral-300">
                {t("domainMod.cachedEntries")}{" "}
                <b>{mediaCacheCount === null ? "…" : mediaCacheCount}</b>
              </span>
              <button
                type="button"
                onClick={onClearMediaCache}
                disabled={clearingCache || (mediaCacheCount ?? 0) === 0}
                className="rounded-md border border-neutral-300 px-2.5 py-1 font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
              >
                {clearingCache ? t("domainMod.clearing") : t("domainMod.clearCache")}
              </button>
            </div>
          </div>
        )}

        {error && (
          <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2 border-t border-neutral-200 pt-3 dark:border-neutral-800">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            {t("common.cancel")}
          </button>
          <button
            type="submit"
            disabled={busy}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900"
          >
            {busy ? t("common.saving") : isEdit ? t("common.save") : t("domains.add")}
          </button>
        </div>
      </form>
    </Modal>
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
