import type { MetricsSummary, SummaryReport, TrendsResponse } from "../types/api";
import { api, downloadFile, params, type DownloadedFile } from "./apiClient";

export interface DateWindow {
  date_from?: string;
  date_to?: string;
}

export async function getSummary(window: DateWindow = {}): Promise<MetricsSummary> {
  return (await api.get<MetricsSummary>("/metrics/summary", { params: params({ ...window }) })).data;
}

export async function getTrends(bucket: "day" | "hour", window: DateWindow = {}): Promise<TrendsResponse> {
  return (await api.get<TrendsResponse>("/metrics/trends", { params: params({ bucket, ...window }) })).data;
}

export async function getSummaryReport(window: DateWindow = {}): Promise<SummaryReport> {
  return (await api.get<SummaryReport>("/reports/summary", { params: params({ ...window, format: "json" }) })).data;
}

export async function downloadSummaryReport(format: "csv" | "json", window: DateWindow = {}): Promise<DownloadedFile> {
  return downloadFile("/reports/summary", params({ ...window, format }), `cybersentinel-summary.${format}`);
}
