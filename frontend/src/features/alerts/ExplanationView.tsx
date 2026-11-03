/**
 * Explanation of a single prediction: feature attributions (TreeSHAP for XGBoost, tree-path attribution for
 * random forests, or a baseline-deviation heuristic), reason codes, class scores, anomaly details and the
 * policy risk breakdown. Attributions describe the model's behaviour, not causality.
 */
import { Badge } from "../../components/Badge";
import { KeyValueList } from "../../components/DataDisplay";
import { Callout } from "../../components/States";
import type { Explanation } from "../../types/api";
import { formatNumber, formatRisk, formatScore, humanize } from "../../utils/format";

/** Keys are the backend's ``ExplanationMethod`` values (app/ml/constants.py). */
export const METHOD_LABELS: Record<string, string> = {
  xgboost_tree_shap: "TreeSHAP (exact, XGBoost)",
  tree_path_attribution: "Tree-path attribution (Saabas)",
  baseline_deviation: "Baseline-deviation heuristic",
};

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "missing";
  if (typeof value === "number") return Number.isInteger(value) ? formatNumber(value) : formatNumber(value, 4);
  return String(value);
}

export function ExplanationView({ explanation }: { explanation: Explanation }) {
  const features = explanation.top_features ?? [];
  const max = Math.max(...features.map((item) => Math.abs(item.contribution)), 1e-12);
  const heuristic = explanation.method_family === "heuristic";
  const risk = (explanation.risk ?? null) as Record<string, unknown> | null;

  return (
    <div className="stack">
      <div className="row">
        <Badge tone="primary">{METHOD_LABELS[explanation.method] ?? humanize(explanation.method)}</Badge>
        <Badge>{heuristic ? "Heuristic" : "Model attribution"}</Badge>
        <Badge>Units: {humanize(explanation.units)}</Badge>
        <span className="small muted">
          Explaining: <strong>{explanation.target_label}</strong>
        </span>
      </div>

      {explanation.fallback_reason ? <Callout tone="warning">{explanation.fallback_reason}</Callout> : null}

      {explanation.reason_codes?.length ? (
        <div className="stack-sm">
          <h3>Why this result</h3>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {explanation.reason_codes.map((reason, index) => (
              <li key={`${reason.code}-${index}`}>{reason.text}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {features.length ? (
        <div className="stack-sm">
          <h3>{heuristic ? "Largest deviations from the benign baseline" : "Top contributing features"}</h3>
          <div className="stack-sm" role="list">
            {features.map((item) => {
              const width = (Math.abs(item.contribution) / max) * 50;
              const positive = item.contribution > 0;
              return (
                <div key={item.feature} className="contrib-row" role="listitem">
                  <span className="break" title={item.feature}>
                    <strong>{item.feature}</strong>
                    <br />
                    <span className="small subtle">
                      value {formatValue(item.value)}
                      {item.baseline !== undefined && item.baseline !== null ? ` · baseline ${formatValue(item.baseline)}` : ""}
                    </span>
                  </span>
                  <span className="contrib-track" aria-hidden="true">
                    <span
                      className={`contrib-fill ${positive ? "up" : "down"}`}
                      style={positive ? { left: "50%", width: `${width}%` } : { right: "50%", width: `${width}%` }}
                    />
                  </span>
                  <span className="mono small text-right" title={humanize(item.direction)}>
                    {item.contribution > 0 ? "+" : ""}
                    {formatNumber(item.contribution, 4)}
                  </span>
                </div>
              );
            })}
          </div>
          <p className="small subtle">
            {heuristic
              ? "Bars show how far each value is from the benign median (robust z-score); right = above baseline."
              : `Bars right of centre push the model towards “${explanation.target_label}”; bars left of centre push away from it.`}
          </p>
        </div>
      ) : (
        <p className="muted">No feature attributions are available for this prediction.</p>
      )}

      <div className="grid-2">
        {explanation.class_scores?.length ? (
          <div className="stack-sm">
            <h3>Top class scores {explanation.scores_calibrated ? "(calibrated probabilities)" : "(uncalibrated)"}</h3>
            <KeyValueList items={explanation.class_scores.map((item) => ({ label: item.label, value: formatScore(item.score) }))} />
          </div>
        ) : null}
        {explanation.anomaly ? (
          <div className="stack-sm">
            <h3>Anomaly detector</h3>
            <KeyValueList
              items={[
                { label: "Anomaly score", value: formatScore(explanation.anomaly.score, 4) },
                { label: "Threshold", value: formatScore(explanation.anomaly.threshold, 4) },
                { label: "Flagged", value: explanation.anomaly.is_anomaly ? "Yes — above threshold" : "No" },
                { label: "Direction", value: humanize(explanation.anomaly.score_direction) },
              ]}
            />
          </div>
        ) : null}
      </div>

      {risk ? (
        <div className="stack-sm">
          <h3>Risk score breakdown</h3>
          <KeyValueList
            items={[
              { label: "Policy version", value: String(risk.policy_version ?? "—") },
              { label: "Classifier component", value: formatScore(risk.classifier_component as number | null) },
              { label: "Anomaly component", value: formatScore(risk.anomaly_component as number | null) },
              {
                label: "Weights",
                value: (() => {
                  const weights = (risk.weights ?? {}) as Record<string, number>;
                  return `classifier ${weights.classifier ?? "—"} · anomaly ${weights.anomaly ?? "—"}`;
                })(),
              },
              { label: "Floor applied", value: risk.floor_applied ? humanize(String(risk.floor_applied)) : "None" },
              { label: "Risk score", value: `${formatRisk(risk.risk_score as number | null)} (${humanize(String(risk.risk_band ?? ""))})` },
            ]}
          />
        </div>
      ) : null}

      <p className="small subtle">{explanation.disclaimer}</p>
    </div>
  );
}
