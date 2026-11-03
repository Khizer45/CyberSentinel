import type { AnalysisCreate, AnalysisJob, Page, Prediction, PredictionDetail, QuickAnalysisResponse, Review, ReviewCreate } from "../types/api";
import { api, downloadFile, params, type DownloadedFile } from "./apiClient";

export interface JobQuery {
  status?: string;
  dataset_id?: string;
  model_version_id?: string;
  sort?: string;
  limit?: number;
  offset?: number;
}

export interface PredictionQuery {
  label?: string[];
  risk_band?: string[];
  is_anomaly?: boolean;
  is_alert?: boolean;
  min_risk?: number;
  max_risk?: number;
  sort?: string;
  limit?: number;
  offset?: number;
}

export async function listJobs(query: JobQuery = {}): Promise<Page<AnalysisJob>> {
  return (await api.get<Page<AnalysisJob>>("/analyses", { params: params({ ...query }) })).data;
}

export async function getJob(id: string): Promise<AnalysisJob> {
  return (await api.get<AnalysisJob>(`/analyses/${encodeURIComponent(id)}`)).data;
}

export async function createJob(payload: AnalysisCreate): Promise<AnalysisJob> {
  return (await api.post<AnalysisJob>("/analyses", payload)).data;
}

export async function cancelJob(id: string): Promise<AnalysisJob> {
  return (await api.post<AnalysisJob>(`/analyses/${encodeURIComponent(id)}/cancel`)).data;
}

export async function listPredictions(jobId: string, query: PredictionQuery = {}): Promise<Page<Prediction>> {
  return (await api.get<Page<Prediction>>(`/analyses/${encodeURIComponent(jobId)}/predictions`, { params: params({ ...query }) })).data;
}

export async function getPrediction(id: string): Promise<PredictionDetail> {
  return (await api.get<PredictionDetail>(`/predictions/${encodeURIComponent(id)}`)).data;
}

export async function addReview(predictionId: string, payload: ReviewCreate): Promise<Review> {
  return (await api.post<Review>(`/predictions/${encodeURIComponent(predictionId)}/reviews`, payload)).data;
}

export async function exportJob(jobId: string, format: "csv" | "json", query: PredictionQuery = {}): Promise<DownloadedFile> {
  const { sort: _sort, limit: _limit, offset: _offset, ...filters } = query;
  return downloadFile(`/analyses/${encodeURIComponent(jobId)}/export`, params({ ...filters, format }), `analysis-${jobId}.${format}`);
}

export type FeatureValue = number | string | null;

export async function quickAnalyze(
  modelVersionId: string,
  mode: string,
  records: Record<string, FeatureValue>[],
): Promise<QuickAnalysisResponse> {
  const body = { model_version_id: modelVersionId, mode, records: records.map((features) => ({ features })) };
  return (await api.post<QuickAnalysisResponse>("/analyze/batch", body)).data;
}

export async function listReviews(predictionId: string): Promise<Review[]> {
  return (await api.get<Review[]>(`/predictions/${encodeURIComponent(predictionId)}/reviews`)).data;
}
