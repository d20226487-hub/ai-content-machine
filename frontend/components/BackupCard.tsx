"use client";

import { useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api";
import {
  getBackupConfig,
  listBackupRuns,
  testBackupConnection,
  triggerBackupNow,
  updateBackupConfig,
  type BackupConfig,
  type BackupRun,
} from "@/lib/backup";
import { useT } from "@/lib/i18n-context";

function formatBytes(n: number | null): string {
  if (n === null || n === undefined) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
}

function formatTs(s: string | null): string {
  if (!s) return "—";
  const d = new Date(s);
  return d.toLocaleString();
}

export function BackupCard() {
  const { t } = useT();
  const [config, setConfig] = useState<BackupConfig | null>(null);
  const [runs, setRuns] = useState<BackupRun[]>([]);
  const [editing, setEditing] = useState<BackupConfig | null>(null);
  const [secretInput, setSecretInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load config + runs once.
  useEffect(() => {
    void load();
  }, []);

  async function load() {
    try {
      const [cfg, history] = await Promise.all([getBackupConfig(), listBackupRuns()]);
      setConfig(cfg);
      setEditing(cfg);
      setRuns(history);
    } catch (e) {
      setMessage({ kind: "err", text: e instanceof ApiError ? e.message : t("common.failedToLoad") });
    }
  }

  // Poll runs while a backup is in flight.
  useEffect(() => {
    const inFlight = runs.some((r) => r.status === "running");
    if (inFlight && !pollRef.current) {
      pollRef.current = setInterval(() => {
        void listBackupRuns().then(setRuns).catch(() => {});
      }, 2000);
    } else if (!inFlight && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current && !inFlight) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [runs]);

  async function save() {
    if (!editing) return;
    setSaving(true);
    setMessage(null);
    try {
      const payload = {
        schedule_enabled: editing.schedule_enabled,
        schedule_hour_utc: editing.schedule_hour_utc,
        s3_enabled: editing.s3_enabled,
        s3_endpoint_url: editing.s3_endpoint_url || null,
        s3_region: editing.s3_region || null,
        s3_bucket: editing.s3_bucket || null,
        s3_access_key_id: editing.s3_access_key_id || null,
        s3_prefix: editing.s3_prefix,
        local_retention_days: editing.local_retention_days,
        s3_retention_days: editing.s3_retention_days,
        ...(secretInput !== "" ? { s3_secret_access_key: secretInput } : {}),
      };
      const updated = await updateBackupConfig(payload);
      setConfig(updated);
      setEditing(updated);
      setSecretInput("");
      setMessage({ kind: "ok", text: t("common.saved") });
    } catch (e) {
      setMessage({ kind: "err", text: e instanceof ApiError ? e.message : t("common.failedToLoad") });
    } finally {
      setSaving(false);
    }
  }

  async function clearSecret() {
    setSaving(true);
    setMessage(null);
    try {
      const updated = await updateBackupConfig({ s3_secret_access_key: "" });
      setConfig(updated);
      setEditing(updated);
      setSecretInput("");
      setMessage({ kind: "ok", text: t("backup.secretCleared") });
    } catch (e) {
      setMessage({ kind: "err", text: e instanceof ApiError ? e.message : t("common.failedToLoad") });
    } finally {
      setSaving(false);
    }
  }

  async function test() {
    setTesting(true);
    setMessage(null);
    try {
      const r = await testBackupConnection();
      setMessage({ kind: r.ok ? "ok" : "err", text: r.message });
    } catch (e) {
      setMessage({ kind: "err", text: e instanceof ApiError ? e.message : t("common.failedToLoad") });
    } finally {
      setTesting(false);
    }
  }

  async function runNow() {
    setRunning(true);
    setMessage(null);
    try {
      await triggerBackupNow();
      // Re-fetch list immediately so the new "running" row appears.
      setRuns(await listBackupRuns());
    } catch (e) {
      setMessage({ kind: "err", text: e instanceof ApiError ? e.message : t("common.failedToLoad") });
    } finally {
      setRunning(false);
    }
  }

  if (!config || !editing) {
    return (
      <section className="rounded-lg border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-900">
        <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
          {t("backup.title")}
        </h2>
        {message ? (
          <>
            <p className="mt-2 text-sm text-red-700 dark:text-red-400">{message.text}</p>
            <p className="mt-2 text-xs text-neutral-500 dark:text-neutral-400">
              {t("backup.loadHint")}
            </p>
            <button
              type="button"
              onClick={() => {
                setMessage(null);
                void load();
              }}
              className="mt-3 rounded-md border border-neutral-300 px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              {t("common.retry")}
            </button>
          </>
        ) : (
          <p className="mt-2 text-sm text-neutral-500 dark:text-neutral-400">
            {t("common.loading")}
          </p>
        )}
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-900">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
            {t("backup.title")}
          </h2>
          <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">{t("backup.subtitle")}</p>
        </div>
        <button
          type="button"
          onClick={runNow}
          disabled={running}
          className="shrink-0 rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300"
        >
          {running ? t("backup.runningNow") : t("backup.runNow")}
        </button>
      </div>

      {/* --- Schedule --- */}
      <div className="mt-6">
        <h3 className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
          {t("backup.scheduleHeading")}
        </h3>
        <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
          {t("backup.scheduleHint")}
        </p>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <label className="flex items-start gap-2">
            <input
              type="checkbox"
              checked={editing.schedule_enabled}
              onChange={(e) =>
                setEditing({ ...editing, schedule_enabled: e.target.checked })
              }
              className="mt-0.5"
            />
            <span className="text-sm">
              <span className="font-medium text-neutral-900 dark:text-neutral-100">
                {t("backup.scheduleEnabled")}
              </span>
              <span className="block text-xs text-neutral-500 dark:text-neutral-400">
                {t("backup.scheduleEnabledHint")}
              </span>
            </span>
          </label>
          <div>
            <label className="block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
              {t("backup.scheduleHour")}
            </label>
            <select
              value={editing.schedule_hour_utc}
              disabled={!editing.schedule_enabled}
              onChange={(e) =>
                setEditing({
                  ...editing,
                  schedule_hour_utc: Number(e.target.value),
                })
              }
              className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-2 py-1.5 text-sm disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-100"
            >
              {Array.from({ length: 24 }, (_, h) => (
                <option key={h} value={h}>
                  {String(h).padStart(2, "0")}:00 UTC
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* --- Destination --- */}
      <h3 className="mt-8 text-sm font-medium text-neutral-700 dark:text-neutral-300">
        {t("backup.destinationHeading")}
      </h3>
      <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        {t("backup.destinationHint")}
      </p>
      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        <label className="flex items-start gap-2 sm:col-span-2">
          <input
            type="checkbox"
            checked={editing.s3_enabled}
            onChange={(e) => setEditing({ ...editing, s3_enabled: e.target.checked })}
            className="mt-0.5"
          />
          <span className="text-sm">
            <span className="font-medium text-neutral-900 dark:text-neutral-100">
              {t("backup.s3Enabled")}
            </span>
            <span className="block text-xs text-neutral-500 dark:text-neutral-400">
              {t("backup.s3EnabledHint")}
            </span>
          </span>
        </label>

        <Field
          label={t("backup.endpoint")}
          value={editing.s3_endpoint_url ?? ""}
          onChange={(v) => setEditing({ ...editing, s3_endpoint_url: v || null })}
          placeholder="https://s3.amazonaws.com"
        />
        <Field
          label={t("backup.region")}
          value={editing.s3_region ?? ""}
          onChange={(v) => setEditing({ ...editing, s3_region: v || null })}
          placeholder="us-east-1"
        />
        <Field
          label={t("backup.bucket")}
          value={editing.s3_bucket ?? ""}
          onChange={(v) => setEditing({ ...editing, s3_bucket: v || null })}
          placeholder="acm-backups"
        />
        <Field
          label={t("backup.prefix")}
          value={editing.s3_prefix}
          onChange={(v) => setEditing({ ...editing, s3_prefix: v })}
          placeholder="acm/"
        />
        <Field
          label={t("backup.accessKey")}
          value={editing.s3_access_key_id ?? ""}
          onChange={(v) => setEditing({ ...editing, s3_access_key_id: v || null })}
          placeholder="AKIA…"
        />
        <div>
          <label className="block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            {t("backup.secretKey")}
          </label>
          <input
            type="password"
            value={secretInput}
            onChange={(e) => setSecretInput(e.target.value)}
            placeholder={
              config.s3_secret_access_key_configured
                ? t("backup.secretConfigured")
                : t("backup.secretEmpty")
            }
            className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-100"
          />
          {config.s3_secret_access_key_configured && (
            <button
              type="button"
              onClick={clearSecret}
              className="mt-1 text-xs text-red-600 hover:underline dark:text-red-400"
            >
              {t("backup.clearSecret")}
            </button>
          )}
        </div>

        <NumField
          label={t("backup.localRetention")}
          value={editing.local_retention_days}
          onChange={(v) => setEditing({ ...editing, local_retention_days: v })}
          min={1}
          max={365}
        />
        <NumField
          label={t("backup.s3Retention")}
          value={editing.s3_retention_days}
          onChange={(v) => setEditing({ ...editing, s3_retention_days: v })}
          min={1}
          max={3650}
        />
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
        >
          {saving ? t("common.saving") : t("common.save")}
        </button>
        <button
          type="button"
          onClick={test}
          disabled={testing || !config.s3_enabled || !config.s3_secret_access_key_configured}
          className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
        >
          {testing ? t("backup.testing") : t("backup.testConnection")}
        </button>
        {message && (
          <span
            className={
              "text-xs " +
              (message.kind === "ok"
                ? "text-green-700 dark:text-green-400"
                : "text-red-700 dark:text-red-400")
            }
          >
            {message.text}
          </span>
        )}
      </div>

      <h3 className="mt-8 text-sm font-medium text-neutral-700 dark:text-neutral-300">
        {t("backup.recentRuns")}
      </h3>
      {runs.length === 0 ? (
        <p className="mt-2 text-xs text-neutral-500 dark:text-neutral-400">
          {t("backup.noRuns")}
        </p>
      ) : (
        <div className="mt-2 overflow-x-auto rounded border border-neutral-200 dark:border-neutral-800">
          <table className="w-full text-xs">
            <thead className="bg-neutral-50 dark:bg-neutral-800">
              <tr className="text-left">
                <th className="px-2 py-1">{t("backup.col.started")}</th>
                <th className="px-2 py-1">{t("backup.col.status")}</th>
                <th className="px-2 py-1">{t("backup.col.size")}</th>
                <th className="px-2 py-1">{t("backup.col.trigger")}</th>
                <th className="px-2 py-1">{t("backup.col.s3")}</th>
                <th className="px-2 py-1">{t("backup.col.error")}</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-t border-neutral-200 dark:border-neutral-800">
                  <td className="px-2 py-1 font-mono">{formatTs(r.started_at)}</td>
                  <td className="px-2 py-1">
                    <StatusPill status={r.status} />
                  </td>
                  <td className="px-2 py-1">{formatBytes(r.size_bytes)}</td>
                  <td className="px-2 py-1">{r.trigger}</td>
                  <td className="px-2 py-1 font-mono">{r.s3_key ?? "—"}</td>
                  <td className="px-2 py-1 text-red-700 dark:text-red-400">{r.error ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {label}
      </label>
      <input
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-100"
      />
    </div>
  );
}

function NumField({
  label,
  value,
  onChange,
  min,
  max,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
}) {
  return (
    <div>
      <label className="block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {label}
      </label>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-100"
      />
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    ok: "bg-green-100 text-green-800 dark:bg-green-950/60 dark:text-green-300",
    failed: "bg-red-100 text-red-800 dark:bg-red-950/60 dark:text-red-300",
    running:
      "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  };
  return (
    <span className={"rounded-full px-1.5 py-0.5 text-[10px] font-medium " + (map[status] ?? "")}>
      {status}
    </span>
  );
}
