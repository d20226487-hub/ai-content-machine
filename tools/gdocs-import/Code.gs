/**
 * ===========================================================================
 * Content Beast — Google Docs → Custom CMS import extractor (Apps Script)
 * ===========================================================================
 *
 * WHAT THIS IS
 * ------------
 * A standalone Google Apps Script that runs *as you* (your work Google
 * account), so it inherits your org access to the spreadsheet and to every
 * linked Google Doc. It reads a sheet that lists, per row:
 *   - a target domain (or domains),
 *   - a language,
 *   - a "Structure" cell — the page list for that domain; its entries are the
 *     page slugs, and
 *   - a "Links" cell with the Google Docs for the written pages. Links are
 *     captured whether they're rich-text hyperlinks, =HYPERLINK() formulas,
 *     plain-text Doc URLs, OR Google Drive smart chips (the grey pills with a
 *     doc icon — these need the Sheets API, see SETUP). Hyperlinks placed
 *     directly on Structure entries are also captured. Each link's anchor text
 *     is later paired to a Structure entry to choose the slug (server-side).
 *
 * For every linked Doc it exports the Doc to HTML, and it emits ONE JSON file
 * to your Google Drive. You then download that JSON and upload it into Content
 * Beast (Library → Import from Google Docs), which does the messy part:
 * cleaning the HTML, AI-pairing each Structure page to its Doc by wording,
 * pulling the meta title / meta description out of the top of each Doc, and
 * building the bulk-publish table (single-site or multi-site, decided by how
 * many distinct domains appear).
 *
 * WHY APPS SCRIPT (and not a GCP service account / OAuth app)
 * ----------------------------------------------------------
 * Apps Script auto-provisions its own hidden Google Cloud project and runs
 * under YOUR identity when you click Run. That means no "create a GCP project"
 * rights are needed, and org-restricted Docs that only you can view are
 * readable here. The trade-off: it's a manual run-and-download step rather
 * than a server-side automation. For v1 that's the deal.
 *
 * SETUP (one time, ~2 minutes)
 * ----------------------------
 *   1. Open https://script.google.com → New project.
 *   2. Delete the stub Code.gs contents and paste THIS file in.
 *   3. Click the gear (Project Settings) → tick
 *      "Show appsscript.json manifest file in editor".
 *   4. Open the now-visible appsscript.json and paste in the manifest shipped
 *      alongside this file (tools/gdocs-import/appsscript.json). It declares
 *      the OAuth scopes we need (sheets read, drive, external_request).
 *   5. IF your Doc links are smart chips (grey pills with a doc icon), add the
 *      Sheets API so the script can read them: in the editor, click
 *      "Services" (＋) → select "Google Sheets API" → Add. (Plain hyperlinks
 *      and =HYPERLINK() formulas work without this; chips need it.)
 *   6. Back in Code.gs, edit the CONFIG block below: set SHEET_URL (and
 *      SHEET_NAME if your tab isn't the first one).
 *   7. Run → choose the function `run`. Google will prompt you to authorize;
 *      review the scopes and Allow. (First run only.)
 *   8. When it finishes, check the Execution log: it prints the name and a
 *      direct link of the JSON file it wrote to your Drive ("My Drive" root by
 *      default). Download that JSON.
 *   9. Upload the JSON in Content Beast.
 *
 * BIG SHEETS / TIMEOUTS
 * ---------------------
 * Apps Script caps a single execution at ~6 minutes. Exporting many Docs is
 * the slow part. If you have a lot of rows, run in chunks: set ROW_START /
 * ROW_END (1-based sheet row numbers, header is row 1) to process a slice,
 * download that JSON, bump the range, run again. The importer accepts multiple
 * JSON files. Leave both at 0 to process every row.
 *
 * WHAT YOU DON'T NEED TO DO
 * -------------------------
 * No HTML cleanup, no link/structure matching, no meta extraction here — all
 * of that happens server-side in Content Beast where it can be reviewed and
 * re-run. This script's only job is faithful extraction.
 *
 * ---------------------------------------------------------------------------
 * JSON CONTRACT (this is what the backend importer parses — keep in sync)
 * ---------------------------------------------------------------------------
 * {
 *   "version": 1,
 *   "generatedAt": "2026-06-04T12:00:00.000Z",
 *   "source": { "spreadsheetId": "...", "sheetName": "Sheet1", "url": "..." },
 *   "columns": {                         // resolved header -> 0-based col index
 *     "domain":   { "header": "Domains",   "index": 0 },
 *     "language": { "header": "Language",  "index": 1 },
 *     "structure":{ "header": "Structure", "index": 4 },
 *     "links":    { "header": "Links",     "index": 5 }
 *   },
 *   "rows": [
 *     {
 *       "rowNumber": 2,                   // 1-based sheet row
 *       "domain": "example1.com",
 *       "language": "en",
 *       "structure": ["About us", "Pricing", "Contact"],  // parsed page list
 *       "structureRaw": "About us\nPricing\nContact",
 *       "links": [
 *         { "label": "About us",
 *           "url": "https://docs.google.com/document/d/ID1/edit",
 *           "docId": "ID1",
 *           "kind": "hyperlink" }        // "hyperlink" | "plain"
 *       ]
 *     }
 *   ],
 *   "docs": {                            // deduped across all rows, keyed by docId
 *     "ID1": { "ok": true,  "title": "Doc title", "html": "<...>" },
 *     "ID2": { "ok": false, "error": "Export failed: 404" }
 *   },
 *   "warnings": [ "Row 7: no links column value", ... ]
 * }
 * ===========================================================================
 */

// ======================= CONFIG — EDIT THESE =============================

/** Full URL of the spreadsheet (copy from the browser address bar). */
var SHEET_URL = "PASTE_YOUR_SHEET_URL_HERE";

/** Tab name. Leave "" to use the first sheet. */
var SHEET_NAME = "";

/** Process only rows in [ROW_START, ROW_END] (1-based, inclusive). 0 = no bound. */
var ROW_START = 0;
var ROW_END = 0;

/** Keep images in exported HTML? (We export full HTML either way; the importer
 *  decides what to keep. This flag is informational, surfaced in the JSON.) */
var KEEP_IMAGES = true;

// ========================================================================


/** Entry point. Run this. */
function run() {
  var ss = SpreadsheetApp.openByUrl(SHEET_URL);
  var sheet = SHEET_NAME ? ss.getSheetByName(SHEET_NAME) : ss.getSheets()[0];
  if (!sheet) {
    throw new Error("Sheet not found: " + (SHEET_NAME || "(first sheet)"));
  }

  var warnings = [];
  var range = sheet.getDataRange();
  var values = range.getValues();          // display values (text)
  var rich = range.getRichTextValues();    // for recovering hyperlink URLs
  var formulas = range.getFormulas();      // for recovering =HYPERLINK() links

  if (values.length < 2) {
    throw new Error("Sheet has no data rows (need a header row + at least one row).");
  }

  var header = values[0];
  var cols = resolveColumns_(header, warnings);

  // Smart-chip links (Insert > Smart chips > Drive file, or @file) are NOT
  // visible to getRichTextValues()/getLinkUrl() — only the Sheets API exposes
  // them, via chipRuns. Fetch them once for the whole sheet.
  var chipInfo = fetchChipData_(ss.getId(), sheet.getName());
  if (!chipInfo.ok) {
    warnings.push(
      "Could not read smart-chip links via the Sheets API (" + chipInfo.error +
      "). If your Doc links are smart chips (grey pills with a doc icon), " +
      "enable the Google Sheets API for this script (Apps Script editor → " +
      "Services → add 'Google Sheets API'), or convert the chips to plain " +
      "links. Regular hyperlinks and =HYPERLINK() formulas still work.");
  }

  var rowStart = ROW_START > 1 ? ROW_START : 2;   // never include the header
  var rowEnd = ROW_END > 0 ? Math.min(ROW_END, values.length) : values.length;

  var docs = {};            // docId -> {ok,title,html,error}
  var rows = [];

  for (var r = rowStart; r <= rowEnd; r++) {
    var rowVals = values[r - 1];
    var rowRich = rich[r - 1];
    var rowFormulas = formulas[r - 1];

    var domain = cols.domain.index >= 0 ? String(rowVals[cols.domain.index] || "").trim() : "";
    var language = cols.language.index >= 0 ? String(rowVals[cols.language.index] || "").trim() : "";
    var structureRaw = cols.structure.index >= 0 ? String(rowVals[cols.structure.index] || "").trim() : "";

    // Doc links: read the dedicated "Links" column (rich-text hyperlinks,
    // =HYPERLINK() formulas, and plain-text URLs are all captured), and also
    // any hyperlinks placed directly on Structure entries. Dedupe by docId.
    var links = [];
    if (cols.links.index >= 0) {
      links = links.concat(
        extractLinksFromCell_(
          rowRich[cols.links.index],
          rowVals[cols.links.index],
          rowFormulas[cols.links.index]
        )
      );
      links = links.concat(chipLinksAt_(chipInfo, r, cols.links.index));
    }
    if (cols.structure.index >= 0) {
      links = links.concat(extractLinksFromStructure_(rowRich[cols.structure.index]));
      links = links.concat(chipLinksAt_(chipInfo, r, cols.structure.index));
    }
    links = dedupeLinks_(links);

    // Skip wholly empty rows quietly.
    if (!domain && !language && !structureRaw && links.length === 0) {
      continue;
    }
    if (links.length === 0) {
      warnings.push("Row " + r +
        ": no Google Doc links found (checked the Structure and Links columns, " +
        "including smart chips).");
    }

    // Queue each unique Doc for export.
    for (var i = 0; i < links.length; i++) {
      var id = links[i].docId;
      if (id && !docs[id]) {
        docs[id] = exportDoc_(id);
      }
    }

    rows.push({
      rowNumber: r,
      domain: domain,
      language: language,
      structure: parseStructure_(structureRaw),
      structureRaw: structureRaw,
      links: links,
    });
  }

  var payload = {
    version: 1,
    generatedAt: new Date().toISOString(),
    keepImages: KEEP_IMAGES,
    source: {
      spreadsheetId: ss.getId(),
      sheetName: sheet.getName(),
      url: SHEET_URL,
    },
    columns: {
      domain: cols.domain,
      language: cols.language,
      structure: cols.structure,
      links: cols.links,
    },
    rows: rows,
    docs: docs,
    warnings: warnings,
  };

  var fileName = "gdocs-import-" + ss.getId().slice(0, 8) + "-" +
    formatStamp_(new Date()) +
    (ROW_START || ROW_END ? "-rows" + rowStart + "-" + rowEnd : "") + ".json";

  var file = DriveApp.createFile(fileName, JSON.stringify(payload), "application/json");

  Logger.log("Done. %s rows, %s docs (%s failed), %s warnings.",
    rows.length,
    Object.keys(docs).length,
    Object.keys(docs).filter(function (k) { return !docs[k].ok; }).length,
    warnings.length);
  Logger.log("JSON file: %s", file.getName());
  Logger.log("Download here: %s", file.getUrl());
  if (warnings.length) {
    Logger.log("Warnings:\n - %s", warnings.join("\n - "));
  }
}


/**
 * Find which column is which by header text. Falls back to position heuristics
 * for the links column (the column with the most Doc-bearing cells, else last).
 */
function resolveColumns_(header, warnings) {
  function find(patterns) {
    for (var c = 0; c < header.length; c++) {
      var h = String(header[c] || "").trim().toLowerCase();
      if (!h) continue;
      for (var p = 0; p < patterns.length; p++) {
        if (patterns[p].test(h)) {
          return { header: String(header[c]).trim(), index: c };
        }
      }
    }
    return { header: "", index: -1 };
  }

  var domain = find([/^domains?$/, /domain/, /^sites?$/, /^urls?$/, /host/]);
  var language = find([/^lang/, /language/, /locale/]);
  var structure = find([/structure/, /pages?/, /sitemap/, /outline/]);
  var links = find([/links?/, /docs?$/, /google ?docs?/, /content/, /articles?/]);

  // If we couldn't name the links column, pick the last column that isn't one
  // of the already-identified ones; the JSON consumer can still override.
  if (links.index < 0) {
    var taken = {};
    [domain, language, structure].forEach(function (col) {
      if (col.index >= 0) taken[col.index] = true;
    });
    for (var c = header.length - 1; c >= 0; c--) {
      if (!taken[c]) {
        links = { header: String(header[c] || "").trim() || ("col" + (c + 1)), index: c };
        warnings.push("Could not identify the links column by header; guessed column " +
          (c + 1) + " (\"" + links.header + "\").");
        break;
      }
    }
  }

  if (domain.index < 0) warnings.push("No domain column found by header.");
  if (language.index < 0) warnings.push("No language column found by header.");
  if (structure.index < 0) warnings.push("No Structure column found by header.");

  return { domain: domain, language: language, structure: structure, links: links };
}


/**
 * Read Google Drive smart-chip links (Insert > Smart chips > Drive file, or
 * typing "@file"). These are invisible to getRichTextValues()/getLinkUrl() and
 * to =HYPERLINK() parsing — the ONLY way to read them is the Sheets API's
 * chipRuns field. We fetch the whole sheet's grid once (formattedValue +
 * chipRuns) using the script's OAuth token (needs the spreadsheets scope the
 * manifest already declares). Each chip's display text becomes the link label.
 *
 * Returns { ok, byCell: { "<1-based row>,<0-based col>": [link,...] }, error }.
 */
function fetchChipData_(ssId, sheetName) {
  var fields =
    "sheets(properties(title)," +
    "data(startRow,rowData(values(formattedValue," +
    "chipRuns(startIndex,chip(richLinkProperties(uri)))))))";

  var json = null;
  var errors = [];

  // Preferred path: the Sheets *advanced service*. Adding it via the editor
  // (Services → Google Sheets API) enables the API on the script's project for
  // you — no Cloud Console access needed. Returns a parsed object.
  try {
    if (typeof Sheets !== "undefined" && Sheets.Spreadsheets) {
      json = Sheets.Spreadsheets.get(ssId, {
        includeGridData: true,
        fields: fields,
      });
    } else {
      errors.push("advanced 'Sheets' service not added");
    }
  } catch (e1) {
    errors.push("advanced service: " + (e1 && e1.message ? e1.message : String(e1)));
  }

  // Fallback path: REST via UrlFetch. Needs the Sheets API enabled on the
  // script's GCP project (the console link in the error does this).
  if (!json) {
    try {
      var url = "https://sheets.googleapis.com/v4/spreadsheets/" +
        encodeURIComponent(ssId) +
        "?includeGridData=true&fields=" + encodeURIComponent(fields);
      var resp = UrlFetchApp.fetch(url, {
        headers: { Authorization: "Bearer " + ScriptApp.getOAuthToken() },
        muteHttpExceptions: true,
      });
      if (resp.getResponseCode() === 200) {
        json = JSON.parse(resp.getContentText());
      } else {
        errors.push("REST HTTP " + resp.getResponseCode() + ": " +
          resp.getContentText().slice(0, 140));
      }
    } catch (e2) {
      errors.push("REST: " + (e2 && e2.message ? e2.message : String(e2)));
    }
  }

  if (!json) {
    return { ok: false, error: errors.join(" | ") || "Sheets API unavailable" };
  }

  try {
    var sheets = json.sheets || [];
    var target = null;
    for (var i = 0; i < sheets.length; i++) {
      if (sheets[i].properties && sheets[i].properties.title === sheetName) {
        target = sheets[i];
        break;
      }
    }
    if (!target) target = sheets[0];

    var byCell = {};
    var data = (target && target.data) || [];
    for (var d = 0; d < data.length; d++) {
      var startRow = data[d].startRow || 0;
      var rowData = data[d].rowData || [];
      for (var ri = 0; ri < rowData.length; ri++) {
        var sheetRow = startRow + ri + 1; // 1-based sheet row
        var vals = rowData[ri].values || [];
        for (var ci = 0; ci < vals.length; ci++) {
          var cell = vals[ci];
          var runs = cell && cell.chipRuns;
          if (!runs || !runs.length) continue;
          var fv = cell.formattedValue != null ? String(cell.formattedValue) : "";
          var list = [];
          for (var k = 0; k < runs.length; k++) {
            var chip = runs[k].chip;
            var uri = chip && chip.richLinkProperties && chip.richLinkProperties.uri;
            if (!uri) continue;
            var id = docIdFromUrl_(uri);
            if (!id) continue;                 // only Google Doc chips
            var s = runs[k].startIndex || 0;
            var e = (k + 1 < runs.length) ? (runs[k + 1].startIndex || fv.length) : fv.length;
            list.push({
              label: fv.substring(s, e).trim(),
              url: uri,
              docId: id,
              kind: "chip",
            });
          }
          if (list.length) byCell[sheetRow + "," + ci] = list;
        }
      }
    }
    return { ok: true, byCell: byCell };
  } catch (err) {
    return { ok: false, error: (err && err.message ? err.message : String(err)) };
  }
}


/** Smart-chip links for one cell (1-based row, 0-based col), or []. */
function chipLinksAt_(chipInfo, row, col) {
  if (!chipInfo || !chipInfo.ok) return [];
  return chipInfo.byCell[row + "," + col] || [];
}


/**
 * Pull every Google Doc link out of one cell.
 * - Real hyperlinks: walk the RichText runs and read getLinkUrl().
 * - =HYPERLINK("url","label") formulas: parse the cell formula (these are
 *   invisible to getRuns(), so without this they'd be silently dropped).
 * - Plain-text URLs: regex-scan the cell text.
 * Dedupes by docId, preserves first-seen order, keeps the run/anchor text as label.
 */
function extractLinksFromCell_(richValue, displayValue, formula) {
  var out = [];
  var seen = {};

  function push(url, label, kind) {
    if (!url) return;
    var id = docIdFromUrl_(url);
    if (!id) return;                 // only care about Google Doc links
    if (seen[id]) return;
    seen[id] = true;
    out.push({
      label: String(label || "").trim(),
      url: url,
      docId: id,
      kind: kind,
    });
  }

  // 1) Hyperlinks via rich text runs.
  if (richValue && typeof richValue.getRuns === "function") {
    var runs = richValue.getRuns();
    for (var i = 0; i < runs.length; i++) {
      var u = runs[i].getLinkUrl();
      if (u) push(u, runs[i].getText(), "hyperlink");
    }
    // Some cells carry a single cell-level link rather than per-run links.
    if (out.length === 0 && typeof richValue.getLinkUrl === "function") {
      var cu = richValue.getLinkUrl();
      if (cu) push(cu, richValue.getText(), "hyperlink");
    }
  }

  // 2) =HYPERLINK("url","label") formulas — a cell can hold several joined
  //    with & / CHAR(10); match each occurrence. These never appear in the
  //    rich-text runs, so they must be recovered from the formula text.
  if (formula) {
    var fRe = /HYPERLINK\(\s*"([^"]+)"\s*(?:,\s*"([^"]*)")?\s*\)/gi;
    var fm;
    while ((fm = fRe.exec(String(formula))) !== null) {
      push(fm[1], fm[2] || fm[1], "formula");
    }
  }

  // 3) Plain-text URLs in the visible text.
  var text = "";
  if (richValue && typeof richValue.getText === "function") {
    text = richValue.getText();
  } else if (displayValue != null) {
    text = String(displayValue);
  }
  var urlRe = /https?:\/\/[^\s<>"')]+/g;
  var m;
  while ((m = urlRe.exec(text)) !== null) {
    push(m[0].replace(/[.,;]+$/, ""), m[0], "plain");
  }

  return out;
}


/**
 * Extract Google Doc hyperlinks from a Structure cell.
 *
 * Writers hyperlink each written page's Doc onto its Structure entry, so this
 * is the primary link source. Each link is labelled with the FULL text of the
 * structure line it sits on (the page entry — e.g. "Host cities" or
 * "/host-cities/"), even when only part of that line carries the hyperlink.
 * Run offsets are computed by accumulating run text lengths (runs are returned
 * in order and cover the cell text contiguously).
 */
function extractLinksFromStructure_(richValue) {
  var out = [];
  if (!richValue || typeof richValue.getRuns !== "function") return out;
  var fullText = typeof richValue.getText === "function" ? richValue.getText() : "";
  var lines = computeLineSpans_(fullText);
  var runs = richValue.getRuns();
  var pos = 0;
  for (var i = 0; i < runs.length; i++) {
    var runText = String(runs[i].getText() || "");
    var url = typeof runs[i].getLinkUrl === "function" ? runs[i].getLinkUrl() : null;
    if (url) {
      var id = docIdFromUrl_(url);
      if (id) {
        out.push({
          label: lineLabelAt_(lines, pos) || runText.trim(),
          url: url,
          docId: id,
          kind: "hyperlink",
        });
      }
    }
    pos += runText.length;
  }
  return out;
}


/** Build [{start,end,text}] spans for each newline-separated line of `text`. */
function computeLineSpans_(text) {
  var spans = [];
  var parts = String(text || "").split("\n");
  var pos = 0;
  for (var i = 0; i < parts.length; i++) {
    var len = parts[i].length;
    spans.push({ start: pos, end: pos + len, text: parts[i].trim() });
    pos += len + 1; // +1 for the "\n" that split consumed
  }
  return spans;
}


/** Trimmed text of the line span containing character index `idx`. */
function lineLabelAt_(spans, idx) {
  for (var i = 0; i < spans.length; i++) {
    if (idx >= spans[i].start && idx <= spans[i].end) return spans[i].text;
  }
  return "";
}


/** Dedupe links by docId, first-seen wins (Structure before the Links column). */
function dedupeLinks_(links) {
  var out = [];
  var seen = {};
  for (var i = 0; i < links.length; i++) {
    var id = links[i].docId;
    if (!id || seen[id]) continue;
    seen[id] = true;
    out.push(links[i]);
  }
  return out;
}


/** Extract a Google Doc ID from any of its URL shapes. */
function docIdFromUrl_(url) {
  if (!url) return "";
  var m = url.match(/\/document\/d\/([a-zA-Z0-9_-]+)/);
  if (m) return m[1];
  m = url.match(/[?&]id=([a-zA-Z0-9_-]+)/);
  if (m) return m[1];
  // open?id= style already covered above; bail otherwise.
  return "";
}


/** Export one Doc to HTML using the user's OAuth token. */
function exportDoc_(docId) {
  try {
    var title = "";
    try {
      title = DriveApp.getFileById(docId).getName();
    } catch (e) {
      // Not fatal — keep going, title can be recovered from HTML later.
    }
    var url = "https://docs.google.com/feeds/download/documents/export/Export" +
      "?id=" + encodeURIComponent(docId) + "&exportFormat=html";
    var resp = UrlFetchApp.fetch(url, {
      headers: { Authorization: "Bearer " + ScriptApp.getOAuthToken() },
      muteHttpExceptions: true,
      followRedirects: true,
    });
    var code = resp.getResponseCode();
    if (code !== 200) {
      return { ok: false, title: title, error: "Export failed: HTTP " + code };
    }
    return { ok: true, title: title, html: resp.getContentText() };
  } catch (err) {
    return { ok: false, error: "Export error: " + (err && err.message ? err.message : String(err)) };
  }
}


/**
 * Turn a Structure cell into a page list. Prefer newline-separated lines;
 * fall back to commas / semicolons / bullets if it's a single line.
 */
function parseStructure_(raw) {
  if (!raw) return [];
  var parts;
  if (/\n/.test(raw)) {
    parts = raw.split(/\r?\n/);
  } else if (/[;,]/.test(raw)) {
    parts = raw.split(/[;,]/);
  } else {
    parts = [raw];
  }
  return parts
    .map(function (s) { return s.replace(/^[\s•\-\*\d.\)]+/, "").trim(); })
    .filter(function (s) { return s.length > 0; });
}


/** yyyymmdd-hhmmss for filenames. */
function formatStamp_(d) {
  function p(n) { return (n < 10 ? "0" : "") + n; }
  return "" + d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) +
    "-" + p(d.getHours()) + p(d.getMinutes()) + p(d.getSeconds());
}
