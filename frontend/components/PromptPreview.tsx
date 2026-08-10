"use client";

import { useMemo } from "react";

/**
 * Prompt template rendered with its {{variables}} highlighted — the live
 * preview shown next to the test form.
 *
 * Substitution mirrors backend `app/services/prompts.py`
 * (`_VAR_PATTERN` / `_normalize` / `render_template`) so what's on screen is
 * exactly what the model receives:
 *   * a name is normalized by collapsing internal whitespace runs and
 *     trimming, so `{{ Slot  name }}` and `{{Slot name}}` are one variable;
 *   * a variable whose value is EMPTY counts as missing — the backend leaves
 *     the literal `{{placeholder}}` in the prompt rather than substituting a
 *     blank, so the preview shows the placeholder too (amber), not an empty gap.
 * Filled values render green and unfilled placeholders amber, so the two
 * states are distinguishable at a glance.
 */
const VAR_RE = /\{\{\s*([A-Za-z_][\w.\- ]*?)\s*\}\}/g;

export interface PromptSegment {
  /** text = literal prompt text; filled = substituted value; empty = untouched placeholder. */
  kind: "text" | "filled" | "empty";
  /** What to display for this segment. */
  text: string;
  /** Variable name — set for filled/empty segments only. */
  name?: string;
}

function normalizeName(raw: string): string {
  return raw.replace(/\s+/g, " ").trim();
}

/** Split a template into literal-text and variable segments (see component doc). */
export function splitPromptTemplate(
  content: string,
  values: Record<string, string>,
): PromptSegment[] {
  const out: PromptSegment[] = [];
  let last = 0;
  // Module-level regex carries /g state between calls — reset before use.
  VAR_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = VAR_RE.exec(content)) !== null) {
    if (m.index > last) {
      out.push({ kind: "text", text: content.slice(last, m.index) });
    }
    const name = normalizeName(m[1]);
    const value = values[name];
    if (value != null && value !== "") {
      out.push({ kind: "filled", text: value, name });
    } else {
      // Backend leaves the placeholder as-is when the value is missing/blank.
      out.push({ kind: "empty", text: m[0], name });
    }
    last = m.index + m[0].length;
  }
  if (last < content.length) {
    out.push({ kind: "text", text: content.slice(last) });
  }
  return out;
}

export function PromptPreview({
  content,
  values,
  activeVar = null,
  className = "",
}: {
  /** The prompt template text. */
  content: string;
  /** Current variable values, keyed by normalized name. */
  values: Record<string, string>;
  /** Variable whose input is focused — its spans get a ring so the user can
   *  see where the field they're typing in lands in the prompt. */
  activeVar?: string | null;
  className?: string;
}) {
  const segments = useMemo(
    () => splitPromptTemplate(content, values),
    [content, values],
  );

  return (
    <pre
      className={
        "whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-neutral-800 dark:text-neutral-200 " +
        className
      }
    >
      {segments.map((s, i) => {
        if (s.kind === "text") return <span key={i}>{s.text}</span>;
        const active = activeVar != null && s.name === activeVar;
        const tone =
          s.kind === "filled"
            ? "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100"
            : "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-100";
        const ring = active
          ? " ring-2 ring-blue-400 dark:ring-blue-500"
          : "";
        return (
          <mark
            key={i}
            data-var={s.name}
            title={s.name}
            className={`rounded-sm px-0.5 ${tone}${ring}`}
          >
            {s.text}
          </mark>
        );
      })}
    </pre>
  );
}
