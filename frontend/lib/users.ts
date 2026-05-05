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

export function deleteUser(id: number): Promise<void> {
  return api<void>(`/users/${id}`, { method: "DELETE" });
}
