/** Human-readable rendering of ``datasets.validation_report`` (accepted or rejected uploads). */
import { Chart, countsToSeries } from "../../components/Chart";
import { KeyValueList } from "../../components/DataDisplay";
import { Callout } from "../../components/States";
import { formatNumber, formatPercent, humanize } from "../../utils/format";

type Report = Record<string, unknown> | null | undefined;

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function asCounts(value: unknown): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [key, item] of Object.entries(asRecord(value))) if (typeof item === "number") out[key] = item;
  return out;
}

function ListOrNone({ items, limit = 12 }: { items: string[]; limit?: number }) {
  if (items.length === 0) return <span className="muted">None</span>;
  const shown = items.slice(0, limit);
  return (
    <span className="break">
      {shown.join(", ")}
      {items.length > limit ? ` … (+${items.length - limit} more)` : ""}
    </span>
  );
}

export function ValidationReport({ report }: { report: Report }) {
  const data = asRecord(report);
  if (Object.keys(data).length === 0) return <p className="muted">No validation report is available.</p>;

  if (data.accepted === false) {
    const error = asRecord(data.error);
    const details = asRecord(error.details);
    return (
      <Callout tone="danger" title="The file was rejected">
        <p>{typeof error.message === "string" ? error.message : "The file did not pass validation."}</p>
        <RejectionDetails details={details} />
      </Callout>
    );
  }

  const columns = asRecord(data.columns);
  const detection = asRecord(data.schema_detection);
  const groundTruth = asRecord(data.ground_truth);
  const quality = asRecord(data.data_quality);
  const warnings = asStringList(data.warnings);
  const coverage = asCounts(detection.feature_coverage);
  const distribution = asCounts(groundTruth.label_distribution);

  return (
    <div className="stack">
      {warnings.length ? (
        <Callout tone="warning" title="Warnings">
          <ul>
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </Callout>
      ) : null}
      <KeyValueList
        items={[
          { label: "Schema", value: String(data.schema_version ?? "—") },
          {
            label: "Schema detection",
            value:
              detection.mode === "explicit"
                ? "Selected by the uploader"
                : `Automatic (feature coverage: ${Object.entries(coverage)
                    .map(([schema, fraction]) => `${schema} ${formatPercent(fraction)}`)
                    .join(", ")})`,
          },
          { label: "Encoding", value: String(data.encoding ?? "—") },
          { label: "Rows", value: formatNumber(typeof data.rows === "number" ? data.rows : null) },
          { label: "Columns", value: formatNumber(typeof columns.column_count === "number" ? columns.column_count : null) },
          { label: "Feature columns found", value: formatNumber(typeof columns.feature_columns_found === "number" ? columns.feature_columns_found : null) },
          { label: "Missing features", value: <ListOrNone items={asStringList(columns.missing_features)} /> },
          { label: "Unknown columns (ignored)", value: <ListOrNone items={asStringList(columns.unknown_columns)} /> },
          { label: "Identifier columns", value: <ListOrNone items={asStringList(columns.identifier_columns)} /> },
          { label: "Label columns", value: <ListOrNone items={asStringList(columns.label_columns)} /> },
          {
            label: "Ground truth",
            value: groundTruth.present
              ? groundTruth.usable
                ? "Present — used only to evaluate results, never as model input"
                : "Present but not usable for evaluation"
              : "Not present",
          },
        ]}
      />
      <DataQuality quality={quality} />
      {Object.keys(distribution).length ? (
        <div>
          <h3 style={{ marginBottom: 8 }}>Ground-truth label distribution</h3>
          <Chart title="Ground-truth label distribution" kind="hbar" height={240} series={[countsToSeries("Rows", distribution)]} />
        </div>
      ) : null}
    </div>
  );
}

function DataQuality({ quality }: { quality: Record<string, unknown> }) {
  const sections = Object.entries(quality)
    .map(([kind, value]) => [kind, asCounts(value)] as const)
    .filter(([, counts]) => Object.keys(counts).length > 0);
  if (sections.length === 0) return <p className="muted small">No data-quality issues were found in feature columns.</p>;
  return (
    <div className="stack-sm">
      <h3>Data quality (top affected columns)</h3>
      <KeyValueList
        items={sections.map(([kind, counts]) => ({
          label: humanize(kind),
          value: (
            <span className="break">
              {Object.entries(counts)
                .map(([column, count]) => `${column}: ${formatNumber(count)}`)
                .join(" · ")}
            </span>
          ),
        }))}
      />
      <p className="small subtle">Invalid numeric values are treated as missing and imputed by each model's preprocessing pipeline.</p>
    </div>
  );
}

function RejectionDetails({ details }: { details: Record<string, unknown> }) {
  const entries = Object.entries(details).filter(([key]) => key !== "dataset_id" && key !== "reason");
  if (entries.length === 0) return null;
  return (
    <ul>
      {entries.map(([key, value]) => (
        <li key={key}>
          <strong>{humanize(key)}:</strong>{" "}
          {typeof value === "object" && value !== null
            ? Object.entries(value as Record<string, unknown>)
                .slice(0, 20)
                .map(([k, v]) => `${k}: ${typeof v === "number" && v <= 1 && v >= 0 && key !== "rows" ? formatPercent(v) : String(v)}`)
                .join(", ")
            : String(value)}
        </li>
      ))}
    </ul>
  );
}
