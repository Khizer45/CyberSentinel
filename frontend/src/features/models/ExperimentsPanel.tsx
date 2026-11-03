/**
 * Read-only viewer for experiment records written by the training notebooks (``model_artifacts/experiments``).
 * Every number shown here was measured by a notebook run; the UI never generates or estimates results.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "../../components/Badge";
import { Card } from "../../components/Card";
import { Chart, type ChartKind, type ChartSeries } from "../../components/Chart";
import { JsonView, KeyValueList } from "../../components/DataDisplay";
import { DataTable } from "../../components/DataTable";
import { Callout, ErrorState, LoadingState } from "../../components/States";
import { getExperiment, listExperiments } from "../../services/models";
import { queryKeys } from "../../services/queryKeys";
import type { ExperimentRecord, ExperimentSummary } from "../../types/api";
import { formatDateTime, formatNumber, humanize } from "../../utils/format";
import { formatMetricValue, MetricsTree } from "./MetricsTree";

type Row = Record<string, string | number | boolean | null>;

interface ChartSpec {
  x: string[];
  y: string[];
  group?: string;
  kind: ChartKind;
}

const CHART_SPECS: Record<string, ChartSpec> = {
  supervised_comparison: { x: ["model"], y: ["macro_f1"], group: "task", kind: "bar" },
  anomaly_detection: { x: ["variant", "name", "model"], y: ["roc_auc", "pr_auc"], kind: "bar" },
  unknown_attack_holdout: { x: ["held_out_category"], y: ["classified_as_other_attack", "flagged_anomalous", "missed_by_both"], kind: "bar" },
  semi_supervised_label_budget: { x: ["label_budget"], y: ["macro_f1"], group: "method", kind: "line" },
  risk_policy_evaluation: { x: ["classifier_weight"], y: ["attack_recall_at_alert", "alert_precision", "alert_f1"], kind: "line" },
};

/** Build chart series from recorded rows (mean over repeated x values, e.g. several random seeds). */
export function experimentSeries(record: Pick<ExperimentRecord, "experiment_type" | "rows">): { kind: ChartKind; series: ChartSeries[]; x: string } | null {
  const spec = CHART_SPECS[record.experiment_type];
  const rows = (record.rows ?? []) as Row[];
  if (!spec || rows.length === 0) return null;
  const x = spec.x.find((key) => rows.some((row) => row[key] !== undefined && row[key] !== null));
  if (!x) return null;
  const metrics = spec.y.filter((key) => rows.some((row) => typeof row[key] === "number"));
  if (metrics.length === 0) return null;
  const groups = spec.group && rows.some((row) => row[spec.group as string] !== undefined) ? Array.from(new Set(rows.map((row) => String(row[spec.group as string])))) : [null];
  const numericX = rows.every((row) => typeof row[x] === "number");
  const xs = Array.from(new Set(rows.map((row) => row[x]))).filter((value) => value !== null && value !== undefined);
  if (numericX) xs.sort((a, b) => Number(a) - Number(b));
  const series: ChartSeries[] = [];
  for (const group of groups) {
    for (const metric of metrics) {
      const ys = xs.map((xValue) => {
        const values = rows
          .filter((row) => row[x] === xValue && (group === null || String(row[spec.group as string]) === group))
          .map((row) => row[metric])
          .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
        return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : Number.NaN;
      });
      const name = group === null ? humanize(metric) : metrics.length > 1 ? `${group} · ${humanize(metric)}` : group;
      series.push({ name, x: xs.map((value) => (typeof value === "number" ? value : String(value))), y: ys });
    }
  }
  return { kind: spec.kind, series, x };
}

export function ExperimentsPanel() {
  const experiments = useQuery({ queryKey: queryKeys.experiments, queryFn: () => listExperiments() });
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (experiments.isPending) return <LoadingState label="Loading experiments…" />;
  if (experiments.isError) return <ErrorState error={experiments.error} onRetry={() => void experiments.refetch()} />;

  return (
    <div className="stack">
      <Callout tone="info">
        Experiment records are written by the training notebooks to <code>model_artifacts/experiments/</code>. They are shown exactly as recorded; if
        none are listed, the notebooks have not been run on this installation yet.
      </Callout>
      <Card title="Experiment records" flush>
        <DataTable<ExperimentSummary>
          caption="Experiment records"
          rows={experiments.data}
          rowKey={(row) => row.experiment_id}
          onRowClick={(row) => setSelectedId(row.experiment_id)}
          rowLabel={(row) => `Open experiment ${row.title}`}
          emptyTitle="No experiment records yet"
          emptyMessage="Run the notebooks in notebooks/ to produce comparison results."
          columns={[
            { key: "title", header: "Experiment", render: (row) => <strong className="break">{row.title}</strong> },
            { key: "type", header: "Type", render: (row) => <Badge tone="info">{humanize(row.experiment_type)}</Badge> },
            { key: "family", header: "Dataset", render: (row) => `${row.dataset_family} · ${row.schema_version}` },
            { key: "rows", header: "Rows", align: "right", render: (row) => formatNumber(row.row_count) },
            { key: "created", header: "Recorded", render: (row) => <span className="nowrap">{formatDateTime(row.created_at)}</span> },
          ]}
        />
      </Card>
      {selectedId ? <ExperimentDetail id={selectedId} /> : null}
    </div>
  );
}

function ExperimentDetail({ id }: { id: string }) {
  const experiment = useQuery({ queryKey: queryKeys.experiment(id), queryFn: () => getExperiment(id) });
  if (experiment.isPending) return <LoadingState label="Loading experiment…" />;
  if (experiment.isError) return <ErrorState error={experiment.error} onRetry={() => void experiment.refetch()} />;
  const record = experiment.data;
  const rows = (record.rows ?? []) as Row[];
  const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row)))).slice(0, 16);
  const chart = experimentSeries(record);
  return (
    <Card title={record.title} subtitle={`${humanize(record.experiment_type)} · ${record.dataset_family} · recorded ${formatDateTime(record.created_at)}`}>
      <div className="stack">
        {record.notes?.length ? (
          <Callout tone="info" title="Notes">
            <ul>
              {record.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </Callout>
        ) : null}
        {chart ? <Chart title={record.title} kind={chart.kind} series={chart.series} xTitle={humanize(chart.x)} height={300} /> : null}
        {record.columns && Object.keys(record.columns).length ? (
          <KeyValueList items={Object.entries(record.columns).map(([key, description]) => ({ label: humanize(key), value: description }))} />
        ) : null}
        <DataTable<Row>
          caption={`${record.title} results`}
          compact
          rows={rows}
          rowKey={(row) => JSON.stringify(row)}
          emptyTitle="No rows recorded"
          columns={columns.map((key) => ({
            key,
            header: humanize(key),
            align: rows.some((row) => typeof row[key] === "number") ? ("right" as const) : undefined,
            render: (row: Row) => formatMetricValue(row[key]),
          }))}
        />
        {record.summary && Object.keys(record.summary).length ? (
          <div className="stack-sm">
            <h3>Summary</h3>
            <MetricsTree value={record.summary} />
          </div>
        ) : null}
        <details>
          <summary>Configuration and runtime</summary>
          <JsonView value={{ config: record.config, runtime: record.runtime, schema_version: record.schema_version }} />
        </details>
      </div>
    </Card>
  );
}
