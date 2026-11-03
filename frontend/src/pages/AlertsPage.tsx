import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { LabelBadge, RiskBadge, StatusBadge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { ChipGroup, TextField } from "../components/FormFields";
import { PageHeader } from "../components/PageHeader";
import { Pagination } from "../components/Pagination";
import { useToast } from "../components/Toast";
import { DispositionBadge } from "../features/alerts/ReviewPanel";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { useSearchState } from "../hooks/useSearchState";
import { exportAlerts, listAlerts, type AlertQuery } from "../services/alerts";
import { queryKeys } from "../services/queryKeys";
import { ALERT_STATUSES, RISK_BANDS, type Alert } from "../types/api";
import { saveBlob } from "../utils/download";
import { errorMessage } from "../utils/errors";
import { dayBoundary, formatDateTime, formatNumber, formatScore, humanize } from "../utils/format";

export function AlertsPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const search = useSearchState();
  const [labelText, setLabelText] = useState(search.get("label"));
  const [ipText, setIpText] = useState(search.get("ip"));
  const label = useDebouncedValue(labelText.trim(), 350);
  const ip = useDebouncedValue(ipText.trim(), 500);
  const [exporting, setExporting] = useState<"csv" | "json" | null>(null);

  const query: AlertQuery = {
    severity: search.getAll("severity"),
    status: search.getAll("status"),
    label: label ? [label] : undefined,
    ip: ip || undefined,
    analysis_job_id: search.get("job") || undefined,
    date_from: dayBoundary(search.get("from")),
    date_to: dayBoundary(search.get("to"), true),
    sort: search.get("sort", "-created_at"),
    limit: search.getNumber("limit", 25),
    offset: search.getNumber("offset", 0),
  };
  const alerts = useQuery({ queryKey: queryKeys.alerts(query), queryFn: () => listAlerts(query), placeholderData: keepPreviousData });

  const runExport = async (format: "csv" | "json") => {
    setExporting(format);
    try {
      const file = await exportAlerts(format, query);
      saveBlob(file.blob, file.filename);
      if (file.truncated) toast.info("The export reached the server's row limit and was truncated. Narrow the filters to export the rest.");
      else toast.success("Export downloaded.");
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setExporting(null);
    }
  };

  return (
    <>
      <PageHeader
        title="Alerts"
        description="Flows whose policy risk band reached the alert threshold. Review each alert and record a disposition; reviews are append-only."
        actions={
          <>
            <Button icon="download" loading={exporting === "csv"} disabled={exporting !== null} onClick={() => void runExport("csv")}>
              Export CSV
            </Button>
            <Button icon="download" loading={exporting === "json"} disabled={exporting !== null} onClick={() => void runExport("json")}>
              Export JSON
            </Button>
          </>
        }
      />
      <Card flush>
        <div className="filter-bar">
          <ChipGroup
            label="Severity"
            options={RISK_BANDS.map((band) => ({ value: band, label: humanize(band) }))}
            selected={query.severity ?? []}
            onChange={(values) => search.update({ severity: values })}
          />
          <ChipGroup
            label="Status"
            options={ALERT_STATUSES.map((status) => ({ value: status, label: humanize(status) }))}
            selected={query.status ?? []}
            onChange={(values) => search.update({ status: values })}
          />
        </div>
        <div className="filter-bar">
          <TextField
            label="Predicted label"
            placeholder="e.g. DoS"
            value={labelText}
            onChange={(event) => {
              setLabelText(event.target.value);
              search.update({ label: event.target.value });
            }}
          />
          <TextField
            label="IP address"
            placeholder="Source or destination"
            hint="Matched via pseudonym; raw IPs are not stored."
            value={ipText}
            maxLength={45}
            onChange={(event) => {
              setIpText(event.target.value);
              search.update({ ip: event.target.value });
            }}
          />
          <TextField label="From" type="date" value={search.get("from")} onChange={(event) => search.update({ from: event.target.value })} />
          <TextField label="To" type="date" value={search.get("to")} onChange={(event) => search.update({ to: event.target.value })} />
          {query.analysis_job_id ? (
            <Button size="sm" variant="ghost" icon="close" onClick={() => search.update({ job: null })}>
              Clear job filter
            </Button>
          ) : null}
        </div>
        <DataTable<Alert>
          caption="Alerts"
          rows={alerts.data?.items}
          loading={alerts.isFetching}
          error={alerts.error}
          onRetry={() => void alerts.refetch()}
          rowKey={(row) => row.id}
          sort={query.sort}
          onSortChange={(sort) => search.update({ sort })}
          onRowClick={(row) => navigate(`/alerts/${row.id}`)}
          rowLabel={(row) => `Open alert for record ${row.record_index} of ${row.dataset_name}`}
          emptyTitle="No alerts match these filters"
          emptyMessage="Alerts appear when completed analyses produce high-risk predictions."
          columns={[
            { key: "risk", header: "Risk", sortKey: "risk_score", render: (row) => <RiskBadge band={row.risk_band} score={row.risk_score} /> },
            { key: "label", header: "Prediction", render: (row) => <LabelBadge label={row.predicted_label} /> },
            {
              key: "scores",
              header: "Scores",
              render: (row) => (
                <span className="small">
                  {row.probability !== null ? `p ${formatScore(row.probability)}` : `clf ${formatScore(row.classifier_score)}`}
                  {row.anomaly_score !== null ? ` · anom ${formatScore(row.anomaly_score)}` : ""}
                  {row.is_anomaly ? " ⚑" : ""}
                </span>
              ),
            },
            {
              key: "source",
              header: "Source",
              render: (row) => (
                <div className="stack-sm" style={{ gap: 0 }}>
                  <span className="break">{row.dataset_name}</span>
                  <span className="small subtle">record {formatNumber(row.record_index)}</span>
                </div>
              ),
            },
            {
              key: "model",
              header: "Model",
              render: (row) => (
                <span className="small">
                  {row.model_name} {row.model_version}
                </span>
              ),
            },
            { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
            {
              key: "review",
              header: "Latest review",
              render: (row) => (row.latest_disposition ? <DispositionBadge disposition={row.latest_disposition} /> : <span className="subtle">—</span>),
            },
            { key: "created", header: "Detected", sortKey: "created_at", render: (row) => <span className="nowrap">{formatDateTime(row.created_at)}</span> },
          ]}
        />
        {alerts.data ? (
          <Pagination
            total={alerts.data.total}
            limit={query.limit ?? 25}
            offset={query.offset ?? 0}
            onChange={(offset) => search.update({ offset }, { resetPage: false })}
            onLimitChange={(limit) => search.update({ limit })}
          />
        ) : null}
      </Card>
    </>
  );
}
