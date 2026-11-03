/** Renders ``analysis_jobs.summary``: counts, risk statistics, data quality and (when labels exist) evaluation. */
import { Chart, countsToSeries, RISK_BAND_COLORS, RISK_BAND_ORDER } from "../../components/Chart";
import { Card } from "../../components/Card";
import { KeyValueList } from "../../components/DataDisplay";
import { DataTable } from "../../components/DataTable";
import { KpiCard } from "../../components/KpiCard";
import { Callout } from "../../components/States";
import { ConfusionMatrix } from "../../components/ConfusionMatrix";
import { formatDuration, formatNumber, formatPercent, formatRisk, formatScore, humanize } from "../../utils/format";

type Dict = Record<string, unknown>;

function dict(value: unknown): Dict {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Dict) : {};
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function counts(value: unknown): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [key, item] of Object.entries(dict(value))) if (typeof item === "number") out[key] = item;
  return out;
}

export function JobSummary({ summary }: { summary: Dict }) {
  const processed = num(dict(summary.rows).processed);
  const risk = dict(summary.risk_score);
  const timing = dict(summary.timing);
  const quality = counts(summary.data_quality);
  const bands = counts(summary.risk_band_counts);
  const evaluation = summary.evaluation ? dict(summary.evaluation) : null;
  const ratio = (value: number | null) => (processed && value !== null ? formatPercent(value / processed) : undefined);

  return (
    <div className="stack">
      <div className="grid-kpi">
        <KpiCard label="Processed records" value={formatNumber(processed)} hint={timing.rows_per_second ? `${formatNumber(num(timing.rows_per_second))} records/s` : undefined} />
        <KpiCard label="Alerts" value={formatNumber(num(summary.alert_count))} hint={ratio(num(summary.alert_count))} tone={num(summary.alert_count) ? "danger" : "success"} />
        <KpiCard label="Malicious predictions" value={formatNumber(num(summary.malicious_count))} hint={ratio(num(summary.malicious_count))} />
        <KpiCard label="Anomalies" value={summary.anomaly_count === null ? "n/a" : formatNumber(num(summary.anomaly_count))} hint={ratio(num(summary.anomaly_count))} />
        <KpiCard label="Needs review" value={formatNumber(num(summary.needs_review_count))} hint="Below confidence threshold" />
        <KpiCard label="Risk score (p95 / max)" value={`${formatRisk(num(risk.p95))} / ${formatRisk(num(risk.max))}`} hint={`mean ${formatRisk(num(risk.mean))}`} />
      </div>
      <div className="grid-2">
        <Card title="Predicted labels">
          <Chart title="Predicted labels in this job" kind="hbar" height={260} series={[countsToSeries("Records", counts(summary.label_counts))]} />
        </Card>
        <Card title="Risk bands">
          <Chart
            title="Risk bands in this job"
            kind="donut"
            height={260}
            series={[countsToSeries("Records", bands, RISK_BAND_ORDER)]}
            categoryColorVars={RISK_BAND_ORDER.filter((band) => band in bands).map((band) => RISK_BAND_COLORS[RISK_BAND_ORDER.indexOf(band)] as string)}
          />
        </Card>
      </div>
      <div className="grid-2">
        <Card title="Run details">
          <KeyValueList
            items={[
              { label: "Duration", value: formatDuration(num(timing.duration_seconds)) },
              { label: "Explained records", value: formatNumber(num(summary.explained_rows)) },
              { label: "Risk policy", value: String(summary.risk_policy_version ?? "—") },
              { label: "Model manifest", value: <code className="break">{String(dict(summary.model).manifest_sha256 ?? "—")}</code> },
            ]}
          />
        </Card>
        <Card title="Input data quality" subtitle="Invalid values were treated as missing and imputed by the model's preprocessing.">
          <KeyValueList items={Object.entries(quality).map(([key, value]) => ({ label: humanize(key), value: formatNumber(value) }))} />
        </Card>
      </div>
      {evaluation ? <EvaluationSection evaluation={evaluation} /> : null}
    </div>
  );
}

function EvaluationSection({ evaluation }: { evaluation: Dict }) {
  const classification = evaluation.classification ? dict(evaluation.classification) : null;
  const anomaly = evaluation.anomaly_detection ? dict(evaluation.anomaly_detection) : null;
  const perClass: (Dict & { label: string })[] = Object.entries(dict(classification?.per_class)).map(([label, value]) => ({ ...dict(value), label }));
  const binary = classification ? dict(classification.binary) : null;
  return (
    <Card title="Evaluation against dataset labels" subtitle={String(evaluation.source ?? "")}>
      <div className="stack">
        <Callout tone="info">
          These metrics compare predictions with the labels contained in this dataset ({formatNumber(num(evaluation.labeled_rows))} labelled rows). They describe
          this dataset only. {String(evaluation.note ?? "")}
        </Callout>
        {classification ? (
          <>
            <div className="grid-kpi">
              <KpiCard label="Accuracy" value={formatPercent(num(classification.accuracy))} />
              <KpiCard label="Macro F1" value={formatScore(num(dict(classification.macro).f1))} />
              <KpiCard label="Weighted F1" value={formatScore(num(dict(classification.weighted).f1))} />
              <KpiCard label="False-alarm rate" value={formatPercent(num(classification.false_alarm_rate), 2)} hint="Benign flows predicted as attacks" />
              {binary ? <KpiCard label="Attack recall (binary)" value={formatPercent(num(binary.recall))} /> : null}
            </div>
            <DataTable
              caption="Per-class metrics"
              compact
              rowKey={(row) => row.label}
              rows={perClass}
              columns={[
                { key: "label", header: "Class", render: (row) => row.label },
                { key: "precision", header: "Precision", align: "right", render: (row) => formatScore(num(row.precision)) },
                { key: "recall", header: "Recall", align: "right", render: (row) => formatScore(num(row.recall)) },
                { key: "f1", header: "F1", align: "right", render: (row) => formatScore(num(row.f1)) },
                { key: "support", header: "Support", align: "right", render: (row) => formatNumber(num(row.support)) },
              ]}
            />
            <ConfusionMatrix matrix={classification.confusion_matrix} />
          </>
        ) : null}
        {anomaly ? (
          <div className="stack-sm">
            <h3>Anomaly detector vs. labels (attack = positive)</h3>
            <KeyValueList
              items={[
                { label: "Precision", value: formatScore(num(anomaly.precision)) },
                { label: "Recall", value: formatScore(num(anomaly.recall)) },
                { label: "F1", value: formatScore(num(anomaly.f1)) },
                { label: "False-positive rate", value: formatPercent(num(anomaly.false_positive_rate), 2) },
                { label: "TP / FP / TN / FN", value: [anomaly.tp, anomaly.fp, anomaly.tn, anomaly.fn].map((v) => formatNumber(num(v))).join(" / ") },
              ]}
            />
          </div>
        ) : null}
      </div>
    </Card>
  );
}
