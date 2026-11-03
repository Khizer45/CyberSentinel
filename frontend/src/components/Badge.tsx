import type { ReactNode } from "react";
import { cx } from "../utils/cx";
import { formatRisk, humanize } from "../utils/format";

export type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info" | "primary";

export function Badge({ tone = "neutral", dot = false, children, title }: { tone?: BadgeTone; dot?: boolean; children: ReactNode; title?: string }) {
  return (
    <span className={cx("badge", tone !== "neutral" && `badge-${tone}`, dot && "badge-dot")} title={title}>
      {children}
    </span>
  );
}

const STATUS_TONES: Record<string, BadgeTone> = {
  // analysis jobs
  queued: "neutral",
  validating: "info",
  running: "info",
  completed: "success",
  failed: "danger",
  cancelled: "neutral",
  // datasets
  pending: "neutral",
  validated: "success",
  rejected: "danger",
  deleted: "neutral",
  // models
  draft: "neutral",
  approved: "success",
  retired: "neutral",
  revoked: "danger",
  // alerts
  open: "danger",
  investigating: "warning",
  closed: "success",
  // audit outcomes
  success: "success",
  failure: "danger",
  denied: "warning",
};

export function StatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <Badge>Unknown</Badge>;
  return (
    <Badge tone={STATUS_TONES[status] ?? "neutral"} dot>
      {humanize(status)}
    </Badge>
  );
}

const BANDS = new Set(["low", "medium", "high", "critical"]);

/** Policy risk band (and optionally the 0–100 policy score). Not a probability. */
export function RiskBadge({ band, score }: { band: string | null | undefined; score?: number | null }) {
  if (!band || !BANDS.has(band)) return <Badge>Not scored</Badge>;
  return (
    <span className={`badge badge-risk-${band}`} title="Policy risk band (versioned risk policy, not a probability)">
      {humanize(band)}
      {score !== undefined && score !== null ? ` · ${formatRisk(score)}` : ""}
    </span>
  );
}

/** Predicted label: benign, abstained (needs_review), unclassified (anomaly-only) or an attack class. */
export function LabelBadge({ label }: { label: string | null | undefined }) {
  if (!label) return <Badge>—</Badge>;
  if (label === "Benign") return <Badge tone="success">Benign</Badge>;
  if (label === "needs_review") return <Badge tone="warning" title="Model confidence below the configured minimum">Needs review</Badge>;
  if (label === "unclassified") return <Badge title="Anomaly-only analysis: no class prediction">Unclassified</Badge>;
  return <Badge tone="danger">{label}</Badge>;
}

export function RoleBadge({ role }: { role: string }) {
  const tone: BadgeTone = role === "admin" ? "primary" : role === "analyst" ? "info" : "neutral";
  return <Badge tone={tone}>{humanize(role)}</Badge>;
}
