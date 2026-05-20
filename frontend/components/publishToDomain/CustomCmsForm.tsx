"use client";

import { Field } from "./Field";

/**
 * Placeholder-driven publish form for Custom CMS domains.
 *
 * The set of inputs comes from the parent (derived from the domain's
 * body_template at modal-open time) so this component stays dumb — it
 * just renders one input per key.
 *
 * Convention from the bulk-publish modal carries over here: ``content``
 * gets a multi-line textarea, everything else gets a single-line input.
 * System-injected placeholders (``language``, ``action``) are filtered
 * out by the parent before the values map is built; if you see one here
 * it'll just render an empty box.
 */
export function CustomCmsForm({
  values,
  onFieldChange,
}: {
  values: Record<string, string>;
  onFieldChange: (key: string, value: string) => void;
}) {
  return (
    <div className="space-y-3 border-t border-neutral-200 pt-3 dark:border-neutral-800">
      {Object.keys(values).map((key) => (
        <Field key={key} label={key}>
          {key === "content" ? (
            <textarea
              value={values[key]}
              onChange={(e) => onFieldChange(key, e.target.value)}
              rows={8}
              className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm font-mono dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            />
          ) : (
            <input
              value={values[key]}
              onChange={(e) => onFieldChange(key, e.target.value)}
              className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            />
          )}
        </Field>
      ))}
    </div>
  );
}
