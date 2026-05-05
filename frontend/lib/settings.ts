import { api } from "./api";
import type { ConnectionTestResult, Provider, ProviderUpdate } from "./types";

export function listProviders(): Promise<Provider[]> {
  return api<Provider[]>("/settings/providers");
}

export function updateProvider(
  code: string,
  patch: ProviderUpdate,
): Promise<Provider> {
  return api<Provider>(`/settings/providers/${code}`, {
    method: "PATCH",
    body: patch,
  });
}

export interface TestConnectionPayload {
  /** If provided, test this key. Otherwise the stored key is decrypted and used. */
  api_key?: string;
  model?: string;
}

export function testProviderConnection(
  code: string,
  payload: TestConnectionPayload = {},
): Promise<ConnectionTestResult> {
  return api<ConnectionTestResult>(`/settings/providers/${code}/test`, {
    method: "POST",
    body: payload,
  });
}
