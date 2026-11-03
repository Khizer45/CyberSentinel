/**
 * Named aliases over the types generated from the backend's OpenAPI document (src/types/api.generated.ts).
 * Regenerate with `npm run generate:api` after API changes; `npm run typecheck` then flags any drift.
 */
import type { components } from "./api.generated";

type S = components["schemas"];

export type UserRole = S["UserRole"];
export type User = S["UserRead"];
export type UserRef = S["UserRef"];
export type UserCreate = S["UserCreate"];
export type UserUpdate = S["UserUpdate"];
export type TokenResponse = S["TokenResponse"];

export type Dataset = S["DatasetRead"];
export type DatasetStatus = S["DatasetStatus"];
export type DatasetSchema = S["DatasetSchemaRead"];

export type ModelVersion = S["ModelVersionRead"];
export type ModelStatus = S["ModelStatus"];
export type ModelVerifyResult = S["ModelVerifyResult"];

export type AnalysisMode = S["AnalysisMode"];
export type AnalysisJob = S["AnalysisJobRead"];
export type AnalysisCreate = S["AnalysisCreate"];
export type JobStatus = S["JobStatus"];

export type Prediction = S["PredictionRead"];
export type PredictionDetail = S["PredictionDetail"];
export type Explanation = S["Explanation"];
export type TopFeature = S["TopFeature"];
export type Review = S["ReviewRead"];
export type ReviewCreate = S["ReviewCreate"];
export type Disposition = S["Disposition"];

export type Alert = S["AlertRead"];
export type AlertStatus = S["AlertStatus"];
export type RiskBand = S["RiskBand"];

export type MetricsSummary = S["MetricsSummary"];
export type TrendsResponse = S["TrendsResponse"];
export type ModelMetrics = S["ModelMetricsRead"];
export type SummaryReport = S["SummaryReport"];

export type ExperimentSummary = S["ExperimentSummary"];
export type ExperimentRecord = S["ExperimentRecord"];

export type AuditLog = S["AuditLogRead"];
export type AuditOutcome = S["AuditOutcome"];

export type QuickAnalysisResponse = S["QuickAnalysisResponse"];
export type QuickResult = S["QuickResult"];

export type RiskPolicyResponse = S["RiskPolicyResponse"];
export type SystemInfo = S["SystemInfo"];
export type HealthResponse = S["HealthResponse"];
export type ErrorResponse = S["ErrorResponse"];

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export const RISK_BANDS: RiskBand[] = ["low", "medium", "high", "critical"];
export const DISPOSITIONS: Disposition[] = ["true_positive", "false_positive", "benign", "duplicate", "needs_investigation"];
export const ALERT_STATUSES: AlertStatus[] = ["open", "investigating", "closed"];
export const ACTIVE_JOB_STATUSES: JobStatus[] = ["queued", "validating", "running"];
