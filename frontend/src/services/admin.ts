import type { AuditLog, Page, User, UserCreate, UserUpdate } from "../types/api";
import { api, params } from "./apiClient";

export async function listUsers(query: { role?: string; is_active?: boolean; q?: string; limit?: number; offset?: number } = {}): Promise<Page<User>> {
  return (await api.get<Page<User>>("/admin/users", { params: params({ ...query }) })).data;
}

export async function createUser(payload: UserCreate): Promise<User> {
  return (await api.post<User>("/admin/users", payload)).data;
}

export async function updateUser(id: string, payload: UserUpdate): Promise<User> {
  return (await api.patch<User>(`/admin/users/${encodeURIComponent(id)}`, payload)).data;
}

export async function resetPassword(id: string, newPassword: string): Promise<void> {
  await api.post(`/admin/users/${encodeURIComponent(id)}/reset-password`, { new_password: newPassword });
}

export interface AuditQuery {
  action?: string;
  outcome?: string;
  resource_type?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

export async function listAuditLogs(query: AuditQuery = {}): Promise<Page<AuditLog>> {
  return (await api.get<Page<AuditLog>>("/audit-logs", { params: params({ ...query }) })).data;
}
