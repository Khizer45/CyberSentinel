/** Locale-aware formatting helpers. Missing values render as an em dash so "no data" is never shown as zero. */
export const EMPTY = "—";

const integerFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });

export function formatNumber(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return EMPTY;
  if (digits === 0) return integerFormat.format(value);
  return new Intl.NumberFormat(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
}

/** ``value`` is a fraction in [0, 1]. */
export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return EMPTY;
  return new Intl.NumberFormat(undefined, { style: "percent", minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
}

/** Model scores (probabilities, classifier and anomaly scores) keep enough precision to be comparable. */
export function formatScore(value: number | null | undefined, digits = 3): string {
  return formatNumber(value, digits);
}

/** Policy risk score on the 0–100 scale. */
export function formatRisk(value: number | null | undefined): string {
  return formatNumber(value, 1);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return EMPTY;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return EMPTY;
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return EMPTY;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return EMPTY;
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes)) return EMPTY;
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${formatNumber(value, unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return EMPTY;
  if (seconds < 1) return `${formatNumber(seconds * 1000)} ms`;
  if (seconds < 60) return `${formatNumber(seconds, 1)} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes} min ${rest} s`;
}

/** ``snake_case`` / ``kebab-case`` identifiers → "Sentence case" for display. */
export function humanize(value: string | null | undefined): string {
  if (!value) return EMPTY;
  const text = value.replace(/[_-]+/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function shortId(id: string | null | undefined): string {
  return id ? id.slice(0, 8) : EMPTY;
}

/** ``YYYY-MM-DD`` (from a date input) → ISO timestamp at the start or end of that local day. */
export function dayBoundary(day: string, end = false): string | undefined {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return undefined;
  const [y, m, d] = day.split("-").map(Number) as [number, number, number];
  const date = end ? new Date(y, m - 1, d, 23, 59, 59, 999) : new Date(y, m - 1, d, 0, 0, 0, 0);
  return date.toISOString();
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

/**
 * Trend bucket from the API (e.g. ``2026-11-03 00:00:00+00:00``) → a timezone-free label Plotly can place on a
 * date axis. Daily buckets keep their UTC calendar date; hourly buckets are shown in the browser's local time.
 */
export function trendBucketLabel(bucket: string, granularity: "day" | "hour"): string {
  const date = new Date(bucket.trim().replace(" ", "T"));
  if (Number.isNaN(date.getTime())) return bucket;
  if (granularity === "day") return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`;
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:00`;
}

/** Shift a timezone-free ``YYYY-MM-DD[ HH:mm]`` label by ``ms`` milliseconds (wall-clock arithmetic). */
export function shiftTimeLabel(label: string, ms: number): string {
  const [day = "", time = "00:00"] = label.split(" ");
  const [y, m, d] = day.split("-").map(Number) as [number, number, number];
  const [hh, mm] = time.split(":").map(Number) as [number, number];
  const date = new Date(Date.UTC(y, m - 1, d, hh || 0, mm || 0) + ms);
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}`;
}
