"use client";

import { FormEvent, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import { testProviderConnection, updateProvider } from "@/lib/settings";
import type { ConnectionTestResult, Provider, ProviderUpdate } from "@/lib/types";

interface FormState {
  enabled: boolean;
  default_model: string;
  prompt_creation_model: string;
  available_models: string; // newline-separated in the textarea
  requests_per_minute: number;
  max_concurrency: number;
  batch_size: number;
  inter_request_delay_ms: number;
  retry_max_attempts: number;
  backoff_base_ms: number;
  backoff_jitter_ms: number;
  respect_retry_after: boolean;
}

// Vertex AI–only state (kept separate from FormState so the rest of the
// settings card stays generic across providers).
interface VertexFormState {
  project_id: string;
  location: string;
  service_account_json: string; // textarea input; never round-trips from server
}

function toFormState(p: Provider): FormState {
  return {
    enabled: p.enabled,
    default_model: p.default_model ?? "",
    prompt_creation_model: p.prompt_creation_model ?? "",
    available_models: p.available_models.join("\n"),
    requests_per_minute: p.requests_per_minute,
    max_concurrency: p.max_concurrency,
    batch_size: p.batch_size,
    inter_request_delay_ms: p.inter_request_delay_ms,
    retry_max_attempts: p.retry_max_attempts,
    backoff_base_ms: p.backoff_base_ms,
    backoff_jitter_ms: p.backoff_jitter_ms,
    respect_retry_after: p.respect_retry_after,
  };
}

export function ProviderCard({
  provider,
  onUpdated,
}: {
  provider: Provider;
  onUpdated: (next: Provider) => void;
}) {
  const { t } = useT();
  const [form, setForm] = useState<FormState>(toFormState(provider));
  const [apiKeyInput, setApiKeyInput] = useState("");
  const isVertex = provider.code === "vertex";
  const [vertex, setVertex] = useState<VertexFormState>({
    project_id: provider.extra_config_public?.project_id ?? "",
    location: provider.extra_config_public?.location ?? "",
    service_account_json: "",
  });
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const patch: ProviderUpdate = {
        enabled: form.enabled,
        default_model: form.default_model.trim() || null,
        prompt_creation_model: form.prompt_creation_model.trim() || null,
        available_models: form.available_models
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
        requests_per_minute: form.requests_per_minute,
        max_concurrency: form.max_concurrency,
        batch_size: form.batch_size,
        inter_request_delay_ms: form.inter_request_delay_ms,
        retry_max_attempts: form.retry_max_attempts,
        backoff_base_ms: form.backoff_base_ms,
        backoff_jitter_ms: form.backoff_jitter_ms,
        respect_retry_after: form.respect_retry_after,
      };
      // Only include api_key if the user actually typed something or chose to clear.
      // Empty input = "no change". Use the dedicated Clear button to remove.
      if (apiKeyInput.trim()) patch.api_key = apiKeyInput.trim();

      // Vertex AI extras: only send the keys that actually changed. The
      // textarea for service_account_json starts empty on every render and
      // only sends when the user typed a new value — same convention as
      // apiKeyInput, so re-saving the form doesn't wipe a stored SA JSON.
      if (isVertex) {
        const extraPatch: Record<string, string> = {};
        const pubProject = provider.extra_config_public?.project_id ?? "";
        const pubLocation = provider.extra_config_public?.location ?? "";
        if (vertex.project_id !== pubProject) extraPatch.project_id = vertex.project_id.trim();
        if (vertex.location !== pubLocation) extraPatch.location = vertex.location.trim();
        if (vertex.service_account_json.trim()) {
          extraPatch.service_account_json = vertex.service_account_json.trim();
        }
        if (Object.keys(extraPatch).length > 0) patch.extra_config = extraPatch;
      }

      const next = await updateProvider(provider.code, patch);
      onUpdated(next);
      setForm(toFormState(next));
      setApiKeyInput("");
      if (isVertex) {
        setVertex({
          project_id: next.extra_config_public?.project_id ?? "",
          location: next.extra_config_public?.location ?? "",
          service_account_json: "",
        });
      }
      setSavedAt(Date.now());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("settings.saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  async function onClearVertexExtras() {
    if (!confirm(t("settings.vertexConfirmClear"))) return;
    setSaving(true);
    setError(null);
    try {
      const next = await updateProvider(provider.code, { extra_config: {} });
      onUpdated(next);
      setVertex({ project_id: "", location: "", service_account_json: "" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("settings.clearKeyFailed"));
    } finally {
      setSaving(false);
    }
  }

  async function onClearApiKey() {
    if (!confirm(t("settings.confirmClearKey", { provider: provider.display_name }))) return;
    setSaving(true);
    setError(null);
    try {
      const next = await updateProvider(provider.code, { api_key: "" });
      onUpdated(next);
      setApiKeyInput("");
      setTestResult(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("settings.clearKeyFailed"));
    } finally {
      setSaving(false);
    }
  }

  async function onTest() {
    setTesting(true);
    setTestResult(null);
    try {
      const r = await testProviderConnection(provider.code, {
        api_key: apiKeyInput.trim() || undefined,
        model: form.default_model.trim() || undefined,
      });
      setTestResult(r);
    } catch (err) {
      setTestResult({
        ok: false,
        provider_code: provider.code,
        model_used: null,
        latency_ms: null,
        sample_output: null,
        error: err instanceof ApiError ? err.message : t("settings.testRequestFailed"),
      });
    } finally {
      setTesting(false);
    }
  }

  return (
    <form
      onSubmit={onSave}
      className="rounded-lg border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-6 shadow-sm"
    >
      <header className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
            {provider.display_name}
          </h2>
          <p className="font-mono text-xs text-neutral-500 dark:text-neutral-400">{provider.code}</p>
        </div>
        <label className="flex shrink-0 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(e) => set("enabled", e.target.checked)}
            className="h-4 w-4"
          />
          <span className="font-medium">{t("settings.enabled")}</span>
        </label>
      </header>

      {/* API key */}
      <div className="mt-5">
        <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
          {t("settings.apiKey")}
          <input
            type="password"
            placeholder={
              provider.has_api_key
                ? t("settings.apiKeyPlaceholderSet")
                : t("settings.apiKeyPlaceholderUnset")
            }
            value={apiKeyInput}
            onChange={(e) => setApiKeyInput(e.target.value)}
            autoComplete="off"
            className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500"
          />
        </label>
        <div className="mt-1 flex items-center justify-between text-xs">
          <span className="text-neutral-500 dark:text-neutral-400">
            {provider.has_api_key
              ? t("settings.apiKeyStored")
              : t("settings.apiKeyEmpty")}
          </span>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onTest}
              disabled={testing || (!apiKeyInput.trim() && !provider.has_api_key)}
              className="font-medium text-neutral-700 hover:underline disabled:opacity-40 dark:text-neutral-300"
              title={
                apiKeyInput.trim()
                  ? t("settings.testHintTyped")
                  : provider.has_api_key
                    ? t("settings.testHintSaved")
                    : t("settings.testHintNeedKey")
              }
            >
              {testing ? t("settings.testing") : t("settings.testConnection")}
            </button>
            {provider.has_api_key && (
              <button
                type="button"
                onClick={onClearApiKey}
                className="text-red-600 dark:text-red-400 hover:underline"
              >
                {t("settings.clearKey")}
              </button>
            )}
          </div>
        </div>

        {testResult && (
          <div
            className={
              "mt-2 rounded-md px-3 py-2 text-xs " +
              (testResult.ok
                ? "bg-green-50 text-green-800 dark:bg-green-950/40 dark:text-green-300"
                : "bg-red-50 text-red-700 dark:bg-red-950/50 dark:text-red-300")
            }
          >
            {testResult.ok ? (
              <div>
                <p className="font-medium">
                  {t("settings.connectionOk")}
                  {testResult.latency_ms != null && (
                    <span className="ml-2 font-normal opacity-70">
                      {testResult.latency_ms} ms · {testResult.model_used}
                    </span>
                  )}
                </p>
                {testResult.sample_output && (
                  <p className="mt-1 truncate font-mono opacity-80">
                    {t("settings.reply", { text: testResult.sample_output })}
                  </p>
                )}
              </div>
            ) : (
              <div>
                <p className="font-medium">{t("settings.connectionFailed")}</p>
                <p className="mt-0.5 break-words opacity-90">{testResult.error}</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Vertex-specific extras: project_id + location + SA JSON */}
      {isVertex && (
        <div className="mt-5 rounded-md border border-neutral-200 bg-neutral-50 p-4 dark:border-neutral-800 dark:bg-neutral-900/40">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
                {t("settings.vertexAuthHeader")}
              </h3>
              <p className="mt-1 text-xs text-neutral-600 dark:text-neutral-400">
                {t("settings.vertexAuthHint")}
              </p>
            </div>
            {provider.has_extra_config && (
              <button
                type="button"
                onClick={onClearVertexExtras}
                className="shrink-0 text-xs font-medium text-red-600 hover:underline dark:text-red-400"
              >
                {t("settings.vertexClear")}
              </button>
            )}
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
              {t("settings.vertexProjectId")}
              <input
                type="text"
                value={vertex.project_id}
                onChange={(e) => setVertex((v) => ({ ...v, project_id: e.target.value }))}
                placeholder="my-gcp-project-123"
                className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
              />
            </label>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
              {t("settings.vertexLocation")}
              <input
                type="text"
                value={vertex.location}
                onChange={(e) => setVertex((v) => ({ ...v, location: e.target.value }))}
                placeholder="us-central1"
                className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
              />
            </label>
          </div>
          <label className="mt-3 block text-sm font-medium text-neutral-700 dark:text-neutral-300">
            {t("settings.vertexSaJson")}
            <textarea
              rows={5}
              value={vertex.service_account_json}
              onChange={(e) =>
                setVertex((v) => ({ ...v, service_account_json: e.target.value }))
              }
              placeholder={
                provider.has_extra_config
                  ? t("settings.vertexSaJsonStored")
                  : t("settings.vertexSaJsonPlaceholder")
              }
              autoComplete="off"
              spellCheck={false}
              className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 font-mono text-xs focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
            />
          </label>
          <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            {provider.has_extra_config
              ? t("settings.vertexSaJsonHelperStored")
              : t("settings.vertexSaJsonHelperEmpty")}
          </p>
        </div>
      )}

      {/* Models */}
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
          {t("settings.defaultModel")}
          <input
            type="text"
            value={form.default_model}
            onChange={(e) => set("default_model", e.target.value)}
            placeholder="e.g. gemini-2.5-flash"
            className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500"
          />
        </label>
        <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
          {t("settings.modelForAi")}
          <input
            type="text"
            value={form.prompt_creation_model}
            onChange={(e) => set("prompt_creation_model", e.target.value)}
            placeholder="e.g. gemini-2.5-pro"
            className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500"
          />
        </label>
      </div>

      <label className="mt-4 block text-sm font-medium text-neutral-700 dark:text-neutral-300">
        {t("settings.availableModels")}
        <textarea
          rows={4}
          value={form.available_models}
          onChange={(e) => set("available_models", e.target.value)}
          className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 px-3 py-2 font-mono text-xs focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500"
        />
      </label>

      {/* Advanced: rate limits */}
      <div className="mt-5">
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:underline"
        >
          {showAdvanced ? t("settings.hideRateLimits") : t("settings.showRateLimits")}
        </button>

        {showAdvanced && (
          <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <NumberField
              label={t("settings.rpm")}
              value={form.requests_per_minute}
              onChange={(v) => set("requests_per_minute", v)}
              min={1}
            />
            <NumberField
              label={t("settings.maxConcurrency")}
              value={form.max_concurrency}
              onChange={(v) => set("max_concurrency", v)}
              min={1}
            />
            <NumberField
              label={t("settings.batchSize")}
              value={form.batch_size}
              onChange={(v) => set("batch_size", v)}
              min={1}
            />
            <NumberField
              label={t("settings.delayMs")}
              value={form.inter_request_delay_ms}
              onChange={(v) => set("inter_request_delay_ms", v)}
              min={0}
            />
            <NumberField
              label={t("settings.retryMax")}
              value={form.retry_max_attempts}
              onChange={(v) => set("retry_max_attempts", v)}
              min={0}
            />
            <NumberField
              label={t("settings.backoffBase")}
              value={form.backoff_base_ms}
              onChange={(v) => set("backoff_base_ms", v)}
              min={0}
            />
            <NumberField
              label={t("settings.backoffJitter")}
              value={form.backoff_jitter_ms}
              onChange={(v) => set("backoff_jitter_ms", v)}
              min={0}
            />
            <label className="flex items-end gap-2 text-sm font-medium text-neutral-700 dark:text-neutral-300">
              <input
                type="checkbox"
                checked={form.respect_retry_after}
                onChange={(e) => set("respect_retry_after", e.target.checked)}
                className="mb-2 h-4 w-4"
              />
              <span className="mb-2">{t("settings.respectRetryAfter")}</span>
            </label>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="mt-6 flex items-center justify-between border-t border-neutral-200 dark:border-neutral-800 pt-4">
        <div className="text-sm">
          {error && <span className="text-red-600 dark:text-red-400">{error}</span>}
          {!error && savedAt && (
            <span className="text-green-600 dark:text-green-400">{t("common.savedDot")}</span>
          )}
        </div>
        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 dark:hover:bg-neutral-200 disabled:opacity-60"
        >
          {saving ? t("common.saving") : t("common.save")}
        </button>
      </div>
    </form>
  );
}

function NumberField({
  label,
  value,
  onChange,
  min,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
  min?: number;
}) {
  return (
    <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
      {label}
      <input
        type="number"
        value={value}
        min={min}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500"
      />
    </label>
  );
}
