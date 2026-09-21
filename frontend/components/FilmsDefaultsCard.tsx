"use client";

import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { getFilmsDefaults, saveFilmsDefaults, type FilmsDefaults } from "@/lib/domains";
import { useT } from "@/lib/i18n-context";

/**
 * Shared Films connection (Settings → Publishing, admin only).
 *
 * All Films sites share one basic-auth account — separate from Custom CMS's.
 * "Add domain → Films" stamps it onto new sites, and saving a new password
 * here applies it to every existing Films site in the same request (a Films
 * domain has no other per-site config to preserve, so there's no separate
 * "apply to all" step). The password is write-only: the API never returns it.
 */
export function FilmsDefaultsCard() {
  const { t } = useT();
  const [cfg, setCfg] = useState<FilmsDefaults | null>(null);
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getFilmsDefaults()
      .then((c) => {
        setCfg(c);
        setLogin(c.login);
      })
      .catch((e) =>
        setLoadError(e instanceof ApiError ? e.message : t("common.failedToLoad")),
      );
  }, [t]);

  const loginChanged = cfg != null && login.trim() !== cfg.login;
  // First-time setup needs both halves; afterwards either can change alone
  // (the backend keeps the stored password when none is sent).
  const canSave =
    !saving &&
    login.trim() !== "" &&
    (password.trim() !== "" || (loginChanged && !!cfg?.credentials_configured));

  async function onSave() {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      const saved = await saveFilmsDefaults({
        login: login.trim(),
        ...(password.trim() ? { password: password.trim() } : {}),
      });
      setCfg(saved);
      setLogin(saved.login);
      setPassword("");
      setSavedAt(Date.now());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.somethingWentWrong"));
    } finally {
      setSaving(false);
    }
  }

  const inputCls =
    "mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 font-mono text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100";

  return (
    <div
      className="rounded-lg border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-900"
      data-testid="films-defaults-card"
    >
      <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
        {t("filmsCms.title")}
      </h2>
      <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
        {t("filmsCms.subtitle")}
      </p>

      {loadError && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {loadError}
        </p>
      )}

      {cfg && (
        <div className="mt-4 max-w-2xl space-y-4">
          <p className="text-xs text-neutral-600 dark:text-neutral-400">
            {t("filmsCms.endpoint")}{" "}
            <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono dark:bg-neutral-800">
              https://&lt;domain&gt;{cfg.endpoint_path}
            </code>
          </p>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                {t("filmsCms.login")}
              </span>
              <input
                type="text"
                value={login}
                autoComplete="off"
                onChange={(e) => setLogin(e.target.value)}
                className={inputCls}
                data-testid="films-login"
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                {t("filmsCms.password")}
              </span>
              <input
                type="password"
                value={password}
                autoComplete="new-password"
                onChange={(e) => setPassword(e.target.value)}
                placeholder={
                  cfg.credentials_configured
                    ? t("customCms.passwordSet")
                    : t("customCms.passwordEmpty")
                }
                className={inputCls}
                data-testid="films-password"
              />
            </label>
          </div>
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            {t("filmsCms.appliesTo", { n: cfg.domain_count })}
          </p>

          {error && (
            <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
              {error}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => void onSave()}
              disabled={!canSave}
              className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900"
              data-testid="films-save"
            >
              {saving ? t("common.saving") : t("common.save")}
            </button>
            {savedAt && !saving && (
              <span className="text-xs text-green-700 dark:text-green-400">
                {t("common.saved")}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
