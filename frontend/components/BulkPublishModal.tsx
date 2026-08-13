"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Modal } from "@/components/Modal";
import { BackFill } from "@/components/bulkPublish/BackFill";
import { CellFilter } from "@/components/bulkPublish/CellFilter";
import { CmsTypeSegmented } from "@/components/bulkPublish/CmsTypeSegmented";
import { CustomCmsActionPanel } from "@/components/bulkPublish/CustomCmsActionPanel";
import { CustomPageTypeSelector } from "@/components/bulkPublish/CustomPageTypeSelector";
import { FieldMapping } from "@/components/bulkPublish/FieldMapping";
import { LanguageSync } from "@/components/bulkPublish/LanguageSync";
import { MultiModeSection } from "@/components/bulkPublish/MultiModeSection";
import { RowFilter } from "@/components/bulkPublish/RowFilter";
import { SingleModeSection } from "@/components/bulkPublish/SingleModeSection";
import { WordPressOperationPanel } from "@/components/bulkPublish/WordPressOperationPanel";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  DEFAULT_WP_FIELDS,
  getDomain,
  listDomainsPicker,
  type CmsType,
  type Domain,
  type DomainPickerItem,
  type PublishProfile,
} from "@/lib/domains";
import {
  clearMappingMulti,
  clearMappingSingle,
  createBulkRun,
  getMappingMulti,
  getMappingSingle,
  MATCH_PAGE_FIELDS,
  type BulkPublishPayload,
  // Type aliases keep these distinct from the same-named components
  // we import from @/components/bulkPublish/* above.
  type CellFilter as CellFilterValue,
  type CustomPageType,
  type OnSlugConflict,
  type PublishLookupKind,
  type PublishMode,
  type PublishOperation,
  type RowFilter as RowFilterValue,
} from "@/lib/publishBulk";
import { getColumnValues, type ColumnValuesResponse } from "@/lib/library";
import type { BulkTable } from "@/lib/types";
import type { FieldSlot } from "@/components/bulkPublish/FieldMapping";

interface Props {
  table: BulkTable;
  /** Total rows in the whole table (the modal only holds the current page). */
  totalRowCount: number;
  /** True when the grid is in "select all N" mode. */
  allRowsSelected: boolean;
  selectedRowIds: number[];
  onClose: () => void;
}

export function BulkPublishModal({
  table,
  totalRowCount,
  allRowsSelected,
  selectedRowIds,
  onClose,
}: Props) {
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

  // Phase A: instead of preloading all domains (a problem at thousands of
  // sites), we now stream them on demand through the picker endpoint.
  //
  //   selectedFullDomain — the heavy `Domain` for the currently picked
  //     id. Fetched via `getDomain(id)` whenever `domainId` changes. The
  //     `selected` derivation below reads from this; `wpProfiles` and the
  //     per-domain Language picker both walk its `publish_config` /
  //     `languages`.
  //
  //   multiCanonicalDomain — fetched once when entering multi mode (the
  //     run uses the first WP domain's first profile as the canonical
  //     schema for field mapping). Null until that fetch lands.
  //
  //   selectedLabel — keeps the combobox input populated with the
  //     current pick even while `selectedFullDomain` is still in flight
  //     after a selection click, OR after the user reopens the modal
  //     with a stored domainId that hasn't been fetched yet.
  const [selectedFullDomain, setSelectedFullDomain] = useState<Domain | null>(null);
  const [multiCanonicalDomain, setMultiCanonicalDomain] = useState<Domain | null>(null);
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null);
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

  const [rowFilter, setRowFilter] = useState<RowFilterValue>(
    !allRowsSelected && selectedRowIds.length > 0 ? "selected" : "all",
  );
  const [rangeStart, setRangeStart] = useState<string>("1");
  const [rangeEnd, setRangeEnd] = useState<string>(String(totalRowCount));
  const [cellFilter, setCellFilter] = useState<CellFilterValue>("all");

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

  // Custom CMS built-in page type. 'ordinary' = each domain's own endpoint
  // + template (today's behavior); 'match' = hardcoded /add-sport-page +
  // sport field set. Custom-only; reset to 'ordinary' when the CMS-type
  // segmented control leaves Custom.
  const [customPageType, setCustomPageType] =
    useState<CustomPageType>("ordinary");

  // CMS-type segmented control at the top of the modal. Drives:
  //   - which CMS-specific panel renders (WP operation knobs vs Custom
  //     placeholder);
  //   - which domains the single-mode picker offers below.
  // Default seeded from the first credentialled domain on load; flipping
  // the control auto-picks the first matching domain so we never sit on
  // an inconsistent state where the segmented control says one thing and
  // `selected` says another.
  const [cmsTypeFilter, setCmsTypeFilter] = useState<CmsType>("wordpress");

  // Discovery fetch on mount: pick the right CMS-type default from
  // whatever the first credentialled domain is. The picker is ordered
  // credentialled-first, so items[0] is the natural default.
  //
  // Without this, a user whose entire fleet is Custom would land on the
  // WP-by-default segmented control and see an empty combobox until they
  // manually flipped to Custom. One small fetch avoids that papercut.
  useEffect(() => {
    listDomainsPicker({ page_size: 1 })
      .then((r) => {
        if (r.items.length > 0) {
          setCmsTypeFilter(r.items[0].cms_type);
        }
      })
      .catch((err) =>
        setLoadError(err instanceof ApiError ? err.message : t("pubMod.failedLoadDomains")),
      );
  }, [t]);

  // When the segmented control flips, the current selection (if any)
  // probably doesn't match the new type. Clear it; the combobox will
  // re-fetch with the new cms_type and the onResults callback below
  // auto-picks the first credentialled match.
  function onCmsTypeFilterChange(next: CmsType) {
    if (next === cmsTypeFilter) return;
    setCmsTypeFilter(next);
    setDomainId(null);
    setSelectedFullDomain(null);
    setSelectedLabel(null);
    // Page type is Custom-only; a WP run is always 'ordinary'.
    if (next !== "custom") setCustomPageType("ordinary");
  }

  // Page-type change. 'match' offers only create/update (no upsert endpoint),
  // so if the user had Upsert selected, fall back to Create when switching to
  // match. Otherwise the operation carries over unchanged.
  function onCustomPageTypeChange(next: CustomPageType) {
    setCustomPageType(next);
    userTouchedRef.current.customPageType = true;
    if (next === "match" && operation === "upsert") {
      userTouchedRef.current.operation = true;
      setOperation("create");
    }
  }

  // Called by the combobox after every fresh page of results. We use
  // this to seed the initial selection (and to re-seed after a
  // cmsType flip) — picking the first credentialled item if the parent
  // currently has no selection.
  const onPickerResults = useCallback(
    (items: DomainPickerItem[]) => {
      if (domainId != null) return;
      const pick = items.find((d) => d.has_credentials) ?? items[0] ?? null;
      if (!pick) return;
      setDomainId(pick.id);
      setSelectedLabel(pick.name);
    },
    [domainId],
  );

  // When the user explicitly picks a domain from the combobox, we have
  // the lite item immediately — store its label so the input stays
  // populated — and kick off a full Domain fetch so the WP profile
  // picker / language picker / publish_config-driven slots can render.
  function onDomainPicked(item: DomainPickerItem) {
    setDomainId(item.id);
    setSelectedLabel(item.name);
    // selectedFullDomain stays at the previous value until the fetch
    // below resolves; that's a brief flicker for the dependent UI but
    // not visible in practice (the fetch is sub-50ms on local Postgres).
  }

  // Fetch the heavy Domain whenever domainId changes (whether from the
  // combobox or an auto-pick). Latest-wins token guards against a
  // mid-flight stale result clobbering a newer selection.
  const fullDomainTokenRef = useRef(0);
  useEffect(() => {
    if (domainId == null) {
      setSelectedFullDomain(null);
      return;
    }
    const token = ++fullDomainTokenRef.current;
    getDomain(domainId)
      .then((d) => {
        if (token !== fullDomainTokenRef.current) return;
        setSelectedFullDomain(d);
        setSelectedLabel(d.name);
      })
      .catch((err) => {
        if (token !== fullDomainTokenRef.current) return;
        setLoadError(
          err instanceof ApiError ? err.message : t("pubMod.failedLoadDomains"),
        );
      });
  }, [domainId, t]);

  // The full domain record drives everything below — wpProfiles, language
  // pickers, custom_config-derived slot derivation. Kept as a separate
  // memo so the dependents don't have to re-check the loading state.
  const selected = selectedFullDomain;

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

  // Multi-mode field map applies to every row regardless of which
  // domain that row resolves to. We use the first credentialled domain
  // of the SELECTED CMS type as the canonical schema (the user's stated
  // invariant is that all sites of a given type share the same fields).
  //
  // Phase A: we no longer have all domains preloaded, so we fetch one
  // domain via the picker on entering multi mode. Cached in
  // `multiCanonicalDomain`; flipping the CMS-type segmented control
  // invalidates the cache so we re-fetch a matching domain — without
  // this reset, switching WP → Custom would keep showing the WP fields
  // (the original bug: Custom CMS Multi mode showed predefined WP slots).

  const multiCanonicalProfile = useMemo<PublishProfile | null>(() => {
    if (mode !== "multi") return null;
    if (!multiCanonicalDomain) return null;
    // Custom CMS has no profiles concept — return null and let the slot
    // derivation below take the body_template-placeholders branch.
    if (multiCanonicalDomain.cms_type !== "wordpress") return null;
    const profiles = multiCanonicalDomain.publish_config?.profiles;
    if (profiles && profiles.length > 0) return profiles[0];
    return { name: "Default", post_type: "posts", fields: DEFAULT_WP_FIELDS };
  }, [mode, multiCanonicalDomain]);

  // Compute the set of field "slots" the user must map columns to.
  const slots: FieldSlot[] = useMemo(() => {
    // 'match' page type pins a fixed endpoint + body template, so its field
    // schema is a constant — identical in single and multi mode regardless
    // of which domain a row resolves to. (This is why 'match' isn't subject
    // to the "multi mode reads one canonical domain's template" behavior.)
    if (cmsTypeFilter === "custom" && customPageType === "match") {
      return MATCH_PAGE_FIELDS.map((k) => ({
        key: k,
        label: k,
        required: false,
      }));
    }
    if (mode === "multi") {
      // Custom CMS Multi mode: pull placeholders from the canonical
      // Custom CMS domain's body_template, not WP fields. Bug fix —
      // the previous version always rendered DEFAULT_WP_FIELDS in
      // Multi mode even when the user had picked Custom CMS.
      if (
        cmsTypeFilter === "custom" &&
        multiCanonicalDomain?.cms_type === "custom"
      ) {
        const placeholders = collectPlaceholders(
          multiCanonicalDomain.custom_config?.body_template,
        );
        return placeholders
          .filter((p) => p !== "language")
          .map((p) => ({ key: p, label: p, required: false }));
      }
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
  }, [mode, cmsTypeFilter, customPageType, multiCanonicalDomain, multiCanonicalProfile, selected, activeProfile]);

  // When `slots` resolves to empty, render a context-specific reason in
  // the FieldMapping panel instead of the generic
  // "no fields detected" copy. Two realistic causes for an empty list,
  // both surface here with a clear next step:
  //   1. Custom CMS domain whose body_template has no {{placeholders}}.
  //      (Real example: 'lang-single-test' with body_template={x:y}
  //      auto-picked by alphabetical order — user couldn't figure out
  //      why fields disappeared until I traced the picker order.)
  //   2. Multi mode with no WP domain on the account to derive the
  //      canonical schema from — falls back to DEFAULT_WP_FIELDS via
  //      `slots` above, so this branch is theoretical today.
  const mappingEmptyMessage = useMemo<string | null>(() => {
    if (slots.length > 0) return null;
    if (mode === "single" && selected?.cms_type === "custom") {
      return t("bulkPub.noFieldsCustomEmpty", { name: selected.name });
    }
    return null; // FieldMapping falls back to the generic key
  }, [slots.length, mode, selected, t]);

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
    customPageType: false,
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
          // Legacy back-compat: Custom CMS Update used to encode the
          // upstream post-id as field_to_column['id'] — there was no
          // lookup_column_id in the old payload. Migrate transparently
          // so saved mappings from the old UI surface in the new
          // "Find existing posts by" picker without the user having
          // to re-pick the column. Only fires for Custom CMS Update;
          // leaves WP and Create/Upsert mappings alone.
          const legacyCustomId =
            selected?.cms_type === "custom" &&
            m.operation === "update" &&
            typeof (m.field_to_column as Record<string, unknown> | undefined)?.id === "number"
              ? ((m.field_to_column as Record<string, number>).id as number)
              : null;
          if (!userTouchedRef.current.lookupKind) {
            if (m.lookup_kind) setLookupKind(m.lookup_kind);
            else if (legacyCustomId !== null) setLookupKind("id");
          }
          setLookupColumnId((cur) => {
            if (cur !== "") return cur;
            if (typeof m.lookup_column_id === "number") return m.lookup_column_id;
            if (legacyCustomId !== null) return legacyCustomId;
            return "";
          });
          if (m.on_slug_conflict && !userTouchedRef.current.onSlugConflict) {
            setOnSlugConflict(m.on_slug_conflict);
          }
          if (m.custom_page_type && !userTouchedRef.current.customPageType) {
            setCustomPageType(m.custom_page_type);
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
          // Legacy back-compat (same migration as the single-mode branch
          // above): if the saved multi mapping is a Custom-CMS Update
          // that encoded the id via field_to_column['id'], lift it into
          // the new lookup_column_id. cmsTypeFilter scope lets us
          // restrict to Custom; for mixed-CMS tables the bridge runs
          // server-side regardless and the extra body key is harmless
          // for WP rows.
          const legacyCustomId =
            cmsTypeFilter === "custom" &&
            m.operation === "update" &&
            typeof (m.field_to_column as Record<string, unknown> | undefined)?.id === "number"
              ? ((m.field_to_column as Record<string, number>).id as number)
              : null;
          if (!userTouchedRef.current.lookupKind) {
            if (m.lookup_kind) setLookupKind(m.lookup_kind);
            else if (legacyCustomId !== null) setLookupKind("id");
          }
          setLookupColumnId((cur) => {
            if (cur !== "") return cur;
            if (typeof m.lookup_column_id === "number") return m.lookup_column_id;
            if (legacyCustomId !== null) return legacyCustomId;
            return "";
          });
          if (m.on_slug_conflict && !userTouchedRef.current.onSlugConflict) {
            setOnSlugConflict(m.on_slug_conflict);
          }
          if (m.custom_page_type && !userTouchedRef.current.customPageType) {
            setCustomPageType(m.custom_page_type);
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

  // ---- Lightweight per-column values for the previews ----
  //
  // The previews only ever reference up to three columns (post-id target,
  // domain column, language column). Server-side pagination means the modal
  // no longer holds every cell, so we fetch JUST those columns' values (plus
  // the ordered row list, for ranges) from the column-values endpoint. The
  // heavy output cells are never loaded here.
  const neededColumnIds = useMemo(() => {
    const ids = new Set<number>();
    if (postIdTarget !== "") ids.add(Number(postIdTarget));
    if (domainColumnId !== "") ids.add(Number(domainColumnId));
    if (languageColumnId !== "") ids.add(Number(languageColumnId));
    return Array.from(ids).sort((a, b) => a - b);
  }, [postIdTarget, domainColumnId, languageColumnId]);

  const [colValues, setColValues] = useState<ColumnValuesResponse | null>(null);
  const neededKey = neededColumnIds.join(",");
  useEffect(() => {
    let ignored = false;
    getColumnValues(table.id, neededColumnIds)
      .then((r) => {
        if (!ignored) setColValues(r);
      })
      .catch((e) => {
        console.error("[BulkPublish] column-values load failed", e);
        if (!ignored) setColValues({ rows: [], values: {} });
      });
    return () => {
      ignored = true;
    };
    // neededKey captures the column set; table.id captures the table.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [table.id, neededKey]);

  // Ordered row ids for range slicing, and a value getter. Both come from the
  // lite column-values payload (position-ordered server-side).
  const orderedRowIds = useMemo(
    () => (colValues?.rows ?? []).map((r) => r.id),
    [colValues],
  );
  const getVal = useCallback(
    (rowId: number, colId: number): string =>
      colValues?.values?.[rowId]?.[colId] ?? "",
    [colValues],
  );

  // Resolve the candidate row ids for a given filter state from the lite
  // ordered-row list (range/all) or the explicit selection.
  const resolveCandidateIds = useCallback((): number[] => {
    if (rowFilter === "selected") return selectedRowIds.slice();
    if (rowFilter === "range") {
      const s = Math.max(1, Number(rangeStart) || 1) - 1;
      const e = Math.max(0, Number(rangeEnd) || 0);
      return orderedRowIds.slice(s, e);
    }
    return orderedRowIds.slice();
  }, [rowFilter, rangeStart, rangeEnd, selectedRowIds, orderedRowIds]);

  // The domain the mapping schema is read from: the FIRST domain named in the
  // table's domain column. Reading it from the table (rather than "whatever
  // domain the picker returns first") means the slots are the fields this
  // run's fleet actually uses — an unrelated domain with a fat body_template
  // would otherwise fill the mapping with fields that are never published.
  const firstTableDomain = useMemo(() => {
    if (mode !== "multi" || domainColumnId === "") return "";
    const colId = Number(domainColumnId);
    for (const rid of resolveCandidateIds()) {
      const v = getVal(rid, colId).trim();
      if (v) return v;
    }
    return "";
  }, [mode, domainColumnId, resolveCandidateIds, getVal]);

  const multiCanonicalTokenRef = useRef(0);
  // What the cached canonical domain was fetched for. Re-fetch when either the
  // CMS type or the table's first domain changes; without this the schema
  // would stay pinned to the first domain seen when the modal opened.
  const multiCanonicalKeyRef = useRef<string | null>(null);
  useEffect(() => {
    if (mode !== "multi") return;
    // Invalidate stale cache when the user flips CMS-type while in Multi
    // mode: a previously-fetched WP domain isn't a valid schema source
    // for a Custom CMS run and vice versa.
    if (multiCanonicalDomain && multiCanonicalDomain.cms_type !== cmsTypeFilter) {
      setMultiCanonicalDomain(null);
      multiCanonicalKeyRef.current = null;
      return; // wait for the next effect run after state settles
    }
    const wantKey = `${cmsTypeFilter}|${firstTableDomain}`;
    if (multiCanonicalDomain && multiCanonicalKeyRef.current === wantKey) return;
    const token = ++multiCanonicalTokenRef.current;
    multiCanonicalKeyRef.current = wantKey;

    const pickFirstOfType = () =>
      listDomainsPicker({ cms_type: cmsTypeFilter, page_size: 1 });

    // Search by the table's value first; fall back to any domain of this type
    // when no column is chosen yet, or the value matches nothing (typo, or the
    // site hasn't been added) — an empty mapping would be worse than one
    // derived from a sibling site.
    const lookup = firstTableDomain
      ? listDomainsPicker({
          cms_type: cmsTypeFilter,
          q: firstTableDomain,
          page_size: 1,
        }).then((r) => (r.items.length > 0 ? r : pickFirstOfType()))
      : pickFirstOfType();

    lookup
      .then((r) => {
        if (token !== multiCanonicalTokenRef.current) return;
        if (r.items.length === 0) return; // no domain of this type → fallback fields
        return getDomain(r.items[0].id).then((d) => {
          if (token !== multiCanonicalTokenRef.current) return;
          setMultiCanonicalDomain(d);
        });
      })
      .catch(() => {
        // Non-fatal — the slot derivation falls back below.
      });
  }, [mode, cmsTypeFilter, multiCanonicalDomain, firstTableDomain]);

  // "Will publish N rows" estimate.
  const candidatePreview = useMemo(() => {
    let candidates = resolveCandidateIds();
    if (cellFilter !== "all" && postIdTarget !== "") {
      const colId = Number(postIdTarget);
      candidates = candidates.filter((rid) => !getVal(rid, colId));
    }
    return candidates.length;
  }, [resolveCandidateIds, cellFilter, postIdTarget, getVal]);

  // Multi-mode: count distinct domain values across the candidate rows.
  const multiBreakdown = useMemo(() => {
    if (mode !== "multi" || domainColumnId === "") return null;
    const colId = Number(domainColumnId);

    let candidateIds = resolveCandidateIds();
    if (cellFilter !== "all" && postIdTarget !== "") {
      const filterColId = Number(postIdTarget);
      candidateIds = candidateIds.filter((rid) => !getVal(rid, filterColId));
    }

    const counts = new Map<string, number>();
    for (const rid of candidateIds) {
      const v = getVal(rid, colId).trim() || "(empty)";
      counts.set(v, (counts.get(v) ?? 0) + 1);
    }
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([name, count]) => ({ name, count }));
  }, [mode, domainColumnId, resolveCandidateIds, cellFilter, postIdTarget, getVal]);

  // Language-sync targets — drives the LanguageSync pre-flight panel.
  //
  // Built by walking the candidate rows once and grouping each row's
  // language value under its domain value. Empty cells in either column
  // are skipped here on purpose — the sync UI is meant as a quick win,
  // not a row-by-row validation pass; bad rows will get caught later by
  // the actual publish.
  //
  // Custom-CMS-only by design: the upstream `/index.php?__add_language=1`
  // endpoint only exists on the user's Custom CMS sites. The backend
  // also filters non-Custom domains as a `skipped` result, but cutting
  // them client-side keeps the preview honest — no false promises.
  const languageSyncTargets = useMemo<
    { domain_name: string; languages: string[] }[]
  >(() => {
    // Custom-CMS-only by design (the upstream endpoint doesn't exist on
    // WP sites). Single mode has a chosen domain + either a language
    // column (per-row) OR the run-level language picker — fall back to
    // the run-level when there's no column. Multi mode requires both
    // columns (domain + language) as before; without them we can't tell
    // which languages go to which site.
    if (cmsTypeFilter !== "custom") return [];

    if (mode === "single") {
      // Single mode: one target — the picked domain. Languages come from
      // (a) the language column if set [unique values across candidate
      // rows], or (b) the run-level language picker as a single-element
      // list. If neither is set or the domain isn't loaded, nothing to do.
      if (!selected) return [];
      // Belt: don't surface for a domain that's somehow not Custom CMS.
      if (selected.cms_type !== "custom") return [];

      if (languageColumnId !== "") {
        const langs = collectCandidateLanguages(
          Number(languageColumnId),
          resolveCandidateIds(),
          getVal,
          cellFilter,
          postIdTarget,
        );
        if (langs.length === 0) return [];
        return [{ domain_name: selected.name, languages: langs }];
      }
      const runLang = (language || "").trim().toLowerCase();
      if (!runLang) return [];
      return [{ domain_name: selected.name, languages: [runLang] }];
    }

    // mode === "multi"
    if (domainColumnId === "" || languageColumnId === "") return [];

    const domainColId = Number(domainColumnId);
    const langColId = Number(languageColumnId);

    let candidateIds = resolveCandidateIds();
    if (cellFilter !== "all" && postIdTarget !== "") {
      const filterColId = Number(postIdTarget);
      candidateIds = candidateIds.filter((rid) => !getVal(rid, filterColId));
    }

    const byDomain = new Map<string, Set<string>>();
    for (const rid of candidateIds) {
      const domainName = getVal(rid, domainColId).trim();
      if (!domainName) continue;
      // Lowercase + trim — matches the backend's normalization, so
      // "EN" + "en" in different rows collapse to one item.
      const lang = getVal(rid, langColId).trim().toLowerCase();
      if (!lang) continue;
      if (!byDomain.has(domainName)) byDomain.set(domainName, new Set());
      byDomain.get(domainName)!.add(lang);
    }

    return Array.from(byDomain.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([domain_name, langs]) => ({
        domain_name,
        languages: Array.from(langs).sort(),
      }));
  }, [
    mode,
    cmsTypeFilter,
    selected,
    language,
    domainColumnId,
    languageColumnId,
    cellFilter,
    postIdTarget,
    resolveCandidateIds,
    getVal,
  ]);

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
        customPageType: false,
      };
      setOperation("create");
      setLookupKind("id");
      setLookupColumnId("");
      setOnSlugConflict("create");
      setCustomPageType("ordinary");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("domainMod.clearCacheFailed"));
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (mode === "single" && !selected) return;

    // Per-CMS, per-operation submit-time validation. Keep the messages
    // specific so the user knows exactly what to fix.
    const cmsType = cmsTypeFilter;
    if (operation === "upsert" && cmsType !== "custom") {
      setError(t("bulkPub.upsertCustomOnly"));
      return;
    }
    if (operation === "update" && cmsType === "wordpress") {
      // WP update path uses find_post → PATCH, needs the lookup column.
      if (lookupColumnId === "") {
        setError(t("bulkPub.updateLookupRequired"));
        return;
      }
    }
    if (operation === "update" && cmsType === "custom") {
      // Custom CMS Update now uses the unified "Find existing posts by"
      // panel — same shape as WP. The legacy "must map id in field
      // mapping" requirement is gone (the backend bridges
      // lookup_column_id → field_to_column['id'] at run creation).
      if (lookupColumnId === "" && !("id" in fieldToColumn)) {
        setError(t("bulkPub.updateLookupRequired"));
        return;
      }
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
        end: Number(rangeEnd) || totalRowCount,
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
      // Custom-only; WP runs always send 'ordinary'. The server also
      // rejects 'match' against a non-Custom domain as a safety net.
      custom_page_type: cmsTypeFilter === "custom" ? customPageType : "ordinary",
    };

    if (operation === "update" && lookupColumnId !== "") {
      // Send lookup_kind + lookup_column_id for both WP and Custom CMS
      // Update — the backend bridges the Custom-CMS case into the
      // legacy field_to_column['id'] format so the worker path is
      // unchanged. Skip when lookupColumnId is empty (legacy Custom
      // mappings that still encode the id via field_to_column['id']
      // pass validation above and reach the worker just fine).
      payload.lookup_kind = lookupKind;
      payload.lookup_column_id = Number(lookupColumnId);
    } else if (operation === "create") {
      // Slug-conflict handling lives on Create only. Server rejects
      // mixing this with operation='update' or 'upsert', so we just
      // don't send it for those.
      payload.on_slug_conflict = onSlugConflict;
    }
    // operation === 'upsert' or Custom-CMS update: no lookup_*, no
    // on_slug_conflict. Server-side action injection does the rest.

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

        {/* CMS-type segmented control — drives which settings render below
            and filters the single-mode domain picker. */}
        <CmsTypeSegmented value={cmsTypeFilter} onChange={onCmsTypeFilterChange} />

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

        {/* CMS-specific operation panel. WP shows operation + conflict +
            lookup; Custom shows a placeholder until the action-injection
            wiring lands in the follow-up PR. */}
        {cmsTypeFilter === "wordpress" ? (
          <WordPressOperationPanel
            operation={operation}
            onOperationChange={setOperationTouched}
            onSlugConflict={onSlugConflict}
            onSlugConflictChange={setOnSlugConflictTouched}
            lookupKind={lookupKind}
            onLookupKindChange={setLookupKindTouched}
            lookupColumnId={lookupColumnId}
            onLookupColumnIdChange={setLookupColumnId}
            columns={table.columns}
            fieldToColumn={fieldToColumn}
          />
        ) : (
          <div className="space-y-3">
            <CustomPageTypeSelector
              value={customPageType}
              onChange={onCustomPageTypeChange}
            />
            {/* Both page types use the create/update operation + lookup
                knobs. 'match' offers only create + update (Create posts to
                /add-sport-page, Update to /update-sport-page); 'ordinary'
                also offers upsert. */}
            <CustomCmsActionPanel
              operation={operation}
              onOperationChange={setOperationTouched}
              lookupKind={lookupKind}
              onLookupKindChange={setLookupKindTouched}
              lookupColumnId={lookupColumnId}
              onLookupColumnIdChange={setLookupColumnId}
              columns={table.columns}
              operations={
                customPageType === "match"
                  ? ["create", "update"]
                  : ["create", "update", "upsert"]
              }
            />
          </div>
        )}

        {mode === "single" ? (
          <SingleModeSection
            cmsTypeFilter={cmsTypeFilter}
            domainId={domainId}
            selectedLabel={selectedLabel}
            onDomainPicked={onDomainPicked}
            onPickerResults={onPickerResults}
            selected={selected}
            wpProfiles={wpProfiles}
            profileName={profileName}
            onProfileNameChange={setProfileName}
            language={language}
            onLanguageChange={setLanguage}
            languageColumnId={languageColumnId}
            onLanguageColumnIdChange={setLanguageColumnId}
            columns={eligibleColumns}
          />
        ) : (
          <MultiModeSection
            domainColumnId={domainColumnId}
            onDomainColumnIdChange={setDomainColumnId}
            profileColumnId={profileColumnId}
            onProfileColumnIdChange={setProfileColumnId}
            languageColumnId={languageColumnId}
            onLanguageColumnIdChange={setLanguageColumnId}
            columns={eligibleColumns}
          />
        )}

        <RowFilter
          value={rowFilter}
          onChange={setRowFilter}
          rangeStart={rangeStart}
          rangeEnd={rangeEnd}
          onRangeStartChange={setRangeStart}
          onRangeEndChange={setRangeEnd}
          totalRows={totalRowCount}
          selectedCount={allRowsSelected ? totalRowCount : selectedRowIds.length}
        />

        <CellFilter
          value={cellFilter}
          onChange={setCellFilter}
          hasPostIdTarget={postIdTarget !== ""}
        />

        {(mode === "multi" || selected) && (
          <div className="space-y-4 border-t border-neutral-200 pt-3 dark:border-neutral-800">
            <FieldMapping
              slots={slots}
              fieldToColumn={fieldToColumn}
              onSlotChange={setSlot}
              columns={eligibleColumns}
              onClear={onClear}
              emptyMessage={mappingEmptyMessage}
            />
            <BackFill
              postIdTarget={postIdTarget}
              postUrlTarget={postUrlTarget}
              onPostIdTargetChange={setPostIdTarget}
              onPostUrlTargetChange={setPostUrlTarget}
              columns={eligibleColumns}
            />
          </div>
        )}

        {/* Pre-flight language sync. Meaningful on Custom CMS runs in
            both modes — Single mode pushes the run's one language to
            the picked domain; Multi mode pushes each domain's set of
            languages derived from the table's columns. The targets
            memo handles all the conditions; rendering null when empty
            lets us include the panel unconditionally. */}
        {languageSyncTargets.length > 0 && (
          <LanguageSync targets={languageSyncTargets} />
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

/**
 * Single-mode helper: collect the unique non-empty language values from
 * a specific column, restricted to the rows that match the run's filters.
 *
 * Same filter logic as the `languageSyncTargets` Multi-mode branch above,
 * just collapsed to a single output (the column's distinct values) since
 * Single mode has only one target site.
 */
function collectCandidateLanguages(
  langColId: number,
  candidateIds: number[],
  getVal: (rowId: number, colId: number) => string,
  cellFilter: CellFilterValue,
  postIdTarget: number | "",
): string[] {
  let ids = candidateIds;
  if (cellFilter !== "all" && postIdTarget !== "") {
    const filterColId = Number(postIdTarget);
    ids = ids.filter((rid) => !getVal(rid, filterColId));
  }
  const langs = new Set<string>();
  for (const rid of ids) {
    const v = getVal(rid, langColId).trim().toLowerCase();
    if (v) langs.add(v);
  }
  return Array.from(langs).sort();
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
