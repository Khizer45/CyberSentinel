import { formatNumber } from "../utils/format";

interface MatrixShape {
  labels?: unknown;
  matrix?: unknown;
}

/** Confusion matrix (rows = true label, columns = predicted). Diagonal cells are tinted green, errors red. */
export function ConfusionMatrix({ matrix, title = "Confusion matrix (rows = true label, columns = predicted)" }: { matrix: unknown; title?: string }) {
  const shape = (matrix && typeof matrix === "object" ? matrix : {}) as MatrixShape;
  const labels = Array.isArray(shape.labels) ? shape.labels.map(String) : [];
  const rows = Array.isArray(shape.matrix) ? (shape.matrix as unknown[]).filter(Array.isArray).map((row) => (row as unknown[]).map(Number)) : [];
  if (!labels.length || rows.length !== labels.length || labels.length > 25) return null;
  const max = Math.max(1, ...rows.flat().filter(Number.isFinite));
  return (
    <div className="stack-sm">
      <h3>{title}</h3>
      <div className="table-wrap">
        <table className="table table-compact">
          <caption className="sr-only">{title}</caption>
          <thead>
            <tr>
              <th scope="col">True \ Predicted</th>
              {labels.map((label) => (
                <th key={label} scope="col" className="num">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={labels[i] ?? i}>
                <th scope="row">{labels[i]}</th>
                {row.map((value, j) => (
                  <td
                    key={j}
                    className="num"
                    style={{
                      background: value
                        ? `color-mix(in srgb, var(--${i === j ? "success" : "danger"}) ${Math.round((value / max) * 35) + 5}%, transparent)`
                        : undefined,
                    }}
                  >
                    {formatNumber(value)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
