import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, StatusBadge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { JsonView, KeyValueList } from "../components/DataDisplay";
import { DataTable } from "../components/DataTable";
import { ChipGroup } from "../components/FormFields";
import { PageHeader } from "../components/PageHeader";
import { Callout, ErrorCallout } from "../components/States";
import { Chart } from "../components/Chart";
import { METHOD_LABELS } from "../features/alerts/ExplanationView";
import { TabPanel, Tabs } from "../components/Tabs";
import { useToast } from "../components/Toast";
import { MODE_LABELS } from "../features/analysis/modes";
import { useAuth } from "../features/auth/AuthContext";
import { isAdmin } from "../features/auth/roles";
import { ExperimentsPanel } from "../features/models/ExperimentsPanel";
import { MetricsTree } from "../features/models/MetricsTree";
import { useSearchState } from "../hooks/useSearchState";
import { changeModelStatus, listModels, verifyModel } from "../services/models";
import { queryKeys } from "../services/queryKeys";
import type { AnalysisMode, ModelStatus, ModelVerifyResult, ModelVersion } from "../types/api";
import { formatDateTime, humanize } from "../utils/format";

const TABS = [
  { id: "models", label: "Model versions" },
  { id: "experiments", label: "Experiments" },
];
const STATUSES: ModelStatus[] = ["draft", "approved", "retired", "revoked"];
const TRANSITIONS: Record<ModelStatus, ModelStatus[]> = {
  draft: ["approved", "revoked"],
  approved: ["retired", "revoked"],
  retired: ["approved", "revoked"],
  revoked: [],
};
const ACTION_LABELS: Record<ModelStatus, string> = { approved: "Approve", retired: "Retire", revoked: "Revoke", draft: "Draft" };

export function ModelsPage() {
  const { user } = useAuth();
  const admin = isAdmin(user);
  const search = useSearchState();
  const tab = search.get("tab") === "experiments" ? "experiments" : "models";
  return (
    <>
      <PageHeader
        title="Models"
        description="Model versions packaged by the training notebooks and registered by an administrator. Only approved versions can be used for analysis; the API never trains or downloads models."
      />
      <Tabs label="Model information" tabs={TABS} active={tab} onChange={(id) => search.update({ tab: id === "models" ? null : id })} />
      <TabPanel id={tab}>{tab === "models" ? <ModelVersions admin={admin} /> : <ExperimentsPanel />}</TabPanel>
    </>
  );
}

function ModelVersions({ admin }: { admin: boolean }) {
  const search = useSearchState();
  const statuses = search.getAll("status") as ModelStatus[];
  const filter = admin ? { status: statuses.length ? statuses : undefined } : {};
  const models = useQuery({ queryKey: queryKeys.models(filter), queryFn: () => listModels(filter) });
  const selectedId = search.get("model");
  const selected = models.data?.find((model) => model.id === selectedId) ?? null;

  return (
    <div className="stack">
      {models.isSuccess && models.data.length === 0 && statuses.length === 0 ? (
        <Callout tone="warning" title="No models are available">
          {admin
            ? "Train and export a bundle with the notebooks, then run `python -m app.cli models sync` and approve it here. See docs/model_artifact_integration_guide.md."
            : "An administrator has not approved any model yet."}
        </Callout>
      ) : null}
      <Card flush>
        {admin ? (
          <div className="filter-bar">
            <ChipGroup
              label="Status"
              options={STATUSES.map((status) => ({ value: status, label: humanize(status) }))}
              selected={statuses}
              onChange={(values) => search.update({ status: values })}
            />
          </div>
        ) : null}
        <DataTable<ModelVersion>
          caption="Model versions"
          rows={models.data}
          loading={models.isPending}
          error={models.error}
          onRetry={() => void models.refetch()}
          rowKey={(row) => row.id}
          onRowClick={(row) => search.update({ model: row.id }, { resetPage: false })}
          rowLabel={(row) => `Show details of ${row.model_name} ${row.version}`}
          emptyTitle="No model versions match"
          columns={[
            {
              key: "name",
              header: "Model",
              render: (row) => (
                <div className="stack-sm" style={{ gap: 0 }}>
                  <strong className="break">{row.model_name}</strong>
                  <span className="small subtle">version {row.version}</span>
                </div>
              ),
            },
            { key: "type", header: "Type", render: (row) => humanize(row.model_type) },
            { key: "schema", header: "Feature schema", render: (row) => row.feature_schema_version },
            { key: "task", header: "Task", render: (row) => humanize(row.task) },
            {
              key: "calibrated",
              header: "Probabilities",
              render: (row) => (row.probability_calibrated ? <Badge tone="success">Calibrated</Badge> : <Badge>Uncalibrated</Badge>),
            },
            { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
            { key: "updated", header: "Updated", render: (row) => <span className="nowrap">{formatDateTime(row.updated_at)}</span> },
          ]}
        />
      </Card>
      {selected ? <ModelDetail model={selected} admin={admin} onClose={() => search.update({ model: null }, { resetPage: false })} /> : null}
    </div>
  );
}

function ModelDetail({ model, admin, onClose }: { model: ModelVersion; admin: boolean; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [target, setTarget] = useState<ModelStatus | null>(null);
  const [verification, setVerification] = useState<ModelVerifyResult | null>(null);

  const transition = useMutation({
    mutationFn: ({ status, reason }: { status: ModelStatus; reason: string }) => changeModelStatus(model.id, status, reason),
    onSuccess: async (updated) => {
      toast.success(`${updated.model_name} ${updated.version} is now ${updated.status}.`);
      setTarget(null);
      await queryClient.invalidateQueries({ queryKey: queryKeys.modelsAll });
    },
  });
  const verify = useMutation({
    mutationFn: () => verifyModel(model.id),
    onSuccess: (result) => setVerification(result),
  });

  const thresholds = model.threshold_config ?? {};
  return (
    <Card
      title={`${model.model_name} · ${model.version}`}
      subtitle={model.description ?? undefined}
      actions={
        <>
          {admin ? (
            <>
              <Button size="sm" icon="check" loading={verify.isPending} onClick={() => verify.mutate()}>
                Verify artifacts
              </Button>
              {TRANSITIONS[model.status].map((status) => (
                <Button key={status} size="sm" variant={status === "revoked" ? "danger" : status === "approved" ? "primary" : "secondary"} onClick={() => setTarget(status)}>
                  {ACTION_LABELS[status]}
                </Button>
              ))}
            </>
          ) : null}
          <Button size="sm" variant="ghost" icon="close" aria-label="Close model details" onClick={onClose} />
        </>
      }
    >
      <div className="stack">
        {model.status === "revoked" ? (
          <Callout tone="danger" title="Revoked">
            This version can no longer be used. {model.status_reason ? `Reason: ${model.status_reason}` : ""}
          </Callout>
        ) : null}
        <ErrorCallout error={verify.error} />
        {verification ? (
          <Callout tone={verification.verified ? "success" : "danger"} title={verification.verified ? "All integrity checks passed" : "Verification failed"}>
            <ul>
              {verification.checks.map((check) => (
                <li key={check.name}>
                  {check.passed ? "✔" : "✖"} {humanize(check.name)}
                  {check.detail ? ` — ${check.detail}` : ""}
                </li>
              ))}
            </ul>
          </Callout>
        ) : null}
        <div className="grid-2">
          <KeyValueList
            items={[
              { label: "Status", value: <StatusBadge status={model.status} /> },
              { label: "Type", value: humanize(model.model_type) },
              { label: "Task", value: humanize(model.task) },
              { label: "Dataset family", value: model.dataset_family },
              { label: "Feature schema", value: model.feature_schema_version },
              { label: "Preprocessing", value: model.preprocessing_version },
              { label: "Explanation method", value: METHOD_LABELS[model.explanation_method ?? ""] ?? humanize(model.explanation_method) },
              { label: "Probabilities", value: model.probability_calibrated ? "Calibrated" : "Not calibrated — classifier scores only" },
            ]}
          />
          <KeyValueList
            items={[
              {
                label: "Analysis modes",
                value: model.supported_modes.map((mode) => MODE_LABELS[mode as AnalysisMode] ?? mode).join("; "),
              },
              { label: "Approved", value: formatDateTime(model.approved_at) },
              { label: "Registered", value: formatDateTime(model.created_at) },
              { label: "Status note", value: model.status_reason ?? "—" },
              { label: "Manifest SHA-256", value: <code className="break">{model.artifact_sha256}</code> },
            ]}
          />
        </div>
        {Object.keys(thresholds).length ? (
          <div className="stack-sm">
            <h3>Thresholds</h3>
            <MetricsTree value={thresholds} />
          </div>
        ) : null}
        {model.label_map ? (
          <details>
            <summary>Classes and label mapping</summary>
            <JsonView value={model.label_map} />
          </details>
        ) : null}
        <RecordedMetrics metrics={model.metrics} />
      </div>
      <ConfirmDialog
        open={target !== null}
        title={target ? `${ACTION_LABELS[target]} ${model.model_name} ${model.version}?` : ""}
        message={
          target === "approved" ? (
            <p>The artifacts are re-verified (hashes, runtime compatibility, golden parity) before approval. Approved versions become available for analysis.</p>
          ) : target === "revoked" ? (
            <p>Revocation is permanent: the version can never be used again. Existing results remain for traceability.</p>
          ) : (
            <p>Retired versions are no longer offered for new analyses. They can be approved again later.</p>
          )
        }
        confirmLabel={target ? ACTION_LABELS[target] : "Confirm"}
        tone={target === "revoked" ? "danger" : "primary"}
        reasonLabel="Reason"
        reasonRequired={target === "revoked"}
        busy={transition.isPending}
        error={transition.error}
        onConfirm={(reason) => target && transition.mutate({ status: target, reason })}
        onCancel={() => {
          setTarget(null);
          transition.reset();
        }}
      />
    </Card>
  );
}

const KNOWN_METRIC_SECTIONS = ["measured", "calibration", "limitations", "global_feature_importance", "dataset", "runtime"];

/** Metrics stored at registration: the manifest's measured metrics plus training context (see model_registry_service). */
function RecordedMetrics({ metrics }: { metrics: Record<string, unknown> | null }) {
  if (!metrics || Object.keys(metrics).length === 0) {
    return <p className="muted">This bundle does not contain recorded metrics.</p>;
  }
  const limitations = Array.isArray(metrics.limitations) ? metrics.limitations.map(String) : [];
  const importance = (Array.isArray(metrics.global_feature_importance) ? metrics.global_feature_importance : [])
    .filter((item): item is { feature: string; importance: number } => typeof item?.feature === "string" && typeof item?.importance === "number")
    .sort((a, b) => b.importance - a.importance)
    .slice(0, 15);
  const rest = Object.fromEntries(Object.entries(metrics).filter(([key]) => !KNOWN_METRIC_SECTIONS.includes(key)));
  return (
    <div className="stack">
      <div className="stack-sm">
        <h3>Recorded evaluation metrics</h3>
        <p className="small muted">Measured by the training notebooks on the data splits described below and stored in the bundle manifest. They are not re-computed by this server.</p>
        {metrics.measured && typeof metrics.measured === "object" && Object.keys(metrics.measured).length ? (
          <MetricsTree value={metrics.measured} />
        ) : (
          <p className="muted">No measured metrics were recorded for this bundle.</p>
        )}
      </div>
      {metrics.calibration ? (
        <div className="stack-sm">
          <h3>Probability calibration</h3>
          <MetricsTree value={metrics.calibration} />
        </div>
      ) : null}
      {limitations.length ? (
        <Callout tone="warning" title="Documented limitations">
          <ul>
            {limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Callout>
      ) : null}
      {importance.length ? (
        <div className="stack-sm">
          <h3>Global feature importance (top {importance.length})</h3>
          <Chart
            title="Global feature importance"
            kind="hbar"
            height={Math.max(220, importance.length * 24)}
            series={[{ name: "Importance", x: importance.map((item) => item.feature), y: importance.map((item) => item.importance) }]}
          />
        </div>
      ) : null}
      {metrics.dataset ? (
        <details>
          <summary>Training data</summary>
          <MetricsTree value={metrics.dataset} depth={1} />
        </details>
      ) : null}
      {metrics.runtime ? (
        <details>
          <summary>Training runtime versions</summary>
          <MetricsTree value={metrics.runtime} depth={1} />
        </details>
      ) : null}
      {Object.keys(rest).length ? <MetricsTree value={rest} /> : null}
    </div>
  );
}
