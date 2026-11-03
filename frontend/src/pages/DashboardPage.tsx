import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { LabelBadge, RiskBadge, StatusBadge } from "../components/Badge";
import { LinkButton } from "../components/Button";
import { Card } from "../components/Card";
import { Chart, countsToSeries, RISK_BAND_COLORS, RISK_BAND_ORDER } from "../components/Chart";
import { DataTable } from "../components/DataTable";
import { SelectField } from "../components/FormFields";
import { KpiCard } from "../components/KpiCard";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, LoadingState } from "../components/States";
import { useAuth } from "../features/auth/AuthContext";
import { canAnalyze } from "../features/auth/roles";
import { useSearchState } from "../hooks/useSearchState";
import { listAlerts } from "../services/alerts";
import { listJobs } from "../services/analyses";
import { getSummary, getTrends } from "../services/metrics";
import { queryKeys } from "../services/queryKeys";
import type { Alert, AnalysisJob } from "../types/api";
import { formatDateTime, formatNumber, formatPercent, formatRisk, trendBucketLabel } from "../utils/format";
import { normalizeWindow, WINDOW_OPTIONS, windowRange } from "../utils/timeWindow";

export function DashboardPage() {
  const { user } = useAuth();
  const analyst = canAnalyze(user);
  const search = useSearchState();
  const period = normalizeWindow(search.get("window"));
  const bucket = period === "24h" ? "hour" : "day";

  const summary = useQuery({ queryKey: queryKeys.summary(period), queryFn: () => getSummary(windowRange(period)) });
  const trends = useQuery({ queryKey: queryKeys.trends(bucket, period), queryFn: () => getTrends(bucket, windowRange(period)) });

  return (
    <>
      <PageHeader
        title="Security overview"
        description="Organisation-wide results of completed analysis jobs. Figures are model outputs for analyst triage, not confirmed incidents."
        actions={
          <>
            <SelectField
              label="Period"
              options={WINDOW_OPTIONS}
              value={period}
              onChange={(event) => search.update({ window: event.target.value })}
            />
            {analyst ? (
              <LinkButton to="/datasets/upload" variant="primary" icon="upload">
                Upload dataset
              </LinkButton>
            ) : null}
          </>
        }
      />

      {summary.isPending ? (
        <LoadingState label="Loading metrics…" />
      ) : summary.isError ? (
        <Card>
          <ErrorState error={summary.error} onRetry={() => void summary.refetch()} />
        </Card>
      ) : (
        <div className="grid-kpi">
          <KpiCard label="Analysed records" value={formatNumber(summary.data.total_records)} hint={`${formatNumber(summary.data.completed_jobs)} completed jobs`} />
          <KpiCard
            label="Malicious predictions"
            value={formatNumber(summary.data.malicious_count)}
            hint={summary.data.total_records ? `${formatPercent(summary.data.malicious_count / summary.data.total_records)} of records` : undefined}
            tone={summary.data.malicious_count ? "danger" : "default"}
          />
          <KpiCard
            label="Open alerts"
            value={formatNumber(summary.data.open_alert_count)}
            hint={`${formatNumber(summary.data.alert_count)} alerts in total`}
            tone={summary.data.open_alert_count ? "warning" : "success"}
            to={analyst ? "/alerts?status=open" : undefined}
          />
          <KpiCard label="High & critical risk" value={formatNumber(summary.data.high_risk_count)} tone={summary.data.high_risk_count ? "danger" : "default"} />
          <KpiCard label="Anomalies" value={formatNumber(summary.data.anomaly_count)} hint="Unusual vs. benign baseline" />
          <KpiCard label="Needs review" value={formatNumber(summary.data.needs_review_count)} hint="Below model confidence threshold" />
          <KpiCard label="Approved models" value={formatNumber(summary.data.approved_models)} to="/models" />
          <KpiCard label="Active datasets" value={formatNumber(summary.data.active_datasets)} to={analyst ? "/datasets" : undefined} />
        </div>
      )}

      <div className="grid-2">
        <Card title="Detections over time" subtitle={`Per ${bucket}, from completed jobs`}>
          {trends.isPending ? (
            <LoadingState />
          ) : trends.isError ? (
            <ErrorState error={trends.error} onRetry={() => void trends.refetch()} />
          ) : (
            <Chart
              title="Detections over time"
              kind="line"
              timeBucket={bucket}
              series={[
                { name: "Records", x: trends.data.points.map((p) => trendBucketLabel(p.bucket, bucket)), y: trends.data.points.map((p) => p.records), colorVar: "--chart-1" },
                { name: "Malicious", x: trends.data.points.map((p) => trendBucketLabel(p.bucket, bucket)), y: trends.data.points.map((p) => p.malicious), colorVar: "--chart-2" },
                { name: "Alerts", x: trends.data.points.map((p) => trendBucketLabel(p.bucket, bucket)), y: trends.data.points.map((p) => p.alerts), colorVar: "--risk-critical" },
                { name: "Anomalies", x: trends.data.points.map((p) => trendBucketLabel(p.bucket, bucket)), y: trends.data.points.map((p) => p.anomalies), colorVar: "--chart-4" },
              ]}
            />
          )}
        </Card>
        <Card title="Risk bands" subtitle="Policy risk band of every analysed record">
          {summary.data ? (
            <Chart
              title="Risk band distribution"
              kind="donut"
              series={[countsToSeries("Records", summary.data.risk_band_distribution, RISK_BAND_ORDER)]}
              categoryColorVars={RISK_BAND_ORDER.filter((band) => band in summary.data.risk_band_distribution).map(
                (band) => RISK_BAND_COLORS[RISK_BAND_ORDER.indexOf(band)] as string,
              )}
            />
          ) : (
            <LoadingState />
          )}
        </Card>
      </div>

      <Card title="Predicted labels" subtitle="Top classes predicted across completed jobs">
        {summary.data ? <Chart title="Predicted label distribution" kind="hbar" series={[countsToSeries("Records", summary.data.label_distribution)]} /> : <LoadingState />}
      </Card>

      {analyst ? (
        <div className="grid-2">
          <RecentAlerts />
          <RecentJobs />
        </div>
      ) : null}
    </>
  );
}

function RecentAlerts() {
  const navigate = useNavigate();
  const query = { severity: ["critical", "high"], status: ["open", "investigating"], sort: "-created_at", limit: 6 };
  const alerts = useQuery({ queryKey: queryKeys.alerts(query), queryFn: () => listAlerts(query) });
  return (
    <Card title="Latest high-severity alerts" actions={<LinkButton to="/alerts" size="sm">View all</LinkButton>} flush>
      <DataTable<Alert>
        caption="Latest high-severity alerts"
        compact
        rows={alerts.data?.items}
        loading={alerts.isPending}
        error={alerts.error}
        onRetry={() => void alerts.refetch()}
        rowKey={(row) => row.id}
        onRowClick={(row) => navigate(`/alerts/${row.id}`)}
        rowLabel={(row) => `Open alert for record ${row.record_index}`}
        emptyTitle="No open high-severity alerts"
        columns={[
          { key: "risk", header: "Risk", render: (row) => <RiskBadge band={row.risk_band} score={row.risk_score} /> },
          { key: "label", header: "Prediction", render: (row) => <LabelBadge label={row.predicted_label} /> },
          { key: "dataset", header: "Dataset", render: (row) => <span className="break">{row.dataset_name}</span> },
          { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
        ]}
      />
    </Card>
  );
}

function RecentJobs() {
  const navigate = useNavigate();
  const query = { sort: "-created_at", limit: 6 };
  const jobs = useQuery({ queryKey: queryKeys.jobs(query), queryFn: () => listJobs(query) });
  return (
    <Card title="Recent analysis jobs" actions={<LinkButton to="/analyses" size="sm">View all</LinkButton>} flush>
      <DataTable<AnalysisJob>
        caption="Recent analysis jobs"
        compact
        rows={jobs.data?.items}
        loading={jobs.isPending}
        error={jobs.error}
        onRetry={() => void jobs.refetch()}
        rowKey={(row) => row.id}
        onRowClick={(row) => navigate(`/analyses/${row.id}`)}
        rowLabel={(row) => `Open results of analysis on ${row.dataset.name}`}
        emptyTitle="No analysis jobs yet"
        columns={[
          { key: "dataset", header: "Dataset", render: (row) => <span className="break">{row.dataset.name}</span> },
          { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
          {
            key: "alerts",
            header: "Alerts",
            align: "right",
            render: (row) => formatNumber(typeof row.summary?.alert_count === "number" ? row.summary.alert_count : null),
          },
          {
            key: "risk",
            header: "Max risk",
            align: "right",
            render: (row) => formatRisk(((row.summary?.risk_score ?? null) as { max?: number } | null)?.max ?? null),
          },
          { key: "created", header: "Submitted", render: (row) => <span className="nowrap">{formatDateTime(row.created_at)}</span> },
        ]}
      />
    </Card>
  );
}
