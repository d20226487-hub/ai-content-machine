/**
 * Walk a Custom-CMS body_template (nested JSON / arrays / strings) and
 * collect every ``{{placeholder}}`` it references. Same regex + recursion
 * as the equivalent helper in BulkPublishModal; lifted out so both
 * modals can share the implementation without bundling a giant
 * sibling import.
 */
const PLACEHOLDER_RE = /\{\{\s*([A-Za-z_][\w\.\- ]*?)\s*\}\}/g;

export function collectPlaceholders(
  node: unknown,
  out: Set<string> = new Set(),
): string[] {
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
