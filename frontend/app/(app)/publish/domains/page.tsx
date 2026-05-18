"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { DomainCsvImportModal } from "@/components/DomainCsvImportModal";
import { DomainJsonImportModal } from "@/components/DomainJsonImportModal";
import { DomainModal } from "@/components/DomainModal";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useT } from "@/lib/i18n-context";
import {
  deleteDomain,
  getDomainTrashCount,
  listDomains,
  testDomain,
  type Domain,
  type TestConnectionResult,
} from "@/lib/domains";

type ModalState =
  | { kind: "closed" }
  | { kind: "create" }
  | { kind: "edit"; domain: Domain }
  | { kind: "import" }
  | { kind: "importJson" };

export default function DomainsPage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const { t } = useT();

  const [domains, setDomains] = useState<Domain[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalState>({ kind: "closed" });
  const [testing, setTesting] = useState<Set<number>>(new Set());
  const [testResults, setTestResults] = useState<Record<number, TestConnectionResult>>({});
  const [trashCount, setTrashCount] = useState(0);

  const isAuthorized = user && ["admin", "manager"].includes(user.role.name);

  const refreshTrashCount = useCallback(async () => {
    try {
      const { count } = await getDomainTrashCount();
      setTrashCount(count);
    } catch {
      // non-critical; the badge just won't show
    }
  }, []);

  useEffect(() => {
    if (isAuthorized) void refreshTrashCount();
  }, [isAuthorized, refreshTrashCount]);

  useEffect(() => {
    if (!authLoading && user && !isAuthorized) router.replace("/dashboard");
  }, [user, authLoading, isAuthorized, router]);

  const load = useCallback(async () => {
    try {
      const list = await listDomains();
      setDomains(list);
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : t("common.failedToLoad"));
    }
  }, [t]);

  useEffect(() => {
    if (isAuthorized) load();
  }, [isAuthorized, load]);

  if (authLoading || !user || !isAuthorized) return null;

  function upsert(d: Domain) {
    setDomains((list) => {
      if (!list) return [d];
      const i = list.findIndex((x) => x.id === d.id);
      if (i === -1) return [...list, d];
      const copy = list.slice();
      copy[i] = d;
      return copy;
    });
  }

  async function onDelete(target: Domain) {
    if (!confirm(t("domains.confirmDelete", { name: target.name }))) return;
    try {
      await deleteDomain(target.id);
      setDomains((list) => (list ? list.filter((x) => x.id !== target.id) : list));
      await refreshTrashCount();
    } catch (err) {
      // 409 = in-flight bulk publish run targets this domain.
      if (err instanceof ApiError && err.status === 409) {
        alert(err.message || t("domains.deleteBlockedInflight"));
      } else {
        alert(err instanceof ApiError ? err.message : t("common.deleteFailed"));
      }
    }
  }

  async function onTest(target: Domain) {
    setTesting((s) => new Set(s).add(target.id));
    try {
      const r = await testDomain(target.id);
      setTestResults((m) => ({ ...m, [target.id]: r }));
    } catch (err) {
      setTestResults((m) => ({
        ...m,
        [target.id]: {
          ok: false,
          status_code: null,
          detail: err instanceof ApiError ? err.message : t("domains.testFailed"),
          elapsed_ms: null,
        },
      }));
    } finally {
      setTesting((s) => {
        const next = new Set(s);
        next.delete(target.id);
        return next;
      });
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-5 py-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
            {t("domains.title")}
          </h1>
          <p className="mt-0.5 text-sm text-neutral-500 dark:text-neutral-400">
            {t("domains.subtitle")}
          </p>
        </div>
        <div className="flex gap-2">
          {trashCount > 0 && (
            <Link
              href="/publish/domains/trash"
              className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm font-medium text-neutral-600 hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-400 dark:hover:bg-neutral-800"
            >
              {t("domains.trashLinkWithCount", { count: trashCount })}
            </Link>
          )}
          <button
            onClick={() => setModal({ kind: "import" })}
            className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            {t("domains.import")}
          </button>
          <button
            onClick={() => setModal({ kind: "importJson" })}
            title={t("domains.importJsonHint")}
            className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            {t("domains.importJson")}
          </button>
          <button
            onClick={() => setModal({ kind: "create" })}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
          >
            {t("domains.add")}
          </button>
        </div>
      </div>

      {loadError && (
        <div className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {loadError}
        </div>
      )}

      <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
        <table className="min-w-full divide-y divide-neutral-200 text-sm dark:divide-neutral-800">
          <thead className="bg-neutral-50 dark:bg-neutral-900/50">
            <tr className="text-left text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
              <th className="px-3 py-2">{t("domains.colName")}</th>
              <th className="px-3 py-2">{t("domains.colBaseUrl")}</th>
              <th className="px-3 py-2">{t("domains.colCms")}</th>
              <th className="px-3 py-2">{t("domains.colAuth")}</th>
              <th className="px-3 py-2">{t("domains.colLanguages")}</th>
              <th className="px-3 py-2">{t("domains.colPlugin")}</th>
              <th className="px-3 py-2">{t("domains.colTest")}</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
            {domains === null && (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-neutral-500">
                  {t("common.loading")}
                </td>
              </tr>
            )}
            {domains !== null && domains.length === 0 && (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-neutral-500">
                  {t("domains.empty")}
                </td>
              </tr>
            )}
            {domains?.map((d) => {
              const tr = testResults[d.id];
              return (
                <tr key={d.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-800/50">
                  <td className="px-3 py-2 font-medium text-neutral-900 dark:text-neutral-100">
                    {d.name}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-neutral-700 dark:text-neutral-300">
                    {d.base_url}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={
                        "inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset " +
                        (d.cms_type === "wordpress"
                          ? "bg-blue-50 text-blue-700 ring-blue-600/10 dark:bg-blue-950/40 dark:text-blue-400 dark:ring-blue-400/30"
                          : "bg-violet-50 text-violet-700 ring-violet-600/10 dark:bg-violet-950/40 dark:text-violet-400 dark:ring-violet-400/30")
                      }
                    >
                      {d.cms_type}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-xs text-neutral-700 dark:text-neutral-300">
                    {d.auth_type}
                    {!d.has_credentials && (
                      <span className="ml-1 text-neutral-500">{t("domains.noCreds")}</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-neutral-700 dark:text-neutral-300">
                    {d.languages.join(", ")}
                  </td>
                  <td className="px-3 py-2 text-xs text-neutral-700 dark:text-neutral-300">
                    {d.cms_type === "wordpress" ? d.multilingual_plugin : "—"}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => onTest(d)}
                        disabled={testing.has(d.id)}
                        className="rounded-md border border-neutral-300 px-2 py-0.5 text-xs hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
                      >
                        {testing.has(d.id) ? t("domains.testing") : t("domains.testButton")}
                      </button>
                      {tr && (
                        <span
                          title={tr.detail}
                          className={
                            "text-xs " +
                            (tr.ok
                              ? "text-green-700 dark:text-green-400"
                              : "text-red-700 dark:text-red-400")
                          }
                        >
                          {tr.ok ? "✓" : "✗"} {tr.elapsed_ms != null ? `${tr.elapsed_ms}ms` : ""}
                        </span>
                      )}
                    </div>
                    {tr && !tr.ok && (
                      <p className="mt-0.5 max-w-xs truncate text-xs text-red-600 dark:text-red-400" title={tr.detail}>
                        {tr.detail}
                      </p>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right text-xs">
                    <button
                      onClick={() => setModal({ kind: "edit", domain: d })}
                      className="mr-3 text-neutral-700 hover:underline dark:text-neutral-300"
                    >
                      {t("common.edit")}
                    </button>
                    <button
                      onClick={() => onDelete(d)}
                      className="text-red-600 hover:underline dark:text-red-400"
                    >
                      {t("common.delete")}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {modal.kind === "create" && (
        <DomainModal
          onClose={() => setModal({ kind: "closed" })}
          onSaved={(d) => {
            upsert(d);
            setModal({ kind: "closed" });
          }}
        />
      )}
      {modal.kind === "edit" && (
        <DomainModal
          domain={modal.domain}
          onClose={() => setModal({ kind: "closed" })}
          onSaved={(d) => {
            upsert(d);
            setModal({ kind: "closed" });
          }}
        />
      )}
      {modal.kind === "import" && (
        <DomainCsvImportModal
          onClose={() => setModal({ kind: "closed" })}
          onImported={() => void load()}
        />
      )}
      {modal.kind === "importJson" && (
        <DomainJsonImportModal
          onClose={() => setModal({ kind: "closed" })}
          onImported={() => void load()}
        />
      )}
    </main>
  );
}
