import type { ExperimentRecord, ExperimentSummary, ModelMetrics, ModelStatus, ModelVerifyResult, ModelVersion } from "../types/api";
import { api, params } from "./apiClient";

export async function listModels(query: { status?: ModelStatus[]; dataset_family?: string } = {}): Promise<ModelVersion[]> {
  return (await api.get<ModelVersion[]>("/models", { params: params({ ...query }) })).data;
}

export async function getModel(id: string): Promise<ModelVersion> {
  return (await api.get<ModelVersion>(`/models/${encodeURIComponent(id)}`)).data;
}

export async function changeModelStatus(id: string, status: ModelStatus, reason?: string): Promise<ModelVersion> {
  return (await api.patch<ModelVersion>(`/models/${encodeURIComponent(id)}/status`, { status, reason: reason || null })).data;
}

export async function verifyModel(id: string): Promise<ModelVerifyResult> {
  return (await api.post<ModelVerifyResult>(`/models/${encodeURIComponent(id)}/verify`)).data;
}

export async function listModelMetrics(): Promise<ModelMetrics[]> {
  return (await api.get<ModelMetrics[]>("/metrics/models")).data;
}

export async function listExperiments(query: { dataset_family?: string; experiment_type?: string } = {}): Promise<ExperimentSummary[]> {
  return (await api.get<ExperimentSummary[]>("/experiments", { params: params({ ...query }) })).data;
}

export async function getExperiment(id: string): Promise<ExperimentRecord> {
  return (await api.get<ExperimentRecord>(`/experiments/${encodeURIComponent(id)}`)).data;
}
