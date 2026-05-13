import { api } from "./api";
import type {
  Role,
  User,
  UserCreatePayload,
  UserUpdatePayload,
} from "./types";

export function listUsers(): Promise<User[]> {
  return api<User[]>("/users");
}

export function listRoles(): Promise<Role[]> {
  return api<Role[]>("/roles");
}

export function createUser(payload: UserCreatePayload): Promise<User> {
  return api<User>("/users", { method: "POST", body: payload });
}

export function updateUser(id: number, patch: UserUpdatePayload): Promise<User> {
  return api<User>(`/users/${id}`, { method: "PATCH", body: patch });
}

export function resetUserPassword(id: number, newPassword: string): Promise<User> {
  return api<User>(`/users/${id}/reset-password`, {
    method: "POST",
    body: { new_password: newPassword },
  });
}

/** Soft-delete (move to trash). Invalidates the user's JWT on next request. */
export function deleteUser(id: number): Promise<void> {
  return api<void>(`/users/${id}`, { method: "DELETE" });
}

// ----- Trash -----

export function listUserTrash(): Promise<User[]> {
  return api<User[]>("/users/trash");
}

export function getUserTrashCount(): Promise<{ count: number }> {
  return api<{ count: number }>("/users/trash/count");
}

export function previewTrashedUser(id: number): Promise<User> {
  return api<User>(`/users/trash/${id}`);
}

export function restoreUser(id: number): Promise<User> {
  return api<User>(`/users/${id}/restore`, { method: "POST" });
}

export function permanentlyDeleteUser(id: number): Promise<void> {
  return api<void>(`/users/${id}/permanent`, { method: "DELETE" });
}

export function emptyUserTrash(): Promise<{ deleted: number }> {
  return api<{ deleted: number }>("/users/trash", { method: "DELETE" });
}

export function bulkRestoreUsers(
  ids: number[],
): Promise<{ restored: number; skipped_email_conflicts: string[] }> {
  return api<{ restored: number; skipped_email_conflicts: string[] }>(
    "/users/trash/bulk-restore",
    { method: "POST", body: { ids } },
  );
}

export function bulkPermanentlyDeleteUsers(ids: number[]): Promise<{ deleted: number }> {
  return api<{ deleted: number }>("/users/trash/bulk", {
    method: "DELETE",
    body: { ids },
  });
}

export interface TrashRetention {
  days: number;
  default: number;
  max: number;
}

export function getUserTrashRetention(): Promise<TrashRetention> {
  return api<TrashRetention>("/users/trash/retention");
}

export function setUserTrashRetention(days: number): Promise<TrashRetention> {
  return api<TrashRetention>("/users/trash/retention", {
    method: "PUT",
    body: { days },
  });
}
