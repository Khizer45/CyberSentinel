import { useQuery } from "@tanstack/react-query";
import { getSystemInfo } from "../services/system";

export interface ServerLimits {
  maxUploadMb: number;
  maxUploadRows: number;
  quickAnalysisMaxRecords: number;
  exportMaxRows: number;
}

const DEFAULTS: ServerLimits = { maxUploadMb: 200, maxUploadRows: 1_000_000, quickAnalysisMaxRecords: 100, exportMaxRows: 100_000 };

function numberOr(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

/** Limits published by ``GET /system/info``; the server enforces them regardless of what the UI shows. */
export function useServerLimits(): ServerLimits {
  const { data } = useQuery({ queryKey: ["system-info"], queryFn: getSystemInfo, staleTime: 5 * 60_000 });
  const limits = (data?.limits ?? {}) as Record<string, unknown>;
  return {
    maxUploadMb: numberOr(limits.max_upload_mb, DEFAULTS.maxUploadMb),
    maxUploadRows: numberOr(limits.max_upload_rows, DEFAULTS.maxUploadRows),
    quickAnalysisMaxRecords: numberOr(limits.quick_analysis_max_records, DEFAULTS.quickAnalysisMaxRecords),
    exportMaxRows: numberOr(limits.export_max_rows, DEFAULTS.exportMaxRows),
  };
}
