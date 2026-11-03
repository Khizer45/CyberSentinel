import type { AnalysisMode } from "../../types/api";

export const MODE_LABELS: Record<AnalysisMode, string> = {
  combined: "Combined (classifier + anomaly detector)",
  classification: "Classification only",
  anomaly: "Anomaly detection only",
};

export const MODE_HINTS: Record<AnalysisMode, string> = {
  combined: "Known-attack classification plus unusual-traffic detection; risk uses both components.",
  classification: "Predicts benign or attack class using the supervised classifier.",
  anomaly: "Flags flows that deviate from benign training traffic; no class labels are predicted.",
};

export function preferredMode(modes: string[]): AnalysisMode {
  if (modes.includes("combined")) return "combined";
  if (modes.includes("classification")) return "classification";
  return "anomaly";
}
