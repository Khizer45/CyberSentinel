/** Typed builders for API objects used in component tests (shapes follow the generated OpenAPI types). */
import type { AnalysisJob, Dataset, DatasetSchema, Explanation, ModelVersion, PredictionDetail, SystemInfo, User } from "../types/api";

const NOW = "2026-11-01T10:00:00Z";

export function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: "00000000-0000-4000-8000-000000000001",
    email: "analyst@example.org",
    display_name: "Ana Analyst",
    role: "analyst",
    is_active: true,
    last_login_at: NOW,
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  };
}

export function makeModel(overrides: Partial<ModelVersion> = {}): ModelVersion {
  return {
    id: "10000000-0000-4000-8000-000000000001",
    model_name: "unsw-nb15-random-forest-multiclass",
    version: "1.0.0",
    model_type: "ensemble",
    dataset_family: "unsw_nb15",
    feature_schema_version: "unsw_nb15-v1",
    preprocessing_version: "prep-1",
    description: "Random forest with an Isolation Forest",
    explanation_method: "tree_path_attribution",
    probability_calibrated: false,
    status: "approved",
    status_reason: null,
    supported_modes: ["combined", "classification", "anomaly"],
    task: "multiclass",
    threshold_config: { min_confidence: 0.5 },
    label_map: null,
    metrics: null,
    artifact_sha256: "a".repeat(64),
    approved_at: NOW,
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  };
}

export function makeDataset(overrides: Partial<Dataset> = {}): Dataset {
  return {
    id: "20000000-0000-4000-8000-000000000001",
    name: "unsw-test-flows",
    original_filename: "unsw-test-flows.csv",
    owner: { id: makeUser().id, email: makeUser().email, display_name: makeUser().display_name },
    row_count: 1200,
    schema_version: "unsw_nb15-v1",
    sha256: "b".repeat(64),
    size_bytes: 52_000,
    source_type: "upload",
    status: "validated",
    has_ground_truth: true,
    validation_report: { accepted: true, rows: 1200, schema_version: "unsw_nb15-v1", warnings: [] },
    deleted_at: null,
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  };
}

export function makeSchema(overrides: Partial<DatasetSchema> = {}): DatasetSchema {
  return {
    schema_version: "unsw_nb15-v1",
    family: "unsw_nb15",
    display_name: "UNSW-NB15",
    source: "UNSW Canberra",
    features: [
      { name: "dur", dtype: "float", description: "" },
      { name: "proto", dtype: "categorical", description: "" },
      { name: "sbytes", dtype: "float", description: "" },
    ],
    identifier_columns: ["srcip", "dstip"],
    label_columns: ["label", "attack_cat"],
    notes: [],
    ...overrides,
  };
}

export function makeExplanation(overrides: Partial<Explanation> = {}): Explanation {
  return {
    method: "tree_path_attribution",
    method_family: "model_attribution",
    target_label: "DoS",
    units: "probability",
    top_features: [
      { feature: "sbytes", value: 123456, contribution: 0.21, direction: "supports", baseline: 512 },
      { feature: "dur", value: 0.01, contribution: -0.05, direction: "opposes", baseline: 0.3 },
    ],
    reason_codes: [{ code: "attribution", feature: "sbytes", text: "sbytes = 123456 (baseline 512) increased the model's score for 'DoS'." }],
    class_scores: [
      { label: "DoS", score: 0.71 },
      { label: "Benign", score: 0.2 },
    ],
    anomaly: { score: 0.62, threshold: 0.55, is_anomaly: true, score_direction: "higher_is_more_anomalous" },
    risk: {
      policy_version: "1.0.0",
      classifier_component: 0.8,
      anomaly_component: 0.6,
      weights: { classifier: 0.7, anomaly: 0.3 },
      floor_applied: null,
      risk_score: 74,
      risk_band: "high",
    },
    scores_calibrated: false,
    fallback_reason: null,
    disclaimer: "Attributions describe model behaviour, not causality.",
    ...overrides,
  };
}

export function makePredictionDetail(overrides: Partial<PredictionDetail> = {}): PredictionDetail {
  return {
    id: "30000000-0000-4000-8000-000000000001",
    analysis_job_id: "40000000-0000-4000-8000-000000000001",
    record_index: 41,
    predicted_label: "DoS",
    true_label: null,
    probability: null,
    classifier_score: 0.8,
    anomaly_score: 0.62,
    is_anomaly: true,
    risk_score: 74,
    risk_band: "high",
    is_alert: true,
    alert_status: "open",
    scores_calibrated: false,
    explanation: makeExplanation(),
    flow_context: { src_ip: "ip_0123456789abcdef", dst_port: 80, proto: "tcp" },
    dataset: { id: makeDataset().id, name: "unsw-test-flows", schema_version: "unsw_nb15-v1" },
    job: {
      id: "40000000-0000-4000-8000-000000000001",
      status: "completed",
      requested_mode: "combined",
      risk_policy_version: "1.0.0",
      completed_at: NOW,
    },
    model_version: { id: makeModel().id, model_name: makeModel().model_name, model_type: "ensemble", version: "1.0.0" },
    reviews: [],
    created_at: NOW,
    ...overrides,
  };
}

export function makeJob(overrides: Partial<AnalysisJob> = {}): AnalysisJob {
  return {
    id: "40000000-0000-4000-8000-000000000001",
    status: "completed",
    requested_mode: "combined",
    progress: 1,
    processed_rows: 1200,
    input_rows: 1200,
    dataset: { id: makeDataset().id, name: "unsw-test-flows", schema_version: "unsw_nb15-v1" },
    model_version: { id: makeModel().id, model_name: makeModel().model_name, model_type: "ensemble", version: "1.0.0" },
    submitter: { id: makeUser().id, email: makeUser().email, display_name: makeUser().display_name },
    risk_policy_version: "1.0.0",
    summary: null,
    error_code: null,
    error_message: null,
    started_at: NOW,
    completed_at: NOW,
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  };
}

export function makeSystemInfo(overrides: Partial<SystemInfo> = {}): SystemInfo {
  return {
    app_name: "CyberSentinel",
    version: "1.0.0",
    environment: "development",
    explain_scope: "alerts_and_review",
    risk_policy_version: "1.0.0",
    supported_schemas: ["cicids2017-v1", "unsw_nb15-v1"],
    limits: { max_upload_mb: 1, max_upload_rows: 1000, quick_analysis_max_records: 5, export_max_rows: 100 },
    ...overrides,
  };
}
