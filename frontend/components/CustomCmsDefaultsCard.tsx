"use client";

import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import {
  getCustomCmsDefaults,
  reapplyCustomCmsDefaults,
  saveCustomCmsDefaults,
  type CustomCmsDefaults,
} from "@/lib/domains";
import { useT } from "@/lib/i18n-context";

/**
 * Shared Custom-CMS connection config (Settings → Publishing, admin only).
 *
 * Every Custom CMS site here talks to the same in-house CMS, so the endpoint,
 * JSON body and basic-auth password live once instead of per domain. The bulk
 * "Add domain" paste stamps new sites from this; "Re-apply" pushes it onto
 * existing ones after the CMS contract changes.
 *
 * Re-apply overwrites the connection config of EVERY Custom domain, so it is
 * deliberately behind a typed confirmation — an accidental click is expensive
 * and not undoable without a database restore.
 */
export function CustomCmsDefaultsCard() {
  const { t } = useT();

  const [cfg, setCfg] = useState<CustomCmsDefaults | null>(null);
  const [bodyText, setBodyText] = useState("");
  const [bodyError, setBodyError] = useState<string | null>(null);
  const [password, setPassword] = useState("");

  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [reapplying, setReapplying] = useState(false);
  const [reapplyNote, setReapplyNote] = useState<string | null>(null);

  useEffect(() => {
    getCustomCmsDefaults()
      .then((c) => {
        setCfg(c);
        setBodyText(JSON.stringify(c.body_template, null, 2));
      })
      .catch((e) =>
        setLoadError(e instanceof ApiError ? e.message : t("common.failedToLoad")),
      );
  }, [t]);

  function patch(next: Partial<CustomCmsDefaults>) {
    setCfg((c) => (c ? { ...c, ...next } : c));
  }

  async function onSave() {
    if (!cfg || saving) return;
    let body: Record<string, unknown>;
    try {
      body = JSON.parse(bodyText);
      if (typeof body !== "object" || body === null || Array.isArray(body)) {
        throw new Error("not an object");
      }
    } catch {
      setBodyError(t("customCms.bodyInvalid"));
      return;
    }
    setBodyError(null);
    setSaving(true);
    setError(null);
    try {
      const saved = await saveCustomCmsDefaults({
        endpoint_path: cfg.endpoint_path,
        body_template: body,
        response_id_path: cfg.response_id_path,
        response_url_path: cfg.response_url_path,
        ...(password ? { credentials: password } : {}),
      });
      setCfg(saved);
      setBodyText(JSON.stringify(saved.body_template, null, 2));
      setPassword("");
      setSavedAt(Date.now());
      setReapplyNote(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.somethingWentWrong"));
    } finally {
      setSaving(false);
    }
  }

  async function onReapply() {
    if (reapplying) return;
    setReapplying(true);
    setError(null);
    try {
      const r = await reapplyCustomCmsDefaults();
      setReapplyNote(t("customCms.reapplyDone", { n: r.updated }));
      setConfirmOpen(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.somethingWentWrong"));
    } finally {
      setReapplying(false);
    }
  }

  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-900">
      <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
        {t("customCms.title")}
      </h2>
      <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
        {t("customCms.subtitle")}
      </p>

      {loadError && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {loadError}
        </p>
      )}

      {cfg && (
        <div className="mt-4 max-w-2xl space-y-4">
          <label className="block">
            <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
              {t("customCms.endpoint")}
            </span>
            <input
              type="text"
              value={cfg.endpoint_path}
              onChange={(e) => patch({ endpoint_path: e.target.value })}
              className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 font-mono text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
              {t("customCms.password")}
            </span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={
                cfg.credentials_configured
                  ? t("customCms.passwordSet")
                  : t("customCms.passwordEmpty")
              }
              className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 font-mono text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            />
            <span className="mt-1 block text-xs text-neutral-500 dark:text-neutral-400">
              {t("customCms.passwordHint")}
            </span>
          </label>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                {t("customCms.idPath")}
              </span>
              <input
                type="text"
                value={cfg.response_id_path ?? ""}
                onChange={(e) => patch({ response_id_path: e.target.value })}
                className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 font-mono text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                {t("customCms.urlPath")}
              </span>
              <input
                type="text"
                value={cfg.response_url_path ?? ""}
                onChange={(e) => patch({ response_url_path: e.target.value })}
                className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 font-mono text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              />
            </label>
          </div>

          <label className="block">
            <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
              {t("customCms.body")}
            </span>
            <textarea
              rows={10}
              value={bodyText}
              spellCheck={false}
              onChange={(e) => {
                setBodyText(e.target.value);
                setBodyError(null);
              }}
              className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 font-mono text-xs focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            />
            <span className="mt-1 block text-xs text-neutral-500 dark:text-neutral-400">
              {t("customCms.bodyHint")}
            </span>
            {bodyError && (
              <span className="mt-1 block text-xs text-red-600 dark:text-red-400">
                {bodyError}
              </span>
            )}
          </label>

          {error && (
            <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
              {error}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => void onSave()}
              disabled={saving}
              className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900"
            >
              {saving ? t("common.saving") : t("common.save")}
            </button>
            {savedAt && !saving && (
              <span className="text-xs text-green-700 dark:text-green-400">
                {t("common.saved")}
              </span>
            )}
          </div>

          {/* Destructive: overwrites every Custom domain's connection config. */}
          <div className="rounded-md border border-amber-300 bg-amber-50 p-3 dark:border-amber-800/60 dark:bg-amber-950/30">
            <p className="text-sm font-medium text-amber-900 dark:text-amber-200">
              {t("customCms.reapplyTitle")}
            </p>
            <p className="mt-0.5 text-xs text-amber-800 dark:text-amber-300">
              {t("customCms.reapplyHint")}
            </p>
            {reapplyNote && (
              <p className="mt-2 text-xs font-medium text-green-700 dark:text-green-400">
                {reapplyNote}
              </p>
            )}
            {confirmOpen ? (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium text-amber-900 dark:text-amber-200">
                  {t("customCms.reapplyConfirm")}
                </span>
                <button
                  type="button"
                  onClick={() => void onReapply()}
                  disabled={reapplying}
                  data-testid="custom-cms-reapply-confirm"
                  className="rounded-md bg-amber-600 px-3 py-1 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-60"
                >
                  {reapplying ? t("common.loading") : t("customCms.reapplyYes")}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmOpen(false)}
                  className="rounded-md border border-amber-400 px-3 py-1 text-xs font-medium text-amber-900 hover:bg-amber-100 dark:border-amber-700 dark:text-amber-200 dark:hover:bg-amber-900/40"
                >
                  {t("common.cancel")}
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => {
                  setConfirmOpen(true);
                  setReapplyNote(null);
                }}
                data-testid="custom-cms-reapply"
                className="mt-2 rounded-md border border-amber-400 bg-white px-3 py-1 text-xs font-medium text-amber-900 hover:bg-amber-100 dark:border-amber-700 dark:bg-transparent dark:text-amber-200 dark:hover:bg-amber-900/40"
              >
                {t("customCms.reapplyButton")}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
