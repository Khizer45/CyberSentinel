import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { Button, LinkButton } from "../components/Button";
import { Card } from "../components/Card";
import { ProgressBar } from "../components/DataDisplay";
import { FileDropZone } from "../components/FileDropZone";
import { SelectField, TextField } from "../components/FormFields";
import { PageHeader } from "../components/PageHeader";
import { Callout, ErrorCallout } from "../components/States";
import { useToast } from "../components/Toast";
import { ValidationReport } from "../features/datasets/ValidationReport";
import { useServerLimits } from "../hooks/useServerLimits";
import { toApiError } from "../services/apiClient";
import { listDatasetSchemas, uploadDataset } from "../services/datasets";
import { queryKeys } from "../services/queryKeys";
import type { Dataset, DatasetSchema } from "../types/api";
import { normalizeColumnName, parseCsv, readFileHead, type ParsedCsv } from "../utils/csv";
import { formatBytes, formatNumber, formatPercent } from "../utils/format";

const PREVIEW_ROWS = 5;
const PREVIEW_COLUMNS = 14;

interface LocalCheck {
  file: File;
  problems: string[];
  preview: ParsedCsv | null;
}

/** Preliminary, client-side guess only: the server performs the authoritative schema detection. */
function schemaCoverage(header: string[], schemas: DatasetSchema[]): { schema: DatasetSchema; coverage: number }[] {
  const names = new Set(header.map(normalizeColumnName));
  return schemas
    .map((schema) => {
      const features = schema.features.map((feature) => feature.name);
      const found = features.filter((name) => names.has(name)).length;
      return { schema, coverage: features.length ? found / features.length : 0 };
    })
    .sort((a, b) => b.coverage - a.coverage);
}

export function DatasetUploadPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const limits = useServerLimits();
  const schemas = useQuery({ queryKey: queryKeys.schemas, queryFn: listDatasetSchemas, staleTime: Infinity });
  const [check, setCheck] = useState<LocalCheck | null>(null);
  const [name, setName] = useState("");
  const [schemaVersion, setSchemaVersion] = useState("auto");
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<Dataset | null>(null);

  const upload = useMutation({
    mutationFn: (file: File) => uploadDataset(file, { name: name.trim() || undefined, schemaVersion }, setProgress),
    onSuccess: async (dataset) => {
      setResult(dataset);
      toast.success(`Dataset "${dataset.name}" validated (${formatNumber(dataset.row_count)} rows).`);
      await queryClient.invalidateQueries({ queryKey: queryKeys.datasetsAll });
    },
    onError: async () => {
      // Rejected uploads are recorded server-side (status "rejected"); refresh the list either way.
      await queryClient.invalidateQueries({ queryKey: queryKeys.datasetsAll });
    },
  });

  const onFile = async (file: File) => {
    upload.reset();
    setResult(null);
    setProgress(0);
    const problems: string[] = [];
    if (!file.name.toLowerCase().endsWith(".csv")) problems.push("Only .csv files are accepted.");
    if (file.size === 0) problems.push("The file is empty.");
    if (file.size > limits.maxUploadMb * 1024 * 1024) problems.push(`The file is larger than the ${formatNumber(limits.maxUploadMb)} MB upload limit.`);
    let preview: ParsedCsv | null = null;
    if (problems.length === 0) {
      try {
        preview = parseCsv(await readFileHead(file), PREVIEW_ROWS);
        if (preview.header.length < 2) problems.push("The file does not look like a comma-separated file with a header row.");
      } catch {
        problems.push("The file could not be read as text.");
      }
    }
    setCheck({ file, problems, preview });
    if (!name) setName(file.name.replace(/\.csv$/i, "").slice(0, 180));
  };

  const coverage = useMemo(
    () => (check?.preview && schemas.data ? schemaCoverage(check.preview.header, schemas.data) : []),
    [check, schemas.data],
  );
  const best = coverage[0];
  const rejection = upload.error ? toApiError(upload.error) : null;

  return (
    <>
      <PageHeader
        title="Upload dataset"
        description="Upload a CSV export of network flows in the CICIDS2017 or UNSW-NB15 format. The server validates structure, schema, values and size before the dataset can be analysed."
        back={{ to: "/datasets", label: "Datasets" }}
      />
      <div className="grid-2" style={{ alignItems: "start" }}>
        <Card title="1. Choose a file">
          <div className="stack">
            <FileDropZone
              onFile={(file) => void onFile(file)}
              disabled={upload.isPending}
              hint={`CSV only · up to ${formatNumber(limits.maxUploadMb)} MB and ${formatNumber(limits.maxUploadRows)} rows`}
            />
            {check ? (
              <div className="row-between">
                <span>
                  <strong className="break">{check.file.name}</strong> <span className="muted">({formatBytes(check.file.size)})</span>
                </span>
              </div>
            ) : null}
            {check?.problems.length ? (
              <Callout tone="danger" title="This file cannot be uploaded">
                <ul>
                  {check.problems.map((problem) => (
                    <li key={problem}>{problem}</li>
                  ))}
                </ul>
              </Callout>
            ) : null}
            <Callout tone="info">
              Uploaded files are stored outside the web root under a random name, are never executed, and are parsed as data only. Do not
              upload files containing personal data that you are not authorised to process.
            </Callout>
          </div>
        </Card>

        <Card title="2. Describe and upload">
          <form
            className="stack"
            onSubmit={(event) => {
              event.preventDefault();
              if (check && check.problems.length === 0) upload.mutate(check.file);
            }}
          >
            <TextField label="Dataset name" value={name} maxLength={180} onChange={(event) => setName(event.target.value)} hint="Defaults to the file name." />
            <SelectField
              label="Schema"
              value={schemaVersion}
              onChange={(event) => setSchemaVersion(event.target.value)}
              options={[
                { value: "auto", label: "Detect automatically" },
                ...(schemas.data ?? []).map((schema) => ({ value: schema.schema_version, label: `${schema.display_name} (${schema.schema_version})` })),
              ]}
              hint={
                best && best.coverage > 0
                  ? `Preliminary check: ${formatPercent(best.coverage, 0)} of ${best.schema.display_name} features found in the header. The server makes the final decision.`
                  : "The server detects the schema from the column names."
              }
            />
            {upload.isPending ? <ProgressBar value={progress} label="Upload progress" /> : null}
            {upload.isPending && progress >= 1 ? <p className="muted small">Upload complete — the server is validating the file…</p> : null}
            {rejection ? (
              rejection.code === "dataset_rejected" ? (
                <Callout tone="danger" title="The server rejected the file">
                  <p>{rejection.message}</p>
                  <RejectionReason details={rejection.details} />
                </Callout>
              ) : (
                <ErrorCallout error={upload.error} />
              )
            ) : null}
            <div className="row">
              <Button type="submit" variant="primary" icon="upload" loading={upload.isPending} disabled={!check || check.problems.length > 0 || Boolean(result)}>
                Upload and validate
              </Button>
            </div>
          </form>
        </Card>
      </div>

      {check?.preview && check.problems.length === 0 && !result ? <PreviewTable preview={check.preview} /> : null}

      {result ? (
        <Card
          title="Validation passed"
          subtitle={`${result.name} · ${formatNumber(result.row_count)} rows · schema ${result.schema_version ?? "—"}`}
          actions={
            <>
              <LinkButton to="/datasets">All datasets</LinkButton>
              <Button variant="primary" icon="play" onClick={() => navigate(`/analyses?new=1&dataset=${result.id}`)}>
                Analyze this dataset
              </Button>
            </>
          }
        >
          <ValidationReport report={result.validation_report} />
        </Card>
      ) : null}
    </>
  );
}

function RejectionReason({ details }: { details: unknown }) {
  if (!details || typeof details !== "object") return null;
  const record = details as Record<string, unknown>;
  const entries = Object.entries(record).filter(([key]) => key !== "dataset_id");
  if (entries.length === 0) return null;
  return (
    <ul>
      {entries.slice(0, 10).map(([key, value]) => (
        <li key={key}>
          <strong>{key.replace(/_/g, " ")}:</strong> {typeof value === "object" ? JSON.stringify(value).slice(0, 400) : String(value)}
        </li>
      ))}
    </ul>
  );
}

function PreviewTable({ preview }: { preview: ParsedCsv }) {
  const columns = preview.header.slice(0, PREVIEW_COLUMNS);
  return (
    <Card
      title="Local preview"
      subtitle={`First ${Math.min(PREVIEW_ROWS, preview.rows.length)} rows and ${columns.length} of ${formatNumber(preview.header.length)} columns, read in your browser. Nothing has been uploaded yet.`}
      flush
    >
      <div className="table-wrap">
        <table className="table table-compact">
          <caption className="sr-only">Local preview of the selected file</caption>
          <thead>
            <tr>
              {columns.map((column, index) => (
                <th key={`${column}-${index}`} scope="col">
                  {column || `(column ${index + 1})`}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {preview.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {columns.map((_, index) => (
                  <td key={index} className="mono nowrap">
                    {(row[index] ?? "").slice(0, 40)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
