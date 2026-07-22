import { api } from "./api";

// Mirrors backend app/schemas/share.py.

/** Owner-side view of a public share link. Build the URL with `shareUrl`. */
export interface ShareLink {
  id: number;
  token: string;
  row_id: number;
  column_id: number;
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
}

/** What an anonymous visitor gets. Deliberately minimal — no table name. */
export interface SharedCell {
  content: string;
  column_name: string;
  row_number: number;
  expires_at: string;
}

/** The cell's active link, or null when it isn't shared. */
export function getCellShareLink(
  tableId: number,
  rowId: number,
  columnId: number,
): Promise<ShareLink | null> {
  return api<ShareLink | null>(
    `/library/tables/${tableId}/cells/${rowId}/${columnId}/share`,
  );
}

/** Mint (or re-use) a public link to this cell. Idempotent while one is live. */
export function createCellShareLink(
  tableId: number,
  rowId: number,
  columnId: number,
): Promise<ShareLink> {
  return api<ShareLink>(
    `/library/tables/${tableId}/cells/${rowId}/${columnId}/share`,
    { method: "POST" },
  );
}

/** Kill a link immediately — the public URL 404s from here on. */
export function revokeCellShareLink(linkId: number): Promise<void> {
  return api<void>(`/library/share-links/${linkId}`, { method: "DELETE" });
}

/** Public read — no auth header (the recipient has no account). */
export function getSharedCell(token: string): Promise<SharedCell> {
  return api<SharedCell>(`/share/${encodeURIComponent(token)}`, {
    noAuth: true,
  });
}

/** The absolute URL to hand to someone. */
export function shareUrl(token: string): string {
  const origin =
    typeof window !== "undefined" ? window.location.origin : "";
  return `${origin}/share/${token}`;
}
