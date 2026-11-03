import type { HealthResponse, RiskPolicyResponse, SystemInfo } from "../types/api";
import { api } from "./apiClient";

export async function getSystemInfo(): Promise<SystemInfo> {
  return (await api.get<SystemInfo>("/system/info")).data;
}

export async function getRiskPolicy(): Promise<RiskPolicyResponse> {
  return (await api.get<RiskPolicyResponse>("/risk-policy")).data;
}

export async function getHealth(): Promise<HealthResponse> {
  return (await api.get<HealthResponse>("/health", { validateStatus: (s) => s === 200 || s === 503 })).data;
}
