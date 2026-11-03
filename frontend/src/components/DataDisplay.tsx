import type { ReactNode } from "react";
import { cx } from "../utils/cx";

export interface KeyValueItem {
  label: string;
  value: ReactNode;
}

export function KeyValueList({ items }: { items: KeyValueItem[] }) {
  return (
    <dl className="kv">
      {items.map((item) => (
        <div key={item.label} style={{ display: "contents" }}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Pretty-printed JSON rendered as text (never as HTML). */
export function JsonView({ value, label }: { value: unknown; label?: string }) {
  return (
    <pre className="json-view" aria-label={label} tabIndex={0}>
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function ProgressBar({ value, label, tone }: { value: number; label: string; tone?: "success" | "danger" }) {
  const percent = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div className="progress" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
      <div className={cx("progress-bar", tone && `tone-${tone}`)} style={{ width: `${percent}%` }} />
    </div>
  );
}
