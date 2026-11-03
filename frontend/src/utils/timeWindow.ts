/** Relative reporting windows. The concrete timestamps are computed when a request is made, not during render. */
import type { DateWindow } from "../services/metrics";

export const WINDOW_OPTIONS = [
  { value: "24h", label: "Last 24 hours" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
  { value: "all", label: "All time" },
];

const HOURS: Record<string, number> = { "24h": 24, "7d": 24 * 7, "30d": 24 * 30, "90d": 24 * 90 };

export function windowRange(code: string): DateWindow {
  const hours = HOURS[code];
  if (!hours) return {};
  return { date_from: new Date(Date.now() - hours * 3600_000).toISOString() };
}

export function normalizeWindow(code: string, fallback = "30d"): string {
  return code === "all" || code in HOURS ? code : fallback;
}
