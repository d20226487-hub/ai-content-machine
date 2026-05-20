"use client";

import { useT } from "@/lib/i18n-context";
import type { BulkColumn } from "@/lib/types";

/**
 * Back-fill target columns. After a successful publish, the worker writes
 * the new cms_post_id and cms_post_url into these columns so the bulk
 * table becomes the authoritative source of "what's published where".
 *
 * Both targets are optional — empty string means "don't write back". The
 * post_id target also doubles as the source for the CellFilter "only
 * unpublished" / "only failed" modes.
 */
export function BackFill({
  postIdTarget,
  postUrlTarget,
  onPostIdTargetChange,
  onPostUrlTargetChange,
  columns,
}: {
  postIdTarget: number | "";
  postUrlTarget: number | "";
  onPostIdTargetChange: (v: number | "") => void;
  onPostUrlTargetChange: (v: number | "") => void;
  columns: BulkColumn[];
}) {
  const { t } = useT();
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-neutral-900 dark:text-neutral-100">
        {t("bulkPub.backFill")}
      </h3>
      <p className="mb-2 text-xs text-neutral-500 dark:text-neutral-400">
        {t("bulkPub.backFillHint")}
      </p>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <BackFillSlot
          label={t("bulkPub.postIdTarget")}
          value={postIdTarget}
          onChange={onPostIdTargetChange}
          columns={columns}
          placeholder={t("bulkPub.backFillNone")}
        />
        <BackFillSlot
          label={t("bulkPub.postUrlTarget")}
          value={postUrlTarget}
          onChange={onPostUrlTargetChange}
          columns={columns}
          placeholder={t("bulkPub.backFillNone")}
        />
      </div>
    </div>
  );
}

function BackFillSlot({
  label,
  value,
  onChange,
  columns,
  placeholder,
}: {
  label: string;
  value: number | "";
  onChange: (v: number | "") => void;
  columns: BulkColumn[];
  placeholder: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {label}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : "")}
        className="block w-full rounded-md border border-neutral-300 bg-white px-2 py-1 text-xs dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
      >
        <option value="">{placeholder}</option>
        {columns.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
    </label>
  );
}
