"use client";

import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import {
  getAutotoolConfig,
  saveAutotoolConfig,
  testAutotoolConfig,
  type AutotoolConfigUpdate,
  type AutotoolTestResult,
} from "@/lib/autotool";
import { useT } from "@/lib/i18n-context";

/**
 * Autotool connection config (X-Api-Key + target ImportPosts URL). Admin-only —
 * lives on the Settings page. Managers use the /publish/autotool shared-tables
 * page to publish, but can't see or change these credentials.
 */
export function AutotoolConfigCard() {
  const { t } = useT();

  const [targetUrl, setTargetUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [keyConfigured, setKeyConfigured] = useState(false);
  const [clearKey, setClearKey] = useState(false);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<AutotoolTestResult | null>(null);

  useEffect(() => {
    getAutotoolConfig()
      .then((c) => {
        setTargetUrl(c.target_url ?? "");
        setKeyConfigured(c.api_key_configured);
      })
      .catch((e) =>
        setLoadError(e instanceof ApiError ? e.message : t("common.failedToLoad")),
      )
      .finally(() => setLoading(false));
  }, [t]);

  async function save() {
    setSaving(true);
    setSaveError(null);
    const payload: AutotoolConfigUpdate = { target_url: targetUrl.trim() };
    if (clearKey) payload.api_key = "";
    else if (apiKey) payload.api_key = apiKey;
    try {
      const c = await saveAutotoolConfig(payload);
      setTargetUrl(c.target_url ?? "");
      setKeyConfigured(c.api_key_configured);
      setApiKey("");
      setClearKey(false);
      setSavedAt(Date.now());
      // A config change can invalidate the previous test outcome.
      setTestResult(null);
    } catch (e) {
      setSaveError(
        e instanceof ApiError ? e.message : t("common.somethingWentWrong"),
      );
    } finally {
      setSaving(false);
    }
  }

  async function test() {
    setTesting(true);
    setTestResult(null);
    try {
      setTestResult(await testAutotoolConfig());
    } catch (e) {
      setTestResult({
        ok: false,
        status_code: null,
        elapsed_ms: null,
        detail: e instanceof ApiError ? e.message : t("common.somethingWentWrong"),
      });
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-900">
      <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
        {t("autotoolCfg.title")}
      </h2>
      <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
        {t("autotoolCfg.subtitle")}
      </p>

      {loading ? (
        <p className="mt-4 text-sm text-neutral-500 dark:text-neutral-400">
          {t("common.loading")}
        </p>
      ) : loadError ? (
        <p className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {loadError}
        </p>
      ) : (
        <div className="mt-4 max-w-2xl">
          {/* Target URL */}
          <label className="block">
            <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
              {t("autotoolCfg.targetUrl")}
            </span>
            <input
              type="url"
              value={targetUrl}
              onChange={(e) => setTargetUrl(e.target.value)}
              placeholder="https://autotool.mrba-stage1.xyz/api/task/new/ImportPosts"
              className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            />
            <span className="mt-1 block text-xs text-neutral-500 dark:text-neutral-400">
              {t("autotoolCfg.targetUrlHint")}
            </span>
          </label>

          {/* API key */}
          <label className="mt-5 block">
            <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
              {t("autotoolCfg.apiKey")}
            </span>
            <input
              type="password"
              value={clearKey ? "" : apiKey}
              disabled={clearKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={
                keyConfigured
                  ? t("autotoolCfg.apiKeyConfigured")
                  : t("autotoolCfg.apiKeyPlaceholder")
              }
              className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 font-mono text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            />
            <span className="mt-1 flex items-center gap-2 text-xs text-neutral-500 dark:text-neutral-400">
              <span>{t("autotoolCfg.apiKeyHint")}</span>
              {keyConfigured && !clearKey && (
                <button
                  type="button"
                  onClick={() => {
                    setClearKey(true);
                    setApiKey("");
                  }}
                  className="font-medium text-red-600 hover:underline dark:text-red-400"
                >
                  {t("autotoolCfg.clearKey")}
                </button>
              )}
              {clearKey && (
                <button
                  type="button"
                  onClick={() => setClearKey(false)}
                  className="font-medium text-neutral-600 hover:underline dark:text-neutral-300"
                >
                  {t("autotoolCfg.undoClear")}
                </button>
              )}
            </span>
            {clearKey && (
              <span className="mt-1 block text-xs text-red-600 dark:text-red-400">
                {t("autotoolCfg.clearKeyPending")}
              </span>
            )}
          </label>

          {saveError && (
            <p className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
              {saveError}
            </p>
          )}

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => void save()}
              disabled={saving}
              className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
            >
              {saving ? t("common.saving") : t("common.save")}
            </button>
            <button
              type="button"
              onClick={() => void test()}
              disabled={testing}
              className="rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-60 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
              title={t("autotoolCfg.testHint")}
            >
              {testing ? t("autotoolCfg.testing") : t("autotoolCfg.test")}
            </button>
            {savedAt && !saving && (
              <span className="text-xs text-green-700 dark:text-green-400">
                {t("common.saved")}
              </span>
            )}
            {testResult && (
              <span
                className={
                  "inline-flex items-center gap-1.5 text-xs " +
                  (testResult.ok
                    ? "text-green-700 dark:text-green-400"
                    : "text-red-600 dark:text-red-400")
                }
                title={testResult.detail}
              >
                <span>{testResult.ok ? "✓" : "✗"}</span>
                {testResult.status_code != null && (
                  <span>HTTP {testResult.status_code}</span>
                )}
                {testResult.elapsed_ms != null && (
                  <span>· {testResult.elapsed_ms}ms</span>
                )}
                <span>· {testResult.detail}</span>
              </span>
            )}
          </div>

          <p className="mt-4 text-xs text-neutral-500 dark:text-neutral-400">
            {t("autotoolCfg.testNote")}
          </p>
        </div>
      )}
    </div>
  );
}
