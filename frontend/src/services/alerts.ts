import type { Alert, Page, PredictionDetail } from "../types/api";
import { api, downloadFile, params, type DownloadedFile } from "./apiClient";

export interface AlertQuery {
  severity?: string[];
  status?: string[];
  label?: string[];
  analysis_job_id?: string;
  dataset_id?: string;
  date_from?: string;
  date_to?: string;
  ip?: string;
  sort?: string;
  limit?: number;
  offset?: number;
}

export async function listAlerts(query: AlertQuery = {}): Promise<Page<Alert>> {
  return (await api.get<Page<Alert>>("/alerts", { params: params({ ...query }) })).data;
}

export async function getAlert(id: string): Promise<PredictionDetail> {
  return (await api.get<PredictionDetail>(`/alerts/${encodeURIComponent(id)}`)).data;
}

export async function exportAlerts(format: "csv" | "json", query: AlertQuery = {}): Promise<DownloadedFile> {
  const { sort: _sort, limit: _limit, offset: _offset, ...filters } = query;
  return downloadFile("/alerts/export", params({ ...filters, format }), `alerts.${format}`);
}
