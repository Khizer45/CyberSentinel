import type { TokenResponse, User } from "../types/api";
import { api } from "./apiClient";

export async function login(email: string, password: string): Promise<TokenResponse> {
  return (await api.post<TokenResponse>("/auth/login", { email, password })).data;
}

export async function refreshSession(): Promise<TokenResponse> {
  return (await api.post<TokenResponse>("/auth/refresh")).data;
}

export async function logout(): Promise<void> {
  await api.post("/auth/logout");
}

export async function fetchMe(): Promise<User> {
  return (await api.get<User>("/auth/me")).data;
}

export async function updateProfile(displayName: string): Promise<User> {
  return (await api.patch<User>("/auth/me", { display_name: displayName })).data;
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await api.post("/auth/change-password", { current_password: currentPassword, new_password: newPassword });
}
