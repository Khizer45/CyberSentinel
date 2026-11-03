/**
 * Quick analysis of a few flow records without creating a dataset (``POST /analyze/batch``).
 * Records are parsed in the browser from pasted CSV or JSON and sent as JSON; nothing is executed.
 */
import { Fragment, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { LabelBadge, RiskBadge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { SelectField, TextAreaField } from "../../components/FormFields";
import { Callout, ErrorCallout } from "../../components/States";
import { useServerLimits } from "../../hooks/useServerLimits";
import { quickAnalyze, type FeatureValue } from "../../services/analyses";
import { listDatasetSchemas } from "../../services/datasets";
import { listModels } from "../../services/models";
import { queryKeys } from "../../services/queryKeys";
import type { AnalysisMode, QuickAnalysisResponse } from "../../types/api";
import { normalizeColumnName, parseCsv, rowsToRecords } from "../../utils/csv";
import { detailErrors } from "../../utils/errors";
import { formatNumber, formatScore } from "../../utils/format";
import { ExplanationView } from "../alerts/ExplanationView";
import { MODE_LABELS, preferredMode } from "./modes";

type InputFormat = "csv" | "json";

interface ParsedInput {
  records: Record<string, FeatureValue>[];
  notes: string[];
  error: string | null;
}

function parseJsonRecords(text: string): ParsedInput {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return { records: [], notes: [], error: "The text is not valid JSON." };
  }
  const list = Array.isArray(value) ? value : [value];
  const records: Record<string, FeatureValue>[] = [];
  for (const [index, item] of list.entries()) {
    if (!item || typeof item !== "object" || Array.isArray(item)) return { records: [], notes: [], error: `Record ${index + 1} is not a JSON object.` };
    const record: Record<string, FeatureValue> = {};
    for (const [key, field] of Object.entries(item as Record<string, unknown>)) {
      if (field === null || typeof field === "string" || (typeof field === "number" && Number.isFinite(field))) record[key] = field;
      else return { records: [], notes: [], error: `Record ${index + 1}, feature "${key}": values must be numbers, strings or null.` };
    }
    records.push(record);
  }
  return { records, notes: [], error: null };
}

function parseInput(text: string, format: InputFormat, exclude: Set<string>): ParsedInput {
  if (!text.trim()) return { records: [], notes: [], error: null };
  if (format === "json") return parseJsonRecords(text);
  const parsed = parseCsv(text);
  if (parsed.header.length === 0 || parsed.rows.length === 0) return { records: [], notes: [], error: "Paste a header row followed by at least one data row." };
  const converted = rowsToRecords(parsed.header, parsed.rows, exclude);
  const notes: string[] = [];
  if (converted.excludedColumns.length) notes.push(`Label/identifier columns not sent: ${converted.excludedColumns.join(", ")}.`);
  if (converted.nonFiniteValues) notes.push(`${converted.nonFiniteValues} NaN/Infinity value(s) were sent as missing (null) and will be imputed.`);
  return { records: converted.records, notes, error: null };
}

export function QuickAnalysisPanel() {
  const limits = useServerLimits();
  const models = useQuery({ queryKey: queryKeys.models({ status: ["approved"] }), queryFn: () => listModels({ status: ["approved"] }) });
  const schemas = useQuery({ queryKey: queryKeys.schemas, queryFn: listDatasetSchemas, staleTime: Infinity });
  const [modelId, setModelId] = useState("");
  const [mode, setMode] = useState<AnalysisMode | "">("");
  const [format, setFormat] = useState<InputFormat>("csv");
  const [text, setText] = useState("");
  const [result, setResult] = useState<QuickAnalysisResponse | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  const model = models.data?.find((item) => item.id === modelId);
  const effectiveMode: AnalysisMode | "" = model ? (mode && model.supported_modes.includes(mode) ? mode : preferredMode(model.supported_modes)) : "";
  const schema = schemas.data?.find((item) => item.schema_version === model?.feature_schema_version);
  const exclude = useMemo(
    () => new Set([...(schema?.identifier_columns ?? []), ...(schema?.label_columns ?? [])].map(normalizeColumnName)),
    [schema],
  );
  const parsed = useMemo(() => parseInput(text, format, exclude), [text, format, exclude]);
  const tooMany = parsed.records.length > limits.quickAnalysisMaxRecords;

  const run = useMutation({
    mutationFn: () => quickAnalyze(modelId, effectiveMode, parsed.records),
    onSuccess: (response) => {
      setResult(response);
      setExpanded(null);
    },
  });
  const recordErrors = detailErrors(run.error);

  return (
    <div className="stack">
      <Card title="Quick analysis" subtitle="Score a handful of flow records immediately. Results are returned to you and are not stored as a job.">
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            if (model && parsed.records.length && !tooMany && !parsed.error) run.mutate();
          }}
        >
          <div className="grid-3">
            <SelectField
              label="Approved model"
              placeholder={models.isPending ? "Loading…" : "Select a model"}
              value={modelId}
              onChange={(event) => {
                setModelId(event.target.value);
                setMode("");
                setResult(null);
              }}
              options={(models.data ?? []).map((item) => ({
                value: item.id,
                label: `${item.model_name} ${item.version} · ${item.feature_schema_version}`,
              }))}
            />
            <SelectField
              label="Mode"
              value={effectiveMode}
              disabled={!model}
              onChange={(event) => setMode(event.target.value as AnalysisMode)}
              options={(model?.supported_modes ?? []).map((value) => ({ value, label: MODE_LABELS[value as AnalysisMode] ?? value }))}
              placeholder={model ? undefined : "Select a model first"}
            />
            <SelectField
              label="Input format"
              value={format}
              onChange={(event) => setFormat(event.target.value as InputFormat)}
              options={[
                { value: "csv", label: "CSV (header + rows)" },
                { value: "json", label: "JSON (object or array of objects)" },
              ]}
            />
          </div>
          <TextAreaField
            label="Flow records"
            value={text}
            rows={8}
            spellCheck={false}
            placeholder={format === "csv" ? "Paste the CSV header row and up to a few data rows…" : '[{"feature_name": 123, "other_feature": "tcp"}]'}
            onChange={(event) => setText(event.target.value)}
            error={parsed.error ?? (tooMany ? `At most ${formatNumber(limits.quickAnalysisMaxRecords)} records per request.` : null)}
            hint={
              schema
                ? `Expected: the ${schema.display_name} feature columns (${formatNumber(schema.features.length)} features). Missing values may be empty/null; they are imputed.`
                : "Select a model to see which feature columns are expected."
            }
          />
          {parsed.notes.length ? (
            <Callout tone="info">
              <ul>
                {parsed.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </Callout>
          ) : null}
          <ErrorCallout error={run.error} />
          {recordErrors.length ? (
            <Callout tone="warning" title="Record problems reported by the server">
              <ul>
                {recordErrors.slice(0, 15).map((item, index) => (
                  <li key={index}>
                    Record {(item.record ?? 0) + 1}
                    {item.feature ? `, ${item.feature}` : ""}: {item.error}
                  </li>
                ))}
              </ul>
            </Callout>
          ) : null}
          <div className="row">
            <Button type="submit" variant="primary" icon="bolt" loading={run.isPending} disabled={!model || !parsed.records.length || tooMany || Boolean(parsed.error)}>
              Analyze {parsed.records.length ? `${formatNumber(parsed.records.length)} record${parsed.records.length === 1 ? "" : "s"}` : ""}
            </Button>
          </div>
        </form>
      </Card>

      {result ? (
        <Card
          title="Results"
          subtitle={`${result.model.model_name} ${result.model.version} · ${MODE_LABELS[result.mode]} · risk policy ${result.risk_policy_version}`}
          flush
        >
          <div className="stack" style={{ padding: "0 20px 12px" }}>
            {result.warnings?.length ? (
              <Callout tone="warning" title="Warnings">
                <ul>
                  {result.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </Callout>
            ) : null}
            {result.ignored_features.length ? <p className="small muted">Ignored (not used by this model): {result.ignored_features.join(", ")}</p> : null}
            {result.disclaimer ? <p className="small muted">{result.disclaimer}</p> : null}
          </div>
          <div className="table-wrap">
            <table className="table">
              <caption className="sr-only">Quick analysis results</caption>
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">Prediction</th>
                  <th scope="col" className="num">
                    Probability
                  </th>
                  <th scope="col" className="num">
                    Classifier score
                  </th>
                  <th scope="col" className="num">
                    Anomaly score
                  </th>
                  <th scope="col">Risk</th>
                  <th scope="col">Alert</th>
                  <th scope="col">
                    <span className="sr-only">Explanation</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {result.results.map((row) => (
                  <Fragment key={row.index}>
                    <tr>
                      <td>{row.index + 1}</td>
                      <td>
                        <LabelBadge label={row.predicted_label} />
                        {row.top_label && row.top_label !== row.predicted_label ? <span className="small subtle"> top class: {row.top_label}</span> : null}
                      </td>
                      <td className="num">{row.scores_calibrated ? formatScore(row.probability) : <span className="subtle">n/a</span>}</td>
                      <td className="num">{formatScore(row.classifier_score)}</td>
                      <td className="num">
                        {formatScore(row.anomaly_score)}
                        {row.is_anomaly ? " ⚑" : ""}
                      </td>
                      <td>
                        <RiskBadge band={row.risk_band} score={row.risk_score} />
                      </td>
                      <td>{row.is_alert ? "Yes" : "No"}</td>
                      <td className="text-right">
                        {row.explanation ? (
                          <Button size="sm" variant="ghost" aria-expanded={expanded === row.index} onClick={() => setExpanded(expanded === row.index ? null : row.index)}>
                            {expanded === row.index ? "Hide" : "Explain"}
                          </Button>
                        ) : null}
                      </td>
                    </tr>
                    {expanded === row.index && row.explanation ? (
                      <tr>
                        <td colSpan={8}>
                          <ExplanationView explanation={row.explanation} />
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
