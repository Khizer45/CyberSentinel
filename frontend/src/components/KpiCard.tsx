import { Link } from "react-router";
import { cx } from "../utils/cx";

interface KpiCardProps {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "danger" | "warning" | "success";
  to?: string;
}

export function KpiCard({ label, value, hint, tone = "default", to }: KpiCardProps) {
  const body = (
    <>
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}</span>
      {hint ? <span className="kpi-hint">{hint}</span> : null}
    </>
  );
  const className = cx("kpi", tone !== "default" && `tone-${tone}`);
  return to ? (
    <Link to={to} className={className}>
      {body}
    </Link>
  ) : (
    <div className={className}>{body}</div>
  );
}
