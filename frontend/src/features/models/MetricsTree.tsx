/**
 * Generic, read-only rendering of metric dictionaries recorded by the training notebooks (model manifests and
 * experiment summaries). Values are displayed exactly as recorded; nothing is computed or estimated here.
 */
import { ConfusionMatrix } from "../../components/ConfusionMatrix";
import { JsonView, KeyValueList } from "../../components/DataDisplay";
import { DataTable } from "../../components/DataTable";
import { formatNumber, humanize } from "../../utils/format";

type Dict = Record<string, unknown>;

function isDict(value: unknown): value is Dict {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function formatMetricValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return Number.isInteger(value) ? formatNumber(value) : formatNumber(value, Math.abs(value) >= 100 ? 1 : 4);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function isConfusion(value: unknown): boolean {
  return isDict(value) && Array.isArray(value.labels) && Array.isArray(value.matrix);
}

/** ``{class: {precision, recall, f1, support}}`` */
function isPerClass(value: unknown): value is Record<string, Dict> {
  if (!isDict(value)) return false;
  const items = Object.values(value);
  return items.length > 0 && items.every((item) => isDict(item) && ("f1" in item || "recall" in item || "precision" in item));
}

function PerClassTable({ value, caption }: { value: Record<string, Dict>; caption: string }) {
  const rows = Object.entries(value).map(([label, metrics]) => ({ label, ...metrics }));
  const keys = Array.from(new Set(rows.flatMap((row) => Object.keys(row).filter((key) => key !== "label"))));
  return (
    <DataTable
      caption={caption}
      compact
      rowKey={(row) => row.label}
      rows={rows}
      columns={[
        { key: "label", header: "Class", render: (row) => row.label },
        ...keys.map((key) => ({
          key,
          header: humanize(key),
          align: "right" as const,
          render: (row: Dict) => formatMetricValue(row[key]),
        })),
      ]}
    />
  );
}

export function MetricsTree({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (!isDict(value)) return <JsonView value={value} />;
  const entries = Object.entries(value);
  const scalars = entries.filter(([, item]) => item === null || ["number", "string", "boolean"].includes(typeof item));
  const nested = entries.filter(([, item]) => item !== null && typeof item === "object");
  return (
    <div className="stack-sm">
      {scalars.length ? <KeyValueList items={scalars.map(([key, item]) => ({ label: humanize(key), value: formatMetricValue(item) }))} /> : null}
      {nested.map(([key, item]) => {
        if (isConfusion(item)) return <ConfusionMatrix key={key} matrix={item} title={humanize(key)} />;
        if (isPerClass(item))
          return (
            <div key={key} className="stack-sm">
              <h3>{humanize(key)}</h3>
              <PerClassTable value={item} caption={humanize(key)} />
            </div>
          );
        if (Array.isArray(item) || depth >= 3) {
          return (
            <details key={key}>
              <summary>{humanize(key)}</summary>
              <JsonView value={item} />
            </details>
          );
        }
        return (
          <details key={key} open={depth === 0} style={{ paddingLeft: depth ? 12 : 0 }}>
            <summary style={{ cursor: "pointer", fontWeight: 600, margin: "6px 0" }}>{humanize(key)}</summary>
            <MetricsTree value={item} depth={depth + 1} />
          </details>
        );
      })}
    </div>
  );
}
