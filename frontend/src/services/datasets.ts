import type { Dataset, DatasetSchema, Page } from "../types/api";
import { api, params } from "./apiClient";

export interface DatasetQuery {
  status?: string;
  schema_version?: string;
  q?: string;
  sort?: string;
  limit?: number;
  offset?: number;
  include_deleted?: boolean;
}

export async function listDatasets(query: DatasetQuery = {}): Promise<Page<Dataset>> {
  return (await api.get<Page<Dataset>>("/datasets", { params: params({ ...query }) })).data;
}

export async function getDataset(id: string): Promise<Dataset> {
  return (await api.get<Dataset>(`/datasets/${encodeURIComponent(id)}`)).data;
}

export async function deleteDataset(id: string): Promise<void> {
  await api.delete(`/datasets/${encodeURIComponent(id)}`);
}

export async function listDatasetSchemas(): Promise<DatasetSchema[]> {
  return (await api.get<DatasetSchema[]>("/dataset-schemas")).data;
}

export async function uploadDataset(
  file: File,
  options: { name?: string; schemaVersion?: string },
  onProgress?: (fraction: number) => void,
): Promise<Dataset> {
  const form = new FormData();
  form.append("file", file);
  if (options.name) form.append("name", options.name);
  if (options.schemaVersion && options.schemaVersion !== "auto") form.append("schema_version", options.schemaVersion);
  const response = await api.post<Dataset>("/datasets", form, {
    timeout: 15 * 60_000,
    onUploadProgress: (event) => {
      if (onProgress && event.total) onProgress(event.loaded / event.total);
    },
  });
  return response.data;
}
