import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { StatusBadge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { Chart, countsToSeries, RISK_BAND_COLORS, RISK_BAND_ORDER } from "../components/Chart";
import { KeyValueList } from "../components/DataDisplay";
import { DataTable } from "../components/DataTable";
import { SelectField } from "../components/FormFields";
import { KpiCard } from "../components/KpiCard";
import { PageHeader } from "../components/PageHeader";
import { Callout, ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/Toast";
import { formatMetricValue } from "../features/models/MetricsTree";
import { useSearchState } from "../hooks/useSearchState";
import { downloadSummaryReport, getSummaryReport, getTrends } from "../services/metrics";
import { listModelMetrics } from "../services/models";
import { queryKeys } from "../services/queryKeys";
import type { ModelMetrics } from "../types/api";
import { saveBlob } from "../utils/download";
import { errorMessage } from "../utils/errors";
import { formatDateTime, formatNumber, humanize, trendBucketLabel } from "../utils/format";
import { normalizeWindow, WINDOW_OPTIONS, windowRange } from "../utils/timeWindow";

/**
 * Pick a recorded test-split metric. The registry stores the bundle manifest's metrics under ``measured``
 * (``measured.test.macro_f1`` for notebook-trained bundles); nothing is computed here.
 */
export function testMetric(metrics: Record<string, unknown> | null, key: string): unknown {
  const measured = metrics?.measured && typeof metrics.measured === "object" ? (metrics.measured as Record<string, unknown>) : metrics;
  const test = measured?.test;
  if (test && typeof test === "object" && key in (test as Record<string, unknown>)) return (test as Record<string, unknown>)[key];
  return undefined;
}

export function AnalyticsPage() {
  const toast = useToast();
  const navigate = useNavigate();
  const search = useSearchState();
  const period = normalizeWindow(search.get("window"));
  const bucket = search.get("bucket") === "hour" ? "hour" : "day";
  const [downloading, setDownloading] = useState<"csv" | "json" | null>(null);

  const report = useQuery({ queryKey: queryKeys.report(period), queryFn: () => getSummaryReport(windowRange(period)) });
  const trends = useQuery({ queryKey: queryKeys.trends(bucket, period), queryFn: () => getTrends(bucket, windowRange(period)) });
  const modelMetrics = useQuery({ queryKey: queryKeys.modelMetrics, queryFn: listModelMetrics });

  const download = async (format: "csv" | "json") => {
    setDownloading(format);
    try {
      const file = await downloadSummaryReport(format, windowRange(period));
      saveBlob(file.blob, file.filename);
      toast.success("Report downloaded.");
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setDownloading(null);
    }
  };

  const totals = report.data?.totals ?? {};
  return (
    <>
      <PageHeader
        title="Analytics & reports"
        description="Aggregated results across completed analyses, alert handling and model versions. Downloads contain aggregates only."
        actions={
          <>
            <SelectField label="Period" options={WINDOW_OPTIONS} value={period} onChange={(event) => search.update({ window: event.target.value })} />
            <Button icon="download" loading={downloading === "csv"} disabled={downloading !== null} onClick={() => void download("csv")}>
              Report CSV
            </Button>
            <Button icon="download" loading={downloading === "json"} disabled={downloading !== null} onClick={() => void download("json")}>
              Report JSON
            </Button>
          </>
        }
      />

      {report.isPending ? (
        <LoadingState label="Building report…" />
      ) : report.isError ? (
        <Card>
          <ErrorState error={report.error} onRetry={() => void report.refetch()} />
        </Card>
      ) : (
        <>
          <div className="grid-kpi">
            {Object.entries(totals).map(([key, value]) => (
              <KpiCard key={key} label={humanize(key)} value={formatNumber(value)} />
            ))}
          </div>
          <div className="grid-2">
            <Card title="Alert handling" subtitle="Current status of alerts and the latest analyst disposition">
              <div className="grid-2">
                <Chart title="Alerts by status" kind="donut" height={240} series={[countsToSeries("Alerts", report.data.alerts_by_status, ["open", "investigating", "closed"])]} categoryColorVars={["--danger", "--warning", "--success"]} />
                <Chart title="Alerts by latest disposition" kind="hbar" height={240} series={[countsToSeries("Alerts", report.data.alerts_by_disposition)]} />
              </div>
            </Card>
            <Card title="Risk bands">
              <Chart
                title="Risk band distribution"
                kind="bar"
                height={260}
                series={[countsToSeries("Records", report.data.risk_band_distribution, RISK_BAND_ORDER)]}
                categoryColorVars={RISK_BAND_ORDER.filter((band) => band in report.data.risk_band_distribution).map(
                  (band) => RISK_BAND_COLORS[RISK_BAND_ORDER.indexOf(band)] as string,
                )}
              />
            </Card>
          </div>
          <div className="grid-2">
            <Card title="Predicted labels">
              <Chart title="Predicted labels" kind="hbar" height={300} series={[countsToSeries("Records", report.data.label_distribution)]} />
            </Card>
            <Card title="Analysis jobs">
              <KeyValueList items={Object.entries(report.data.jobs).map(([status, count]) => ({ label: humanize(status), value: formatNumber(count) }))} />
              <p className="small subtle" style={{ marginTop: 12 }}>
                Report generated {formatDateTime(report.data.generated_at)} for {report.data.generated_by}.
              </p>
            </Card>
          </div>
          {report.data.notes.length ? (
            <Callout tone="info" title="About these figures">
              <ul>
                {report.data.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </Callout>
          ) : null}
        </>
      )}

      <Card
        title="Trend"
        actions={
          <SelectField
            label="Granularity"
            options={[
              { value: "day", label: "Daily" },
              { value: "hour", label: "Hourly" },
            ]}
            value={bucket}
            onChange={(event) => search.update({ bucket: event.target.value === "day" ? null : event.target.value })}
          />
        }
      >
        {trends.isPending ? (
          <LoadingState />
        ) : trends.isError ? (
          <ErrorState error={trends.error} onRetry={() => void trends.refetch()} />
        ) : (
          <Chart
            title="Analysed records, malicious predictions and alerts over time"
            kind="stacked"
            timeBucket={bucket}
            series={[
              { name: "Benign / other", x: trends.data.points.map((p) => trendBucketLabel(p.bucket, bucket)), y: trends.data.points.map((p) => Math.max(0, p.records - p.malicious)), colorVar: "--chart-3" },
              { name: "Malicious", x: trends.data.points.map((p) => trendBucketLabel(p.bucket, bucket)), y: trends.data.points.map((p) => p.malicious), colorVar: "--chart-2" },
            ]}
            yTitle="Records"
          />
        )}
      </Card>

      <Card title="Model versions" subtitle="Test-split metrics recorded in each bundle manifest by the training notebooks (not measured by this server)." flush>
        <DataTable<ModelMetrics>
          caption="Model version metrics"
          rows={modelMetrics.data}
          loading={modelMetrics.isPending}
          error={modelMetrics.error}
          onRetry={() => void modelMetrics.refetch()}
          rowKey={(row) => row.model_version_id}
          onRowClick={(row) => navigate(`/models?model=${row.model_version_id}`)}
          rowLabel={(row) => `Open ${row.model_name} ${row.version}`}
          emptyTitle="No model versions"
          columns={[
            {
              key: "model",
              header: "Model",
              render: (row) => (
                <span className="break">
                  {row.model_name} <span className="subtle">{row.version}</span>
                </span>
              ),
            },
            { key: "family", header: "Dataset", render: (row) => row.dataset_family },
            { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
            { key: "f1", header: "Test macro-F1", align: "right", render: (row) => formatMetricValue(testMetric(row.metrics, "macro_f1")) },
            { key: "far", header: "Test false-alarm rate", align: "right", render: (row) => formatMetricValue(testMetric(row.metrics, "false_alarm_rate")) },
            { key: "acc", header: "Test accuracy", align: "right", render: (row) => formatMetricValue(testMetric(row.metrics, "accuracy")) },
          ]}
        />
      </Card>
    </>
  );
}
