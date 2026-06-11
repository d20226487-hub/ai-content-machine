/**
 * Minimal, quote-aware delimited-text parser shared by the "Update table"
 * flow (CSV file upload + Excel/Sheets paste).
 *
 * Handles the RFC-4180 essentials that a naive `split` gets wrong:
 *   - quoted fields that contain the delimiter:  "a, b",c
 *   - escaped quotes inside a quoted field:       "she said ""hi"""
 *   - newlines inside a quoted field (Excel does this for multi-line cells)
 *   - \n and \r\n line endings
 *
 * Returns a 2D array of raw field strings (no trimming — the caller decides).
 */
export function parseDelimited(text: string, delimiter: string): string[][] {
  // The tab option travels through the UI as the literal two chars "\t".
  const delim = delimiter === "\\t" ? "\t" : delimiter;
  const rows: string[][] = [];
  let field = "";
  let row: string[] = [];
  let inQuotes = false;
  let i = 0;
  const n = text.length;

  while (i < n) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 2;
          continue;
        }
        inQuotes = false;
        i++;
        continue;
      }
      field += ch;
      i++;
      continue;
    }
    if (ch === '"') {
      inQuotes = true;
      i++;
      continue;
    }
    if (ch === delim) {
      row.push(field);
      field = "";
      i++;
      continue;
    }
    if (ch === "\r") {
      i++;
      continue;
    }
    if (ch === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
      i++;
      continue;
    }
    field += ch;
    i++;
  }
  // Flush the trailing field/row unless the text ended exactly on a newline
  // (which would otherwise yield a spurious empty final row).
  if (field !== "" || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

/** Guess the delimiter from the first non-empty line. Excel/Sheets paste is
 *  tab-separated; semicolon CSVs are common in some locales. */
export function detectDelimiter(text: string): string {
  const firstLine = text.split(/\r?\n/).find((l) => l.trim().length > 0) ?? "";
  if (firstLine.includes("\t")) return "\t";
  if (firstLine.includes(";") && !firstLine.includes(",")) return ";";
  return ",";
}

/** True when every field in the row is blank — used to drop empty lines. */
export function isBlankRow(row: string[]): boolean {
  return row.every((c) => c.trim() === "");
}
