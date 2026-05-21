/**
 * Minimal CSV parser for the language-sync import flow.
 *
 * Only handles what we need: comma-separated, optional double-quoted
 * cells (with `""` escaping inside quotes), header row optional. The
 * full RFC 4180 spec has more edge cases (CRLF inside quotes, escaped
 * separators, etc.) but our use case is "user pastes a sheet export of
 * domain + languages" — keeping the parser ~50 lines is the right
 * trade-off.
 *
 * Returns rows as string[] arrays so the caller can decide whether to
 * treat row 0 as a header or as data.
 */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const ch = text[i];

    if (inQuotes) {
      if (ch === '"') {
        // Doubled "" inside a quoted cell -> literal ".
        if (text[i + 1] === '"') {
          cell += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        cell += ch;
      }
      continue;
    }

    if (ch === '"') {
      inQuotes = true;
      continue;
    }
    if (ch === ",") {
      row.push(cell);
      cell = "";
      continue;
    }
    if (ch === "\r") {
      // Eat \r — the next \n closes the row, OR we're at end-of-file
      // and need to close manually.
      continue;
    }
    if (ch === "\n") {
      row.push(cell);
      // Skip wholly-blank rows so users can leave trailing newlines.
      if (row.some((c) => c.trim() !== "")) rows.push(row);
      row = [];
      cell = "";
      continue;
    }
    cell += ch;
  }

  // Flush any tailing cell/row (file without trailing newline).
  if (cell !== "" || row.length > 0) {
    row.push(cell);
    if (row.some((c) => c.trim() !== "")) rows.push(row);
  }

  return rows;
}

/**
 * Split a "languages" cell into individual codes. Accepts any of:
 * commas, semicolons, spaces, newlines as separators (so "ru en, de"
 * all collapse to the same set). Lowercases + trims + dedupes; sorts
 * for stable comparisons in the preview.
 */
export function parseLanguagesCell(text: string): string[] {
  return Array.from(
    new Set(
      text
        .split(/[\s,;]+/)
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean),
    ),
  ).sort();
}
