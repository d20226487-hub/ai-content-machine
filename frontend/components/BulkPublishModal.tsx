"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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
  clearMappingMulti,
  clearMappingSingle,
  createBulkRun,
  getMappingMulti,
  getMappingSingle,
  type BulkPublishPayload,
  type CellFilter,
  type OnSlugConflict,
  type PublishLookupKind,
  type PublishMode,
  type PublishOperation,
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
  // Outside-click guard: flips true on the first form interaction. We
  // intentionally don't auto-save on outside-click here — submitting kicks
  // off a real publish run, and that's not the kind of side effect we want
  // a stray click to commit.
  const [touched, setTouched] = useState(false);

  // Mode is the top-level switch. Soft preserve on toggle: mapping/filters/
  // back-fill carry across modes; only the mode-specific target fields reset.
  const [mode, setMode] = useState<PublishMode>("single");

  const [domains, setDomains] = useState<Domain[] | null>(null);
  // Single-mode targets
  const [domainId, setDomainId] = useState<number | null>(null);
  const [profileName, setProfileName] = useState<string | null>(null);
  // Multi-mode targets
  const [domainColumnId, setDomainColumnId] = useState<number | "">("");
  const [profileColumnId, setProfileColumnId] = useState<number | "">("");
  // Multi-mode optional per-row language column. When set, the run-level
  // language picker only acts as a label / fallback display — every row
  // must have a value (strict mode: empty cell fails the row).
  const [languageColumnId, setLanguageColumnId] = useState<number | "">("");

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

  // Create vs Update. Update mode resolves each row to an existing WP post
  // (via lookupColumnId + lookupKind) and PATCHes it. WP-only — Custom CMS
  // is blocked at submit time in single mode and per-row at runtime in multi.
  const [operation, setOperation] = useState<PublishOperation>("create");
  const [lookupKind, setLookupKind] = useState<PublishLookupKind>("id");
  const [lookupColumnId, setLookupColumnId] = useState<number | "">("");

  // Create-mode only: what to do when the row's slug already exists on
  // the target (in the row's effective language).
  const [onSlugConflict, setOnSlugConflict] =
    useState<OnSlugConflict>("create");

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

  // In multi mode the field map applies to every row regardless of domain.
  // We use the first WP domain's first profile as the canonical schema —
  // the user's stated invariant is that all sites share the same fields.
  const multiCanonicalProfile = useMemo<PublishProfile | null>(() => {
    if (mode !== "multi") return null;
    const wp = (domains ?? []).find((d) => d.cms_type === "wordpress");
    if (!wp) return null;
    const profiles = wp.publish_config?.profiles;
    if (profiles && profiles.length > 0) return profiles[0];
    return { name: "Default", post_type: "posts", fields: DEFAULT_WP_FIELDS };
  }, [mode, domains]);

  // Compute the set of field "slots" the user must map columns to.
  const slots: FieldSlot[] = useMemo(() => {
    if (mode === "multi") {
      const fields = multiCanonicalProfile?.fields ?? DEFAULT_WP_FIELDS;
      return fields.map((f) => ({
        key: f.key,
        label: f.label || f.key,
        required: !!f.required,
      }));
    }
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
  }, [mode, multiCanonicalProfile, selected, activeProfile]);

  // Pick default profile for single-WP when selected domain changes.
  useEffect(() => {
    if (mode !== "single" || !selected) return;
    setLanguage(selected.languages[0] ?? "en");
    if (selected.cms_type === "wordpress") {
      const profileNames = wpProfiles.map((p) => p.name);
      setProfileName((cur) =>
        cur && profileNames.includes(cur) ? cur : profileNames[0] ?? null,
      );
    } else {
      setProfileName(null);
    }
  }, [mode, selected, wpProfiles]);

  // Load saved mapping when key changes (single mode: domain+profile; multi: just table).
  //
  // Soft preserve: skip the load when the only thing that changed was `mode`.
  // Without this guard the effect would re-fetch on every Single↔Multi toggle
  // and clobber whatever the user had just filled in. Tracked via a ref so
  // we can detect "previous mode != current mode" without that creating yet
  // another effect dep.
  //
  // Domain-switch preserve: when the user picks a different site/profile, any
  // mappings they've already typed for fields that exist in the new schema
  // are kept (merged on field-key). Only fields the new domain doesn't expose
  // get dropped. Without this, every domain re-pick wiped the entire mapping
  // section above the picker — the "annoying refresh" complaint.
  const prevModeRef = useRef<PublishMode>(mode);
  // `slotsRef` lets the async server-load callback see the slots from the
  // SAME render that triggered the effect (the new domain's fields), so it
  // can drop mappings that no longer have a matching slot.
  const slotsRef = useRef(slots);
  slotsRef.current = slots;
  // Tracks whether the user has explicitly touched the Create/Update toggle,
  // lookup-kind, or on-slug-conflict knob. Without this, picking a different
  // domain would replay the server's saved value over the user's intent —
  // e.g. you set Update, switch sites, and the toggle flips back to Create
  // because the new (table, domain, profile) triple has 'create' on file.
  const userTouchedRef = useRef({
    operation: false,
    lookupKind: false,
    onSlugConflict: false,
  });
  function setOperationTouched(op: PublishOperation): void {
    userTouchedRef.current.operation = true;
    setOperation(op);
  }
  function setLookupKindTouched(k: PublishLookupKind): void {
    userTouchedRef.current.lookupKind = true;
    setLookupKind(k);
  }
  function setOnSlugConflictTouched(o: OnSlugConflict): void {
    userTouchedRef.current.onSlugConflict = true;
    setOnSlugConflict(o);
  }
  useEffect(() => {
    const modeChanged = prevModeRef.current !== mode;
    prevModeRef.current = mode;
    // Soft preserve: a mode toggle alone never refetches.
    if (modeChanged) return;

    // Merge helper: prefer user-current entry for every field key that
    // still exists in the new schema; fill the rest from the server.
    const mergeFieldMap = (
      serverMap: Record<string, number> | undefined,
    ) => {
      setFieldToColumn((current) => {
        const next: Record<string, number> = {};
        const slotKeys = new Set(slotsRef.current.map((s) => s.key));
        // Belt: keep user-typed mappings for any slot still in the schema.
        for (const k of slotKeys) {
          if (current[k] != null) next[k] = current[k];
          else if (serverMap && serverMap[k] != null) next[k] = serverMap[k];
        }
        return next;
      });
    };

    if (mode === "single") {
      if (!selected) {
        setFieldToColumn({});
        setPostIdTarget("");
        setPostUrlTarget("");
        return;
      }
      getMappingSingle(table.id, selected.id, profileName)
        .then((m) => {
          mergeFieldMap(m.field_to_column);
          // Back-fill target columns: keep user's current pick if any —
          // column IDs are table-scoped, not domain-scoped, so they
          // remain valid across domain switches.
          setPostIdTarget((cur) =>
            cur !== ""
              ? cur
              : (m.back_fill?.post_id_target as number | undefined) ?? "",
          );
          setPostUrlTarget((cur) =>
            cur !== ""
              ? cur
              : (m.back_fill?.post_url_target as number | undefined) ?? "",
          );
          if (m.language) setLanguage(m.language);
          // Restore the last operation + lookup choice for this (table,
          // domain, profile) so re-running an update on the same triple
          // doesn't need re-picking the column.
          // Only seed these from the server when the user hasn't explicitly
          // touched them in this modal session. Once they pick "Update" by
          // hand, switching domains shouldn't roll it back to "Create".
          if (m.operation && !userTouchedRef.current.operation) {
            setOperation(m.operation);
          }
          if (m.lookup_kind && !userTouchedRef.current.lookupKind) {
            setLookupKind(m.lookup_kind);
          }
          setLookupColumnId((cur) =>
            cur !== ""
              ? cur
              : typeof m.lookup_column_id === "number" ? m.lookup_column_id : "",
          );
          if (m.on_slug_conflict && !userTouchedRef.current.onSlugConflict) {
            setOnSlugConflict(m.on_slug_conflict);
          }
        })
        .catch(() => {
          // Server lookup failed — still drop fields that don't exist in
          // the new schema, but keep everything the user typed for slots
          // that DO exist. Passing `undefined` here is intentional.
          mergeFieldMap(undefined);
        });
    } else {
      getMappingMulti(table.id)
        .then((m) => {
          mergeFieldMap(m.field_to_column);
          setPostIdTarget((cur) =>
            cur !== ""
              ? cur
              : (m.back_fill?.post_id_target as number | undefined) ?? "",
          );
          setPostUrlTarget((cur) =>
            cur !== ""
              ? cur
              : (m.back_fill?.post_url_target as number | undefined) ?? "",
          );
          if (m.language) setLanguage(m.language);
          if (typeof m.domain_column_id === "number") setDomainColumnId(m.domain_column_id);
          if (typeof m.profile_column_id === "number") setProfileColumnId(m.profile_column_id);
          setLanguageColumnId(
            typeof m.language_column_id === "number" ? m.language_column_id : "",
          );
          // Only seed these from the server when the user hasn't explicitly
          // touched them in this modal session. Once they pick "Update" by
          // hand, switching domains shouldn't roll it back to "Create".
          if (m.operation && !userTouchedRef.current.operation) {
            setOperation(m.operation);
          }
          if (m.lookup_kind && !userTouchedRef.current.lookupKind) {
            setLookupKind(m.lookup_kind);
          }
          setLookupColumnId((cur) =>
            cur !== ""
              ? cur
              : typeof m.lookup_column_id === "number" ? m.lookup_column_id : "",
          );
          if (m.on_slug_conflict && !userTouchedRef.current.onSlugConflict) {
            setOnSlugConflict(m.on_slug_conflict);
          }
        })
        .catch(() => {
          // No saved multi mapping yet — fine.
        });
    }
  }, [mode, selected, profileName, table.id]);

  // Soft-preserve toggle: clear only mode-specific target fields when mode changes.
  function onModeChange(next: PublishMode) {
    if (next === mode) return;
    setMode(next);
    if (next === "multi") {
      // Leaving single → clear single-mode targets; multi-mode columns load
      // from saved mapping in the effect above.
      setProfileName(null);
    } else {
      // Leaving multi → clear multi-mode column refs; domain dropdown will
      // reset to the first credentialled option already-loaded in `domains`.
      setDomainColumnId("");
      setProfileColumnId("");
      // languageColumnId stays: per-row language column works in both
      // modes now, so flipping single↔multi shouldn't drop the picker.
    }
    // Mapping / filters / back-fill stay (intentional — soft preserve).
  }

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

  // Multi-mode: count distinct domain values across the candidate rows.
  const multiBreakdown = useMemo(() => {
    if (mode !== "multi" || domainColumnId === "") return null;
    const colId = Number(domainColumnId);

    let candidateIds: Set<number>;
    if (rowFilter === "selected") {
      candidateIds = new Set(selectedRowIds);
    } else if (rowFilter === "range") {
      const s = Math.max(1, Number(rangeStart) || 1) - 1;
      const e = Math.max(0, Number(rangeEnd) || 0);
      candidateIds = new Set(table.rows.slice(s, e).map((r) => r.id));
    } else {
      candidateIds = new Set(table.rows.map((r) => r.id));
    }
    if (cellFilter !== "all" && postIdTarget !== "") {
      const filterColId = Number(postIdTarget);
      const filled: Record<number, string> = {};
      for (const c of table.cells) {
        if (c.column_id === filterColId) filled[c.row_id] = c.value || "";
      }
      for (const rid of Array.from(candidateIds)) {
        if (filled[rid]) candidateIds.delete(rid);
      }
    }

    const counts = new Map<string, number>();
    for (const cell of table.cells) {
      if (cell.column_id !== colId) continue;
      if (!candidateIds.has(cell.row_id)) continue;
      const v = (cell.value || "").trim() || "(empty)";
      counts.set(v, (counts.get(v) ?? 0) + 1);
    }
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([name, count]) => ({ name, count }));
  }, [mode, domainColumnId, rowFilter, rangeStart, rangeEnd, cellFilter, postIdTarget, selectedRowIds, table]);

  function setSlot(key: string, colId: number | null) {
    setFieldToColumn((m) => {
      const next = { ...m };
      if (colId == null) delete next[key];
      else next[key] = colId;
      return next;
    });
  }

  async function onClear() {
    if (!confirm(t("bulkPub.confirmClearMapping"))) return;
    try {
      if (mode === "single" && selected) {
        await clearMappingSingle(table.id, selected.id, profileName);
      } else if (mode === "multi") {
        await clearMappingMulti(table.id);
      }
      setFieldToColumn({});
      setPostIdTarget("");
      setPostUrlTarget("");
      if (mode === "multi") {
        setDomainColumnId("");
        setProfileColumnId("");
        setLanguageColumnId("");
      }
      // Reset the operation knob to defaults too, since "Clear saved mapping"
      // means "forget everything I remembered for this target". Also clear
      // the touched flags so a subsequent domain switch can seed from the
      // (now-empty) server state instead of sticking on these defaults.
      userTouchedRef.current = {
        operation: false,
        lookupKind: false,
        onSlugConflict: false,
      };
      setOperation("create");
      setLookupKind("id");
      setLookupColumnId("");
      setOnSlugConflict("create");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("domainMod.clearCacheFailed"));
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (mode === "single" && !selected) return;

    // Update mode is WP-only. Catch single-mode + Custom CMS here so the
    // user gets a clear message before the request goes out.
    if (
      operation === "update" &&
      mode === "single" &&
      selected &&
      selected.cms_type !== "wordpress"
    ) {
      setError(t("bulkPub.updateWpOnly", { name: selected.name }));
      return;
    }

    if (operation === "update" && lookupColumnId === "") {
      setError(t("bulkPub.updateLookupRequired"));
      return;
    }

    if (
      operation === "create" &&
      onSlugConflict !== "create" &&
      !("slug" in fieldToColumn)
    ) {
      setError(t("bulkPub.slugConflictNeedsSlug"));
      return;
    }

    // Validate required slots are mapped. In Update mode required slots are
    // softer ("title" doesn't have to be set when you're patching just the
    // content) but we still want the user to have mapped at least one field
    // worth sending.
    if (operation === "update" && Object.keys(fieldToColumn).length === 0) {
      setError(t("bulkPub.updateMapAtLeastOne"));
      return;
    }
    const missing =
      operation === "create"
        ? slots.filter((s) => s.required && fieldToColumn[s.key] == null)
        : [];
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
      mode,
      language,
      row_filter: rowFilter,
      selection,
      cell_filter: cellFilter,
      field_to_column: fieldToColumn,
      back_fill,
      save_mapping: saveMapping,
      operation,
    };

    if (operation === "update") {
      payload.lookup_kind = lookupKind;
      payload.lookup_column_id = Number(lookupColumnId);
    } else {
      // Slug-conflict handling lives on Create only. Server rejects
      // mixing this with operation='update', so we just don't send it
      // for Update runs.
      payload.on_slug_conflict = onSlugConflict;
    }

    if (mode === "single") {
      payload.domain_id = selected!.id;
      payload.profile_name = profileName;
    } else {
      payload.domain_column_id = Number(domainColumnId);
      payload.profile_column_id =
        profileColumnId !== "" ? Number(profileColumnId) : null;
    }
    // Per-row language column works in both modes — read the cell and
    // validate against the resolved domain's languages[]. Sent always
    // when set; the server uses run.language as fallback when null.
    payload.language_column_id =
      languageColumnId !== "" ? Number(languageColumnId) : null;

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
  // In multi mode, the publish button needs a domain column picked (and the
  // standard required-field mapping). Profile column is optional — falls back
  // to the domain's default profile when omitted.
  const publishDisabled =
    busy ||
    candidatePreview === 0 ||
    (mode === "single" && !selected) ||
    (mode === "multi" && domainColumnId === "");

  return (
    <Modal onClose={onClose} size="max-w-3xl" dirty={touched}>
      <form
        onSubmit={onSubmit}
        onChange={() => {
          if (!touched) setTouched(true);
        }}
        className="space-y-4"
      >
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

        {/* Mode toggle */}
        <div>
          <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            {t("bulkPub.mode")}
          </span>
          <div className="inline-flex rounded-md border border-neutral-300 p-0.5 dark:border-neutral-700">
            {(["single", "multi"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => onModeChange(m)}
                className={
                  "rounded px-3 py-1 text-sm font-medium transition-colors " +
                  (mode === m
                    ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                    : "text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100")
                }
              >
                {m === "single" ? t("bulkPub.modeSingle") : t("bulkPub.modeMulti")}
              </button>
            ))}
          </div>
          <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            {mode === "single" ? t("bulkPub.modeSingleHint") : t("bulkPub.modeMultiHint")}
          </p>
        </div>

        {/* Operation toggle: Create vs Update. */}
        <div>
          <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            {t("bulkPub.operation")}
          </span>
          <div className="inline-flex rounded-md border border-neutral-300 p-0.5 dark:border-neutral-700">
            {(["create", "update"] as const).map((op) => (
              <button
                key={op}
                type="button"
                onClick={() => setOperationTouched(op)}
                className={
                  "rounded px-3 py-1 text-sm font-medium transition-colors " +
                  (operation === op
                    ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                    : "text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100")
                }
              >
                {op === "create"
                  ? t("bulkPub.opCreate")
                  : t("bulkPub.opUpdate")}
              </button>
            ))}
          </div>
          <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            {operation === "create"
              ? t("bulkPub.opCreateHint")
              : t("bulkPub.opUpdateHint")}
          </p>
        </div>

        {/* Create mode: what to do when a row's slug already exists. */}
        {operation === "create" && (
          <div className="rounded-md border border-neutral-200 bg-neutral-50 p-3 dark:border-neutral-800 dark:bg-neutral-800/30">
            <Field label={t("bulkPub.onSlugConflict")}>
              <div className="inline-flex rounded-md border border-neutral-300 bg-white p-0.5 dark:border-neutral-700 dark:bg-neutral-900">
                {(["create", "skip", "update"] as const).map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setOnSlugConflictTouched(opt)}
                    className={
                      "rounded px-3 py-1 text-xs font-medium transition-colors " +
                      (onSlugConflict === opt
                        ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                        : "text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100")
                    }
                  >
                    {opt === "create"
                      ? t("bulkPub.onSlugCreate")
                      : opt === "skip"
                      ? t("bulkPub.onSlugSkip")
                      : t("bulkPub.onSlugUpdate")}
                  </button>
                ))}
              </div>
            </Field>
            <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
              {onSlugConflict === "create"
                ? t("bulkPub.onSlugCreateHint")
                : onSlugConflict === "skip"
                ? t("bulkPub.onSlugSkipHint")
                : t("bulkPub.onSlugUpdateHint")}
            </p>
            {onSlugConflict !== "create" && !("slug" in fieldToColumn) && (
              <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
                {t("bulkPub.slugConflictNeedsSlug")}
              </p>
            )}
          </div>
        )}

        {/* Update mode: look-up controls. */}
        {operation === "update" && (
          <div className="rounded-md border border-neutral-200 bg-neutral-50 p-3 dark:border-neutral-800 dark:bg-neutral-800/30">
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("bulkPub.lookupKind")}>
                <div className="inline-flex rounded-md border border-neutral-300 bg-white p-0.5 dark:border-neutral-700 dark:bg-neutral-900">
                  {(["id", "slug"] as const).map((k) => (
                    <button
                      key={k}
                      type="button"
                      onClick={() => setLookupKindTouched(k)}
                      className={
                        "rounded px-3 py-1 text-xs font-medium transition-colors " +
                        (lookupKind === k
                          ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                          : "text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100")
                      }
                    >
                      {k === "id" ? t("bulkPub.lookupKindId") : t("bulkPub.lookupKindSlug")}
                    </button>
                  ))}
                </div>
              </Field>
              <Field label={t("bulkPub.lookupColumn")}>
                <select
                  value={lookupColumnId}
                  onChange={(e) =>
                    setLookupColumnId(e.target.value === "" ? "" : Number(e.target.value))
                  }
                  className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                >
                  <option value="">— {t("bulkPub.lookupColumnPlaceholder")} —</option>
                  {table.columns.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <p className="mt-2 text-xs text-neutral-500 dark:text-neutral-400">
              {lookupKind === "id"
                ? t("bulkPub.lookupHintId")
                : t("bulkPub.lookupHintSlug")}
            </p>
            <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
              {t("bulkPub.updateBlankHint")}
            </p>
          </div>
        )}

        {/* Single-mode: Domain + Profile dropdowns */}
        {mode === "single" && (
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

            {/* Optional per-row language column for Single mode. Shown only
                when the selected domain advertises >1 language — for a
                single-language site this is just clutter. When set, the
                run-level Language picker above becomes the fallback for
                display; the actual language per row comes from the cell.
                Same strict semantics as multi-mode: empty cell fails the
                row, unknown value fails the row. */}
            {selected && selected.languages.length > 1 && (
              <Field label={t("bulkPub.fieldLanguageColumn")}>
                <select
                  value={languageColumnId}
                  onChange={(e) =>
                    setLanguageColumnId(e.target.value ? Number(e.target.value) : "")
                  }
                  className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                >
                  <option value="">{t("bulkPub.languageColumnDefault")}</option>
                  {eligibleColumns.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-[11px] text-neutral-500 dark:text-neutral-400">
                  {t("bulkPub.languageColumnHint")}
                </p>
              </Field>
            )}
          </div>
        )}

        {/* Multi-mode: column pickers */}
        {mode === "multi" && (
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("bulkPub.fieldDomainColumn")}>
              <select
                value={domainColumnId}
                onChange={(e) =>
                  setDomainColumnId(e.target.value ? Number(e.target.value) : "")
                }
                className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              >
                <option value="">{t("bulkPub.pickColumn")}</option>
                {eligibleColumns.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t("bulkPub.fieldProfileColumn")}>
              <select
                value={profileColumnId}
                onChange={(e) =>
                  setProfileColumnId(e.target.value ? Number(e.target.value) : "")
                }
                className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              >
                <option value="">{t("bulkPub.profileColumnDefault")}</option>
                {eligibleColumns.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-[11px] text-neutral-500 dark:text-neutral-400">
                {t("bulkPub.profileColumnHint")}
              </p>
            </Field>
            <Field label={t("bulkPub.fieldLanguageColumn")}>
              <select
                value={languageColumnId}
                onChange={(e) =>
                  setLanguageColumnId(e.target.value ? Number(e.target.value) : "")
                }
                className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              >
                <option value="">{t("bulkPub.languageColumnDefault")}</option>
                {eligibleColumns.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-[11px] text-neutral-500 dark:text-neutral-400">
                {t("bulkPub.languageColumnHint")}
              </p>
            </Field>
          </div>
        )}

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
        {(mode === "multi" || selected) && (
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
          {mode === "multi" && multiBreakdown ? (
            <div>
              <div className="font-medium">
                {operation === "update"
                  ? t("bulkPub.willUpdateAcross", {
                      count: candidatePreview,
                      domains: multiBreakdown.length,
                    })
                  : t("bulkPub.willPublishAcross", {
                      count: candidatePreview,
                      domains: multiBreakdown.length,
                    })}
              </div>
              {multiBreakdown.length > 0 && (
                <ul className="mt-1 max-h-32 overflow-auto text-xs">
                  {multiBreakdown.slice(0, 8).map((b) => (
                    <li key={b.name} className="flex justify-between gap-3">
                      <span className="truncate font-mono">{b.name}</span>
                      <span className="shrink-0 tabular-nums">{b.count}</span>
                    </li>
                  ))}
                  {multiBreakdown.length > 8 && (
                    <li className="text-blue-700/70 dark:text-blue-300/70">
                      {t("bulkPub.andMore", { count: multiBreakdown.length - 8 })}
                    </li>
                  )}
                </ul>
              )}
            </div>
          ) : operation === "update" ? (
            t("bulkPub.willUpdate", { count: candidatePreview })
          ) : (
            t("bulkPub.willPublish", { count: candidatePreview })
          )}
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
            disabled={publishDisabled}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900"
          >
            {busy
              ? t("bulkPub.starting")
              : operation === "update"
              ? t("bulkPub.startUpdate", { count: candidatePreview })
              : t("bulkPub.start", { count: candidatePreview })}
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
