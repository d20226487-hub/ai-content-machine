"use client";

import { Fragment, use, useCallback, useEffect, useMemo, useState } from "react";

import { Pagination } from "@/components/Pagination";
import { ToolBreadcrumb } from "@/components/ToolBreadcrumb";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  dismissTranslationErrors,
  getTranslationTable,
  restoreTranslationErrors,
  type LinkTypeFilter,
  type TranslationLinkTag,
  type TranslationTableRow,
  type TranslationTableView,
} from "@/lib/linkCheck";

const PAGE_SIZE = 25;

const errKey = (rowId: number, url: string) => `${rowId}|${url}`;
const splitKey = (k: string): { row_id: number; link: string } => {
  const i = k.indexOf("|");
  return { row_id: Number(k.slice(0, i)), link: k.slice(i + 1) };
};

// Restored strong green in LIGHT mode; only DARK mode is toned down.
const GREEN = "text-emerald-700 dark:text-emerald-500/90";
const RED = "text-red-600 dark:text-red-400";
const GREY = "text-neutral-500 dark:text-neutral-400";

function kindCls(kind: TranslationLinkTag["kind"]): string {
  return kind === "discrepancy" ? RED : kind === "invented" ? GREY : GREEN;
}

export default function TranslationTablePage({
  params,
}: {
  params: Promise<{ id: string; runId: string }>;
}) {
  const { id, runId } = use(params);
  const tableId = Number(id);
  const rid = Number(runId);
  const { t } = useT();

  const [rows, setRows] = useState<TranslationTableRow[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [view, setView] = useState<TranslationTableView>("active");
  const [linkType, setLinkType] = useState<LinkTypeFilter>("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => setPage(1), [view, linkType]);
  useEffect(() => setSelected(new Set()), [view, linkType, page]);

  const load = useCallback(
    async (p: number) => {
      setLoading(true);
      try {
        const r = await getTranslationTable(rid, p, PAGE_SIZE, view, linkType);
        setRows(r.items);
        setTotal(r.total_rows);
        setError(null);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [rid, view, linkType],
  );

  useEffect(() => {
    if (Number.isFinite(rid)) void load(page);
  }, [rid, page, load]);

  const selectable = view === "active" || view === "dismissed";
  // Every selectable error key on the page (the aligned wrongs).
  const pageKeys = useMemo(
    () =>
      rows.flatMap((r) =>
        r.aligned
          .filter((a) => a.wrong)
          .map((a) => errKey(r.row_id, a.wrong!.url)),
      ),
    [rows],
  );
  const allSelected = pageKeys.length > 0 && pageKeys.every((k) => selected.has(k));

  function toggle(k: string) {
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  }
  function toggleAll() {
    setSelected((cur) =>
      pageKeys.every((k) => cur.has(k)) ? new Set() : new Set(pageKeys),
    );
  }

  async function applyAction() {
    if (selected.size === 0 || busy) return;
    setBusy(true);
    setError(null);
    try {
      const items = Array.from(selected).map(splitKey);
      if (view === "dismissed") await restoreTranslationErrors(rid, items);
      else await dismissTranslationErrors(rid, items);
      setSelected(new Set());
      await load(page);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-5 py-6">
      <ToolBreadcrumb
        tableId={tableId}
        trail={[
          { label: t("linkCheck.title"), href: `/library/${tableId}/link-check` },
          {
            label: t("breadcrumb.run", { id: rid }),
            href: `/library/${tableId}/link-check/runs/${rid}`,
          },
          { label: t("linkCheckRun.rawTableTitle") },
        ]}
      />

      <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
        {t("linkCheckRun.rawTableTitle")}
      </h1>
      <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        {t("linkCheckRun.rawTableSubtitle")}
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <select
          value={view}
          onChange={(e) => setView(e.target.value as TranslationTableView)}
          className="rounded-md border border-neutral-300 px-2 py-1.5 text-xs dark:border-neutral-700 dark:bg-neutral-900"
        >
          <option value="active">{t("linkCheckRun.rawViewActive")}</option>
          <option value="all">{t("linkCheckRun.rawViewAll")}</option>
          <option value="dismissed">{t("linkCheckRun.rawViewDismissed")}</option>
        </select>
        <select
          value={linkType}
          onChange={(e) => setLinkType(e.target.value as LinkTypeFilter)}
          className="rounded-md border border-neutral-300 px-2 py-1.5 text-xs dark:border-neutral-700 dark:bg-neutral-900"
        >
          <option value="all">{t("linkCheckRun.rawTypeAll")}</option>
          <option value="product">{t("linkCheckRun.rawTypeProduct")}</option>
          <option value="internal">{t("linkCheckRun.rawTypeInternal")}</option>
          <option value="external">{t("linkCheckRun.rawTypeExternal")}</option>
        </select>
        <span className="flex flex-wrap items-center gap-3 text-[11px] text-neutral-500 dark:text-neutral-400">
          <LegendDot cls="bg-emerald-500" label={t("linkCheckRun.rawLegendOk")} />
          <LegendDot cls="bg-red-500" label={t("linkCheckRun.rawLegendDiscrepancy")} />
          <LegendDot cls="bg-neutral-400" label={t("linkCheckRun.rawLegendInvented")} />
        </span>
      </div>

      {selectable && selected.size > 0 && (
        <div className="mt-3 flex items-center gap-3 rounded-md border border-violet-200 bg-violet-50 px-3 py-2 text-sm dark:border-violet-900/40 dark:bg-violet-950/20">
          <span className="text-violet-800 dark:text-violet-200">
            {t("linkCheckRun.selectedErrors", { n: selected.size })}
          </span>
          <button
            type="button"
            onClick={applyAction}
            disabled={busy}
            className="ml-auto rounded-md bg-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-700 disabled:opacity-60"
          >
            {view === "dismissed"
              ? t("linkCheckRun.restoreSelected", { n: selected.size })
              : t("linkCheckRun.dismissSelected", { n: selected.size })}
          </button>
        </div>
      )}

      {error && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {!error && (
        <>
          <div className="mt-3 overflow-x-auto rounded-lg border border-neutral-200 dark:border-neutral-800">
            <table className="w-full text-left text-xs">
              <thead className="bg-neutral-50 uppercase tracking-wide text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
                <tr>
                  <th className="px-3 py-2 font-medium">{t("linkCheckRun.colRow")}</th>
                  <th className="px-3 py-2 font-medium">{t("linkCheckRun.rawLang")}</th>
                  <th className="px-3 py-2 font-medium">{t("linkCheckRun.rawOriginal")}</th>
                  <th className="px-3 py-2 font-medium">{t("linkCheckRun.rawTranslation")}</th>
                  {/* Expected ↔ Discrepancy, aligned side by side */}
                  <th className="px-3 py-2 font-medium">
                    <div className="grid grid-cols-2 gap-x-4">
                      <span>{t("linkCheckRun.rawExpected")}</span>
                      <span className="inline-flex items-center gap-1.5">
                        {selectable && pageKeys.length > 0 && (
                          <input
                            type="checkbox"
                            checked={allSelected}
                            onChange={toggleAll}
                            title={t("linkCheckRun.selectAll")}
                            className="h-3.5 w-3.5 rounded border-neutral-300 dark:border-neutral-600"
                          />
                        )}
                        {t("linkCheckRun.rawMismatches")}
                      </span>
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
                {rows.map((r) => (
                  <tr key={r.row_id} className="align-top">
                    <td className="px-3 py-2 tabular-nums text-neutral-500">
                      #{r.row_position + 1}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap font-medium text-neutral-700 dark:text-neutral-300">
                      {r.lang || "—"}
                    </td>
                    <td className="px-3 py-2">
                      <PlainLinks links={r.original} cls="text-blue-600 dark:text-blue-400" />
                    </td>
                    <td className="px-3 py-2">
                      <TaggedLinks links={r.translation} />
                    </td>
                    <td className="px-3 py-2">
                      <AlignedGrid
                        rowId={r.row_id}
                        aligned={r.aligned}
                        selectable={selectable}
                        showType={linkType === "all"}
                        selected={selected}
                        toggle={toggle}
                      />
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && !loading && (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-3 py-4 text-center text-sm text-neutral-500 dark:text-neutral-400"
                    >
                      {view === "active"
                        ? t("linkCheckRun.rawTableEmptyDiscrepancies")
                        : view === "dismissed"
                          ? t("linkCheckRun.rawTableEmptyDismissed")
                          : t("linkCheckRun.rawTableEmpty")}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPage={setPage} />
        </>
      )}
    </main>
  );
}

function LegendDot({ cls, label }: { cls: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={"inline-block h-2 w-2 rounded-full " + cls} />
      {label}
    </span>
  );
}

function Dash() {
  return <span className="text-neutral-300 dark:text-neutral-600">—</span>;
}

function Anchor({ href, cls }: { href: string; cls: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={"break-all hover:underline " + cls}
    >
      {href}
    </a>
  );
}

function PlainLinks({ links, cls }: { links: string[]; cls: string }) {
  if (links.length === 0) return <Dash />;
  return (
    <ul className="space-y-2">
      {links.map((l, i) => (
        <li key={`${l}:${i}`}>
          <Anchor href={l} cls={cls} />
        </li>
      ))}
    </ul>
  );
}

function TaggedLinks({ links }: { links: TranslationLinkTag[] }) {
  if (links.length === 0) return <Dash />;
  return (
    <ul className="space-y-2">
      {links.map((l, i) => (
        <li key={`${l.url}:${i}`}>
          <Anchor href={l.url} cls={kindCls(l.kind) + (l.dismissed ? " opacity-50" : "")} />
        </li>
      ))}
    </ul>
  );
}

/** Expected ↔ wrong as a 2-col grid: each aligned entry is one grid row, so
 *  the red wrong link sits next to the expected link it should have been. */
function TypeChip({ type }: { type: TranslationTableRow["aligned"][number]["link_type"] }) {
  const { t } = useT();
  const label =
    type === "product"
      ? t("linkCheckRun.rawTypeProduct")
      : type === "internal"
        ? t("linkCheckRun.rawTypeInternal")
        : t("linkCheckRun.rawTypeExternal");
  return (
    <span className="mr-1.5 rounded bg-neutral-100 px-1 py-0.5 text-[10px] uppercase tracking-wide text-neutral-500 dark:bg-neutral-800 dark:text-neutral-400">
      {label}
    </span>
  );
}

function AlignedGrid({
  rowId,
  aligned,
  selectable,
  showType,
  selected,
  toggle,
}: {
  rowId: number;
  aligned: TranslationTableRow["aligned"];
  selectable: boolean;
  showType: boolean;
  selected: Set<string>;
  toggle: (k: string) => void;
}) {
  if (aligned.length === 0) return <Dash />;
  return (
    <div className="grid grid-cols-2 items-start gap-x-4 gap-y-2">
      {aligned.map((a, i) => {
        const w = a.wrong;
        const k = w ? errKey(rowId, w.url) : "";
        return (
          <Fragment key={i}>
            <div>
              {showType && <TypeChip type={a.link_type} />}
              {a.expected ? <Anchor href={a.expected} cls={GREEN} /> : <Dash />}
            </div>
            <div>
              {w ? (
                <span className="flex items-start gap-1.5">
                  {selectable && (
                    <input
                      type="checkbox"
                      checked={selected.has(k)}
                      onChange={() => toggle(k)}
                      className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded border-neutral-300 dark:border-neutral-600"
                    />
                  )}
                  <Anchor href={w.url} cls={kindCls(w.kind) + (w.dismissed ? " opacity-50" : "")} />
                </span>
              ) : (
                <Dash />
              )}
            </div>
          </Fragment>
        );
      })}
    </div>
  );
}
