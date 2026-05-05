"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { Modal } from "@/components/Modal";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  DEFAULT_WP_FIELDS,
  listDomains,
  type Domain,
  type PublishProfile,
} from "@/lib/domains";
import {
  clearMapping,
  createBulkRun,
  getMapping,
  type BulkPublishPayload,
  type CellFilter,
  type RowFilter,
} from "@/lib/publishBulk";
import type { BulkColumn, BulkTable } from "@/lib/types";

interface Props {
  table: BulkTable;
  selectedRowIds: number[];
  onClose: () => void;
}

interface FieldSlot {
  key: string;
  label: string;
  required: boolean;
}

export function BulkPublishModal({ table, selectedRowIds, onClose }: Props) {
  const { t } = useT();
  const router = useRouter();
  const [domains, setDomains] = useState<Domain[] | null>(null);
  const [domainId, setDomainId] = useState<number | null>(null);
  const [profileName, setProfileName] = useState<string | null>(null);
  const [language, setLanguage] = useState<string | null>(null);

  const [rowFilter, setRowFilter] = useState<RowFilter>(
    selectedRowIds.length > 0 ? "selected" : "all",
  );
  const [rangeStart, setRangeStart] = useState<string>("1");
  const [rangeEnd, setRangeEnd] = useState<string>(String(table.rows.length));
  const [cellFilter, setCellFilter] = useState<CellFilter>("all");

  const [fieldToColumn, setFieldToColumn] = useState<Record<string, number>>({});
  const [postIdTarget, setPostIdTarget] = useState<number | "">("");
  const [postUrlTarget, setPostUrlTarget] = useState<number | "">("");

  const [saveMapping, setSaveMapping] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    listDomains()
      .then((list) => {
        setDomains(list);
        const first = list.find((d) => d.has_credentials) ?? list[0] ?? null;
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

  const wpProfiles: PublishProfile[] = useMemo(() => {
    if (selected?.cms_type !== "wordpress") return [];
    const saved = selected.publish_config?.profiles;
    if (saved && saved.length > 0) return saved;
    return [{ name: "Default", post_type: "posts", fields: DEFAULT_WP_FIELDS }];
  }, [selected]);

  const activeProfile = useMemo(() => {
    if (!selected || selected.cms_type !== "wordpress") return null;
    return wpProfiles.find((p) => p.name === profileName) ?? wpProfiles[0] ?? null;
  }, [selected, wpProfiles, profileName]);

  // Compute the set of field "slots" the user must map columns to.
  const slots: FieldSlot[] = useMemo(() => {
    if (!selected) return [];
    if (selected.cms_type === "wordpress") {
      const fields = activeProfile?.fields ?? DEFAULT_WP_FIELDS;
      return fields.map((f) => ({
        key: f.key,
        label: f.label || f.key,
        required: !!f.required,
      }));
    }
    // Custom: derive from body_template placeholders
    const placeholders = collectPlaceholders(selected.custom_config?.body_template);
    return placeholders
      .filter((p) => p !== "language")
      .map((p) => ({ key: p, label: p, required: false }));
  }, [selected, activeProfile]);

  // When domain/profile changes: pick default language + load saved mapping memo.
  useEffect(() => {
    if (!selected) return;
    setLanguage(selected.languages[0] ?? "en");

    // Default WP profile picker selection
    if (selected.cms_type === "wordpress") {
      const profileNames = wpProfiles.map((p) => p.name);
      setProfileName((cur) =>
        cur && profileNames.includes(cur) ? cur : profileNames[0] ?? null,
      );
    } else {
      setProfileName(null);
    }
  }, [selected, wpProfiles]);

  useEffect(() => {
    if (!selected) {
      setFieldToColumn({});
      setPostIdTarget("");
      setPostUrlTarget("");
      return;
    }
    getMapping(table.id, selected.id, profileName)
      .then((m) => {
        setFieldToColumn(m.field_to_column ?? {});
        setPostIdTarget(
          (m.back_fill?.post_id_target as number | undefined) ?? "",
        );
        setPostUrlTarget(
          (m.back_fill?.post_url_target as number | undefined) ?? "",
        );
        if (m.language) setLanguage(m.language);
      })
      .catch(() => {
        setFieldToColumn({});
        setPostIdTarget("");
        setPostUrlTarget("");
      });
  }, [selected, profileName, table.id]);

  // "Will publish N rows" estimate (client-side).
  const candidatePreview = useMemo(() => {
    let candidates: number[];
    if (rowFilter === "selected") {
      candidates = selectedRowIds.slice();
    } else if (rowFilter === "range") {
      const s = Math.max(1, Number(rangeStart) || 1) - 1;
      const e = Math.max(0, Number(rangeEnd) || 0);
      candidates = table.rows.slice(s, e).map((r) => r.id);
    } else {
      candidates = table.rows.map((r) => r.id);
    }

    if (cellFilter !== "all" && postIdTarget !== "") {
      const colId = Number(postIdTarget);
      const cellByRow: Record<number, string> = {};
      for (const c of table.cells) {
        if (c.column_id === colId) cellByRow[c.row_id] = c.value || "";
      }
      candidates = candidates.filter((rid) => !cellByRow[rid]);
    }
    return candidates.length;
  }, [rowFilter, rangeStart, rangeEnd, cellFilter, postIdTarget, selectedRowIds, table]);

  function setSlot(key: string, colId: number | null) {
    setFieldToColumn((m) => {
      const next = { ...m };
      if (colId == null) delete next[key];
      else next[key] = colId;
      return next;
    });
  }

  async function onClear() {
    if (!selected) return;
    if (!confirm(t("bulkPub.confirmClearMapping"))) return;
    try {
      await clearMapping(table.id, selected.id, profileName);
      setFieldToColumn({});
      setPostIdTarget("");
      setPostUrlTarget("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("domainMod.clearCacheFailed"));
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selected) return;
    setError(null);

    // Validate required slots are mapped
    const missing = slots.filter((s) => s.required && fieldToColumn[s.key] == null);
    if (missing.length > 0) {
      setError(
        t("bulkPub.missingRequired", { fields: missing.map((m) => m.label).join(", ") }),
      );
      return;
    }

    const back_fill: Record<string, number> = {};
    if (postIdTarget !== "") back_fill.post_id_target = Number(postIdTarget);
    if (postUrlTarget !== "") back_fill.post_url_target = Number(postUrlTarget);

    let selection: Record<string, unknown> | null = null;
    if (rowFilter === "selected") {
      if (selectedRowIds.length === 0) {
        setError(t("bulkPub.noRowsSelected"));
        return;
      }
      selection = { row_ids: selectedRowIds };
    } else if (rowFilter === "range") {
      selection = {
        start: Number(rangeStart) || 1,
        end: Number(rangeEnd) || table.rows.length,
      };
    }

    const payload: BulkPublishPayload = {
      table_id: table.id,
      domain_id: selected.id,
      profile_name: profileName,
      language,
      row_filter: rowFilter,
      selection,
      cell_filter: cellFilter,
      field_to_column: fieldToColumn,
      back_fill,
      save_mapping: saveMapping,
    };

    setBusy(true);
    try {
      const run = await createBulkRun(payload);
      router.push(`/publish/runs/${run.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("bulkPub.failedToStart"));
      setBusy(false);
    }
  }

  const eligibleColumns = table.columns;

  return (
    <Modal onClose={onClose} size="max-w-3xl">
      <form onSubmit={onSubmit} className="space-y-4">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          {t("bulkPub.title")}
        </h2>
        <p className="text-xs text-neutral-500 dark:text-neutral-400">
          {t("bulkPub.subtitle", { table: table.name })}
        </p>

        {loadError && (
          <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
            {loadError}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <Field label={t("bulkPub.fieldDomain")}>
            <select
              value={domainId ?? ""}
              onChange={(e) => setDomainId(Number(e.target.value))}
              className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            >
              {(domains ?? []).map((d) => (
                <option key={d.id} value={d.id} disabled={!d.has_credentials}>
                  {d.name} ({d.cms_type}){!d.has_credentials ? t("pubMod.noCreds") : ""}
                </option>
              ))}
            </select>
          </Field>

          {selected?.cms_type === "wordpress" && wpProfiles.length > 0 && (
            <Field label={t("bulkPub.fieldPostType")}>
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

          {selected && selected.languages.length > 1 && (
            <Field label={t("bulkPub.fieldLanguage")}>
              <select
                value={language ?? ""}
                onChange={(e) => setLanguage(e.target.value)}
                className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              >
                {selected.languages.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </Field>
          )}
        </div>

        {/* Row filter */}
        <div>
          <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            {t("bulkPub.rows")}
          </span>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <label className="flex items-center gap-1">
              <input
                type="radio"
                checked={rowFilter === "all"}
                onChange={() => setRowFilter("all")}
              />
              {t("bulkPub.rowsAll", { count: table.rows.length })}
            </label>
            <label className="flex items-center gap-1">
              <input
                type="radio"
                checked={rowFilter === "selected"}
                onChange={() => setRowFilter("selected")}
                disabled={selectedRowIds.length === 0}
              />
              {t("bulkPub.rowsSelected", { count: selectedRowIds.length })}
            </label>
            <label className="flex items-center gap-1">
              <input
                type="radio"
                checked={rowFilter === "range"}
                onChange={() => setRowFilter("range")}
              />
              {t("bulkPub.rowsRange")}
            </label>
            {rowFilter === "range" && (
              <span className="flex items-center gap-1 text-xs text-neutral-600 dark:text-neutral-400">
                <input
                  type="number"
                  min={1}
                  value={rangeStart}
                  onChange={(e) => setRangeStart(e.target.value)}
                  className="w-20 rounded-md border border-neutral-300 bg-white px-2 py-1 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                />
                <span>–</span>
                <input
                  type="number"
                  min={1}
                  value={rangeEnd}
                  onChange={(e) => setRangeEnd(e.target.value)}
                  className="w-20 rounded-md border border-neutral-300 bg-white px-2 py-1 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                />
              </span>
            )}
          </div>
        </div>

        {/* Cell filter */}
        <div>
          <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            {t("bulkPub.cellFilter")}
          </span>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <label className="flex items-center gap-1">
              <input
                type="radio"
                checked={cellFilter === "all"}
                onChange={() => setCellFilter("all")}
              />
              {t("bulkPub.cellAll")}
            </label>
            <label className="flex items-center gap-1">
              <input
                type="radio"
                checked={cellFilter === "unpublished"}
                onChange={() => setCellFilter("unpublished")}
              />
              {t("bulkPub.cellUnpublished")}
            </label>
            <label className="flex items-center gap-1">
              <input
                type="radio"
                checked={cellFilter === "failed"}
                onChange={() => setCellFilter("failed")}
              />
              {t("bulkPub.cellFailed")}
            </label>
          </div>
          {cellFilter !== "all" && postIdTarget === "" && (
            <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">
              {t("bulkPub.cellNeedTarget")}
            </p>
          )}
        </div>

        {/* Field-to-column mapping */}
        {selected && (
          <div className="border-t border-neutral-200 pt-3 dark:border-neutral-800">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
                {t("bulkPub.mapHeading")}
              </h3>
              <button
                type="button"
                onClick={onClear}
                className="text-xs text-neutral-500 underline hover:text-red-600 dark:text-neutral-400 dark:hover:text-red-400"
              >
                {t("bulkPub.clearMapping")}
              </button>
            </div>
            <div className="space-y-1 text-sm">
              {slots.map((s) => (
                <div
                  key={s.key}
                  className="grid grid-cols-[1fr_2fr] items-center gap-2"
                >
                  <span className="truncate text-neutral-700 dark:text-neutral-300">
                    {s.label}
                    {s.required && <span className="ml-0.5 text-red-600">*</span>}
                  </span>
                  <select
                    value={fieldToColumn[s.key] ?? ""}
                    onChange={(e) =>
                      setSlot(s.key, e.target.value ? Number(e.target.value) : null)
                    }
                    className="block w-full rounded-md border border-neutral-300 bg-white px-2 py-1 text-xs dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                  >
                    <option value="">{t("bulkPub.skip")}</option>
                    {eligibleColumns.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
              {slots.length === 0 && (
                <p className="text-xs text-neutral-500 dark:text-neutral-400">
                  {t("bulkPub.noFieldsDetected")}
                </p>
              )}
            </div>

            <h3 className="mt-4 mb-2 text-sm font-semibold text-neutral-900 dark:text-neutral-100">
              {t("bulkPub.backFill")}
            </h3>
            <p className="mb-2 text-xs text-neutral-500 dark:text-neutral-400">
              {t("bulkPub.backFillHint")}
            </p>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Field label={t("bulkPub.postIdTarget")}>
                <select
                  value={postIdTarget}
                  onChange={(e) =>
                    setPostIdTarget(e.target.value ? Number(e.target.value) : "")
                  }
                  className="block w-full rounded-md border border-neutral-300 bg-white px-2 py-1 text-xs dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                >
                  <option value="">{t("bulkPub.backFillNone")}</option>
                  {eligibleColumns.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t("bulkPub.postUrlTarget")}>
                <select
                  value={postUrlTarget}
                  onChange={(e) =>
                    setPostUrlTarget(e.target.value ? Number(e.target.value) : "")
                  }
                  className="block w-full rounded-md border border-neutral-300 bg-white px-2 py-1 text-xs dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                >
                  <option value="">{t("bulkPub.backFillNone")}</option>
                  {eligibleColumns.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
          </div>
        )}

        <label className="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300">
          <input
            type="checkbox"
            checked={saveMapping}
            onChange={(e) => setSaveMapping(e.target.checked)}
          />
          {t("bulkPub.remember")}
        </label>

        <div className="rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-800 dark:bg-blue-950/40 dark:text-blue-300">
          {t("bulkPub.willPublish", { count: candidatePreview })}
        </div>

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
            disabled={busy || !selected || candidatePreview === 0}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900"
          >
            {busy ? t("bulkPub.starting") : t("bulkPub.start", { count: candidatePreview })}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {label}
      </span>
      {children}
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
