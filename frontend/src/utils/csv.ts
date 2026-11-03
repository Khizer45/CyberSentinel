/**
 * Minimal RFC 4180 CSV parsing for *client-side previews and quick analysis only*.
 * The authoritative validation of uploaded files happens on the server; nothing parsed here is executed.
 */
import type { FeatureValue } from "../services/analyses";

export interface ParsedCsv {
  header: string[];
  rows: string[][];
  /** True when parsing stopped at ``maxRows`` (more rows exist). */
  truncated: boolean;
}

export function parseCsv(text: string, maxRows = Number.POSITIVE_INFINITY): ParsedCsv {
  const records: string[][] = [];
  let field = "";
  let record: string[] = [];
  let inQuotes = false;
  let truncated = false;
  const input = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;

  const endRecord = (): boolean => {
    record.push(field);
    field = "";
    if (!(record.length === 1 && record[0] === "")) records.push(record);
    record = [];
    if (records.length > maxRows) {
      truncated = true;
      return true;
    }
    return false;
  };

  for (let i = 0; i < input.length; i += 1) {
    const char = input[i];
    if (inQuotes) {
      if (char === '"') {
        if (input[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        field += char;
      }
      continue;
    }
    if (char === '"' && field === "") inQuotes = true;
    else if (char === ",") {
      record.push(field);
      field = "";
    } else if (char === "\n" || char === "\r") {
      if (char === "\r" && input[i + 1] === "\n") i += 1;
      if (endRecord()) break;
    } else field += char;
  }
  if (!truncated && (field !== "" || record.length > 0)) endRecord();
  const [header = [], ...rows] = records;
  return { header, rows: truncated ? rows.slice(0, maxRows) : rows, truncated };
}

/** Read only the first ``bytes`` of a file for a header/sample preview (large files are never fully loaded). */
export async function readFileHead(file: Blob, bytes = 64 * 1024): Promise<string> {
  const slice = file.slice(0, bytes);
  const text = await slice.text();
  if (file.size <= bytes) return text;
  const lastNewline = Math.max(text.lastIndexOf("\n"), text.lastIndexOf("\r"));
  return lastNewline > 0 ? text.slice(0, lastNewline) : text;
}

/** Mirror of the backend's header normalization: " Flow Bytes/s" → "flow_bytes_s". */
export function normalizeColumnName(name: string): string {
  return name
    .normalize("NFKC")
    .replace(/\uFEFF/g, "")
    .trim()
    .toLowerCase()
    .replace(/[^0-9a-z]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

const NUMBER_PATTERN = /^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$/;
const NON_FINITE = new Set(["nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"]);

export interface RecordConversion {
  records: Record<string, FeatureValue>[];
  excludedColumns: string[];
  nonFiniteValues: number;
}

/**
 * Convert CSV rows to JSON flow records for ``POST /analyze/batch``: numbers become numbers, empty cells and
 * non-finite values (NaN/Infinity, which JSON cannot carry) become ``null`` (imputed by the model's preprocessor),
 * other text stays text. Columns whose normalized name is in ``exclude`` (labels, identifiers) are dropped.
 */
export function rowsToRecords(header: string[], rows: string[][], exclude: Set<string>): RecordConversion {
  const keep = header.map((name) => !exclude.has(normalizeColumnName(name)));
  const excludedColumns = header.filter((_, index) => !keep[index]);
  let nonFiniteValues = 0;
  const records = rows.map((row) => {
    const record: Record<string, FeatureValue> = {};
    header.forEach((name, index) => {
      if (!keep[index]) return;
      const raw = (row[index] ?? "").trim();
      if (raw === "") record[name] = null;
      else if (NUMBER_PATTERN.test(raw)) record[name] = Number(raw);
      else if (NON_FINITE.has(raw.toLowerCase())) {
        record[name] = null;
        nonFiniteValues += 1;
      } else record[name] = raw;
    });
    return record;
  });
  return { records, excludedColumns, nonFiniteValues };
}
