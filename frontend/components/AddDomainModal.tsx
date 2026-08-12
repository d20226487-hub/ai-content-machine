"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { Modal } from "@/components/Modal";
import { ApiError } from "@/lib/api";
import {
  bulkAddSimpleDomains,
  getCustomCmsDefaults,
  type CustomCmsDefaults,
  type SimpleDomainImportResult,
} from "@/lib/domains";
import { useT } from "@/lib/i18n-context";

/**
 * "Add domain" entry point: pick the CMS, then add.
 *
 * Custom CMS sites in this workspace are identical apart from their domain and
 * languages — endpoint, body template and the shared password all live in
 * Settings → Publishing. So the Custom path is a bulk paste of
 * ``domain.com - en, es, ru`` lines (first language = default) rather than a
 * form with a dozen fields repeated per site.
 *
 * WordPress keeps the full per-domain form: profiles, post types and app
 * passwords genuinely differ per site, so choosing it hands back to the
 * existing DomainModal via ``onPickWordpress``.
 */
export function AddDomainModal({
  onClose,
  onPickWordpress,
  onImported,
}: {
  onClose: () => void;
  /** Chose WordPress — the page opens the full per-domain form. */
  onPickWordpress: () => void;
  /** Domains were created/updated; refresh the list. */
  onImported: (result: SimpleDomainImportResult) => void;
}) {
  const { t } = useT();
  const [step, setStep] = useState<"choose" | "paste">("choose");
  const [cms, setCms] = useState<"custom" | "wordpress">("custom");

  const [text, setText] = useState("");
  const [updateExisting, setUpdateExisting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SimpleDomainImportResult | null>(null);

  // Shown on the paste step so the operator can see what will be stamped on —
  // and is warned before pasting 50 domains if the shared password is missing.
  const [defaults, setDefaults] = useState<CustomCmsDefaults | null>(null);
  useEffect(() => {
    if (step !== "paste") return;
    getCustomCmsDefaults()
      .then(setDefaults)
      .catch(() => setDefaults(null));
  }, [step]);

  function proceed() {
    if (cms === "wordpress") {
      onPickWordpress();
      return;
    }
    setStep("paste");
  }

  async function submit() {
    if (busy || !text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await bulkAddSimpleDomains(text, updateExisting);
      setResult(r);
      if (r.created > 0 || r.updated > 0) onImported(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose} size={step === "paste" ? "max-w-2xl" : "max-w-lg"}>
      <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        {t("addDomain.title")}
      </h2>

      {step === "choose" ? (
        <>
          <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
            {t("addDomain.chooseHint")}
          </p>
          <div className="mt-4 space-y-2">
            {(
              [
                { key: "custom", label: t("addDomain.custom"), hint: t("addDomain.customHint") },
                { key: "wordpress", label: t("addDomain.wordpress"), hint: t("addDomain.wordpressHint") },
              ] as const
            ).map((opt) => (
              <label
                key={opt.key}
                className={
                  "flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm transition-colors " +
                  (cms === opt.key
                    ? "border-neutral-900 bg-neutral-50 dark:border-neutral-100 dark:bg-neutral-800"
                    : "border-neutral-200 hover:bg-neutral-50 dark:border-neutral-700 dark:hover:bg-neutral-800/60")
                }
              >
                <input
                  type="radio"
                  name="cms-type"
                  className="mt-1"
                  checked={cms === opt.key}
                  onChange={() => setCms(opt.key)}
                />
                <span>
                  <span className="block font-medium text-neutral-900 dark:text-neutral-100">
                    {opt.label}
                  </span>
                  <span className="mt-0.5 block text-xs text-neutral-500 dark:text-neutral-400">
                    {opt.hint}
                  </span>
                </span>
              </label>
            ))}
          </div>
          <div className="mt-5 flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              {t("common.cancel")}
            </button>
            <button
              type="button"
              onClick={proceed}
              data-testid="add-domain-proceed"
              className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 dark:bg-neutral-100 dark:text-neutral-900"
            >
              {t("addDomain.proceed")}
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
            {t("addDomain.pasteHint")}
          </p>

          {/* No shared password → the API refuses the batch. Say so up front. */}
          {defaults && !defaults.credentials_configured && (
            <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
              {t("addDomain.noPassword")}{" "}
              <Link
                href="/settings?tab=publishing"
                className="font-medium underline underline-offset-2"
              >
                {t("addDomain.noPasswordLink")}
              </Link>
            </p>
          )}

          <textarea
            rows={9}
            value={text}
            onChange={(e) => setText(e.target.value)}
            spellCheck={false}
            placeholder={"example.com - en, es, ru\nexample.org - es, en"}
            data-testid="add-domain-textarea"
            className="mt-3 block w-full rounded-md border border-neutral-300 px-3 py-2 font-mono text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
          />

          {defaults && (
            <p className="mt-2 text-xs text-neutral-500 dark:text-neutral-400">
              {t("addDomain.appliedConfig", { endpoint: defaults.endpoint_path })}
            </p>
          )}

          <label className="mt-3 flex items-start gap-2 text-sm text-neutral-700 dark:text-neutral-300">
            <input
              type="checkbox"
              checked={updateExisting}
              onChange={(e) => setUpdateExisting(e.target.checked)}
              data-testid="add-domain-update-existing"
              className="mt-0.5 h-4 w-4 rounded border-neutral-300 dark:border-neutral-600"
            />
            <span>
              <span className="font-medium">{t("addDomain.updateExisting")}</span>
              <span className="mt-0.5 block text-xs text-neutral-500 dark:text-neutral-400">
                {t("addDomain.updateExistingHint")}
              </span>
            </span>
          </label>

          {error && (
            <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
              {error}
            </p>
          )}

          {result && (
            <div className="mt-3 rounded-md border border-neutral-200 bg-neutral-50 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900/60">
              <p className="font-medium text-neutral-800 dark:text-neutral-200">
                {t("addDomain.resultSummary", {
                  created: result.created,
                  updated: result.updated,
                  skipped: result.skipped,
                })}
              </p>
              {result.errors.length > 0 && (
                <ul className="mt-2 max-h-40 space-y-0.5 overflow-auto text-xs text-neutral-600 dark:text-neutral-400">
                  {result.errors.map((e, i) => (
                    <li key={i}>
                      {e.line != null && (
                        <span className="font-mono">
                          {t("addDomain.lineNo", { n: e.line })}{" "}
                        </span>
                      )}
                      {e.detail}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className="mt-5 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => (result ? onClose() : setStep("choose"))}
              className="rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              {result ? t("common.close") : t("common.back")}
            </button>
            <button
              type="button"
              onClick={() => void submit()}
              disabled={busy || !text.trim()}
              data-testid="add-domain-submit"
              className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900"
            >
              {busy ? t("common.saving") : t("addDomain.submit")}
            </button>
          </div>
        </>
      )}
    </Modal>
  );
}
