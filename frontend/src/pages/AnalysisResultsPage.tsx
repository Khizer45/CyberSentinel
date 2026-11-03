import { useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router";
import { LabelBadge, RiskBadge, StatusBadge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { KeyValueList, ProgressBar } from "../components/DataDisplay";
import { DataTable } from "../components/DataTable";
import { Checkbox, ChipGroup, SelectField, TextField } from "../components/FormFields";
import { PageHeader } from "../components/PageHeader";
import { Pagination } from "../components/Pagination";
import { ScoreSemantics } from "../components/ScoreSemantics";
import { Callout, ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/Toast";
import { JobSummary } from "../features/analysis/JobSummary";
import { MODE_LABELS } from "../features/analysis/modes";
import { useSearchState } from "../hooks/useSearchState";
import { cancelJob, exportJob, getJob, listPredictions, type PredictionQuery } from "../services/analyses";
import { queryKeys } from "../services/queryKeys";
import { RISK_BANDS, type AnalysisJob, type Prediction } from "../types/api";
import { saveBlob } from "../utils/download";
import { errorMessage } from "../utils/errors";
import { formatDateTime, formatNumber, formatScore, humanize } from "../utils/format";
import { isActive } from "./AnalysisJobsPage";

export function AnalysisResultsPage() {
  const { jobId = "" } = useParams();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [confirmCancel, setConfirmCancel] = useState(false);
  const job = useQuery({
    queryKey: queryKeys.job(jobId),
    queryFn: () => getJob(jobId),
    refetchInterval: (state) => (state.state.data && isActive(state.state.data) ? 2000 : false),
  });
  const cancel = useMutation({
    mutationFn: () => cancelJob(jobId),
    onSuccess: async (updated) => {
      queryClient.setQueryData(queryKeys.job(jobId), updated);
      setConfirmCancel(false);
      toast.info("Cancellation requested.");
      await queryClient.invalidateQueries({ queryKey: queryKeys.jobsAll });
    },
  });

  if (job.isPending) return <LoadingState label="Loading analysis…" />;
  if (job.isError) {
    return (
      <>
        <PageHeader title="Analysis" back={{ to: "/analyses", label: "Analysis jobs" }} />
        <Card>
          <ErrorState error={job.error} onRetry={() => void job.refetch()} />
        </Card>
      </>
    );
  }
  const data = job.data;
  return (
    <>
      <PageHeader
        title={`Results · ${data.dataset.name}`}
        description={`${data.model_version.model_name} ${data.model_version.version} · ${MODE_LABELS[data.requested_mode]}`}
        back={{ to: "/analyses", label: "Analysis jobs" }}
        actions={
          isActive(data) ? (
            <Button icon="stop" onClick={() => setConfirmCancel(true)}>
              Cancel job
            </Button>
          ) : null
        }
      />
      <JobHeader job={data} />
      {data.status === "completed" ? (
        <>
          {data.summary ? <JobSummary summary={data.summary} /> : null}
          <PredictionsSection job={data} />
        </>
      ) : null}
      <ConfirmDialog
        open={confirmCancel}
        title="Cancel analysis?"
        message={<p>The job stops at the next checkpoint and partial predictions are deleted.</p>}
        confirmLabel="Cancel job"
        busy={cancel.isPending}
        error={cancel.error}
        onConfirm={() => cancel.mutate()}
        onCancel={() => setConfirmCancel(false)}
      />
    </>
  );
}

function JobHeader({ job }: { job: AnalysisJob }) {
  return (
    <Card>
      <div className="stack">
        <div className="row-between">
          <StatusBadge status={job.status} />
          <span className="small muted">Job {job.id}</span>
        </div>
        {isActive(job) ? (
          <div className="stack-sm">
            <ProgressBar value={job.progress} label="Analysis progress" />
            <span className="small muted">
              {humanize(job.status)} · {formatNumber(job.processed_rows)} of {formatNumber(job.input_rows)} records processed. This page updates
              automatically.
            </span>
          </div>
        ) : null}
        {job.status === "failed" ? (
          <Callout tone="danger" title="The analysis failed">
            <p>{job.error_message ?? "The job could not be completed."}</p>
            {job.error_code ? <p className="small subtle">Error code: {job.error_code}</p> : null}
            <p className="small">No partial results are kept. Fix the cause (for example, ask an administrator to check the model) and start a new job.</p>
          </Callout>
        ) : null}
        {job.status === "cancelled" ? <Callout tone="warning">This job was cancelled; partial results were discarded.</Callout> : null}
        <KeyValueList
          items={[
            { label: "Dataset", value: `${job.dataset.name} (${job.dataset.schema_version ?? "?"})` },
            { label: "Model", value: `${job.model_version.model_name} ${job.model_version.version} · ${humanize(job.model_version.model_type)}` },
            { label: "Risk policy", value: job.risk_policy_version },
            { label: "Submitted by", value: `${job.submitter.display_name} · ${formatDateTime(job.created_at)}` },
            { label: "Started", value: formatDateTime(job.started_at) },
            { label: "Completed", value: formatDateTime(job.completed_at) },
          ]}
        />
      </div>
    </Card>
  );
}

function PredictionsSection({ job }: { job: AnalysisJob }) {
  const navigate = useNavigate();
  const toast = useToast();
  const search = useSearchState();
  const [exporting, setExporting] = useState<"csv" | "json" | null>(null);
  const labels = Object.keys(((job.summary?.label_counts ?? {}) as Record<string, number>) || {}).sort();
  const minRisk = search.get("min_risk");

  const query: PredictionQuery = {
    risk_band: search.getAll("band"),
    label: search.get("label") ? [search.get("label")] : undefined,
    is_alert: search.getBoolean("alerts") === true ? true : undefined,
    is_anomaly: search.getBoolean("anomalies") === true ? true : undefined,
    min_risk: minRisk !== "" && Number.isFinite(Number(minRisk)) ? Number(minRisk) : undefined,
    sort: search.get("sort", "-risk_score"),
    limit: search.getNumber("limit", 25),
    offset: search.getNumber("offset", 0),
  };
  const predictions = useQuery({
    queryKey: queryKeys.predictions(job.id, query),
    queryFn: () => listPredictions(job.id, query),
    placeholderData: keepPreviousData,
  });

  const runExport = async (format: "csv" | "json") => {
    setExporting(format);
    try {
      const file = await exportJob(job.id, format, query);
      saveBlob(file.blob, file.filename);
      if (file.truncated) toast.info("The export reached the server's row limit and was truncated. Narrow the filters to export the rest.");
      else toast.success("Export downloaded.");
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setExporting(null);
    }
  };

  return (
    <Card
      title="Predictions"
      subtitle="One row per analysed flow. Select a row for its explanation and review history."
      flush
      actions={
        <>
          <Button size="sm" icon="download" loading={exporting === "csv"} disabled={exporting !== null} onClick={() => void runExport("csv")}>
            CSV
          </Button>
          <Button size="sm" icon="download" loading={exporting === "json"} disabled={exporting !== null} onClick={() => void runExport("json")}>
            JSON
          </Button>
        </>
      }
    >
      <div className="filter-bar">
        <ChipGroup
          label="Risk band"
          options={RISK_BANDS.map((band) => ({ value: band, label: humanize(band) }))}
          selected={query.risk_band ?? []}
          onChange={(values) => search.update({ band: values })}
        />
        <SelectField
          label="Predicted label"
          placeholder="Any label"
          options={labels.map((label) => ({ value: label, label }))}
          value={search.get("label")}
          onChange={(event) => search.update({ label: event.target.value })}
        />
        <TextField
          label="Minimum risk"
          type="number"
          min={0}
          max={100}
          step={1}
          style={{ width: 110 }}
          value={minRisk}
          onChange={(event) => search.update({ min_risk: event.target.value })}
        />
        <div className="stack-sm">
          <Checkbox label="Alerts only" checked={query.is_alert === true} onChange={(event) => search.update({ alerts: event.target.checked })} />
          <Checkbox label="Anomalies only" checked={query.is_anomaly === true} onChange={(event) => search.update({ anomalies: event.target.checked })} />
        </div>
      </div>
      <DataTable<Prediction>
        caption="Predictions"
        rows={predictions.data?.items}
        loading={predictions.isFetching}
        error={predictions.error}
        onRetry={() => void predictions.refetch()}
        rowKey={(row) => row.id}
        sort={query.sort}
        onSortChange={(sort) => search.update({ sort })}
        onRowClick={(row) => navigate(`/predictions/${row.id}`)}
        rowLabel={(row) => `Open prediction for record ${row.record_index}`}
        emptyTitle="No predictions match these filters"
        columns={[
          { key: "record", header: "Record", sortKey: "record_index", align: "right", render: (row) => formatNumber(row.record_index) },
          { key: "label", header: "Prediction", render: (row) => <LabelBadge label={row.predicted_label} /> },
          {
            key: "truth",
            header: "Dataset label",
            render: (row) => (row.true_label ? <span className="small">{row.true_label}</span> : <span className="subtle">—</span>),
          },
          {
            key: "probability",
            header: "Probability",
            align: "right",
            render: (row) => (row.probability === null ? <span className="subtle">n/a</span> : formatScore(row.probability)),
          },
          { key: "classifier", header: "Classifier score", sortKey: "classifier_score", align: "right", render: (row) => formatScore(row.classifier_score) },
          {
            key: "anomaly",
            header: "Anomaly score",
            sortKey: "anomaly_score",
            align: "right",
            render: (row) => (
              <span>
                {formatScore(row.anomaly_score)}
                {row.is_anomaly ? <span title="Above the anomaly threshold"> ⚑</span> : null}
              </span>
            ),
          },
          { key: "risk", header: "Risk", sortKey: "risk_score", render: (row) => <RiskBadge band={row.risk_band} score={row.risk_score} /> },
          { key: "alert", header: "Alert", render: (row) => (row.is_alert ? "Yes" : "No") },
        ]}
      />
      {predictions.data ? (
        <Pagination
          total={predictions.data.total}
          limit={query.limit ?? 25}
          offset={query.offset ?? 0}
          onChange={(offset) => search.update({ offset }, { resetPage: false })}
          onLimitChange={(limit) => search.update({ limit })}
        />
      ) : null}
      <div style={{ padding: 16 }}>
        <ScoreSemantics />
      </div>
    </Card>
  );
}
