"use client";

import { AutotoolSharedTables } from "@/components/AutotoolSharedTables";

/**
 * /publish/autotool — the shared-tables list + send view (admin + manager).
 *
 * The connection config (X-Api-Key + target ImportPosts URL) moved to the
 * admin-only Settings page ("Autotool" tab), so this page never shows the
 * proxy credentials; managers can still publish shared tables from here.
 */
export default function AutotoolPage() {
  return (
    <div className="p-5">
      <AutotoolSharedTables />
    </div>
  );
}
