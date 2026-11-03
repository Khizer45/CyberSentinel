import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { StatusBadge } from "../components/Badge";
import { Card } from "../components/Card";
import { JsonView, KeyValueList } from "../components/DataDisplay";
import { DataTable } from "../components/DataTable";
import { SelectField, TextField } from "../components/FormFields";
import { Modal } from "../components/Modal";
import { PageHeader } from "../components/PageHeader";
import { Pagination } from "../components/Pagination";
import { useSearchState } from "../hooks/useSearchState";
import { listAuditLogs } from "../services/admin";
import { queryKeys } from "../services/queryKeys";
import type { AuditLog } from "../types/api";
import { dayBoundary, formatDateTime, humanize } from "../utils/format";

export const AUDIT_ACTIONS = [
  "auth.login.success",
  "auth.login.failure",
  "auth.login.locked",
  "auth.logout",
  "auth.password.change",
  "user.create",
  "user.update",
  "user.role.change",
  "user.deactivate",
  "user.activate",
  "user.password.reset",
  "dataset.upload",
  "dataset.reject",
  "dataset.import",
  "dataset.delete",
  "dataset.purge",
  "analysis.create",
  "analysis.complete",
  "analysis.fail",
  "analysis.cancel",
  "analysis.quick",
  "alert.review",
  "export.predictions",
  "export.alerts",
  "export.report",
  "model.register",
  "model.status.change",
  "model.verify",
  "model.integrity.failure",
  "access.denied",
];
const RESOURCE_TYPES = ["user", "dataset", "analysis_job", "prediction", "alert", "model_version", "report"];

export function AuditLogsPage() {
  const search = useSearchState();
  const [selected, setSelected] = useState<AuditLog | null>(null);
  const query = {
    action: search.get("action") || undefined,
    outcome: search.get("outcome") || undefined,
    resource_type: search.get("resource") || undefined,
    date_from: dayBoundary(search.get("from")),
    date_to: dayBoundary(search.get("to"), true),
    limit: search.getNumber("limit", 50),
    offset: search.getNumber("offset", 0),
  };
  const logs = useQuery({ queryKey: queryKeys.auditLogs(query), queryFn: () => listAuditLogs(query), placeholderData: keepPreviousData });

  return (
    <>
      <PageHeader
        title="Audit logs"
        description="Append-only record of security-relevant actions (sign-ins, data access, model changes, reviews and exports). Entries cannot be edited or deleted through the application."
      />
      <Card flush>
        <div className="filter-bar">
          <SelectField
            label="Action"
            placeholder="Any action"
            options={AUDIT_ACTIONS.map((action) => ({ value: action, label: action }))}
            value={search.get("action")}
            onChange={(event) => search.update({ action: event.target.value })}
          />
          <SelectField
            label="Outcome"
            placeholder="Any outcome"
            options={["success", "failure", "denied"].map((value) => ({ value, label: humanize(value) }))}
            value={search.get("outcome")}
            onChange={(event) => search.update({ outcome: event.target.value })}
          />
          <SelectField
            label="Resource"
            placeholder="Any resource"
            options={RESOURCE_TYPES.map((value) => ({ value, label: humanize(value) }))}
            value={search.get("resource")}
            onChange={(event) => search.update({ resource: event.target.value })}
          />
          <TextField label="From" type="date" value={search.get("from")} onChange={(event) => search.update({ from: event.target.value })} />
          <TextField label="To" type="date" value={search.get("to")} onChange={(event) => search.update({ to: event.target.value })} />
        </div>
        <DataTable<AuditLog>
          caption="Audit log entries"
          compact
          rows={logs.data?.items}
          loading={logs.isFetching}
          error={logs.error}
          onRetry={() => void logs.refetch()}
          rowKey={(row) => row.id}
          onRowClick={setSelected}
          rowLabel={(row) => `Show audit entry ${row.action} at ${row.created_at}`}
          emptyTitle="No audit entries match"
          columns={[
            { key: "time", header: "Time", render: (row) => <span className="nowrap">{formatDateTime(row.created_at)}</span> },
            { key: "action", header: "Action", render: (row) => <code>{row.action}</code> },
            { key: "outcome", header: "Outcome", render: (row) => <StatusBadge status={row.outcome} /> },
            { key: "actor", header: "Actor", render: (row) => (row.actor ? row.actor.email : <span className="subtle">system / anonymous</span>) },
            {
              key: "resource",
              header: "Resource",
              render: (row) =>
                row.resource_type ? (
                  <span className="small">
                    {humanize(row.resource_type)} {row.resource_id ? <code>{row.resource_id.slice(0, 8)}</code> : null}
                  </span>
                ) : (
                  <span className="subtle">—</span>
                ),
            },
            { key: "ip", header: "Client", render: (row) => <span className="small mono">{row.ip_address ?? "—"}</span> },
          ]}
        />
        {logs.data ? (
          <Pagination
            total={logs.data.total}
            limit={query.limit}
            offset={query.offset}
            onChange={(offset) => search.update({ offset }, { resetPage: false })}
            onLimitChange={(limit) => search.update({ limit })}
          />
        ) : null}
      </Card>
      <Modal open={selected !== null} title="Audit entry" onClose={() => setSelected(null)} wide>
        {selected ? (
          <>
            <KeyValueList
              items={[
                { label: "Time", value: formatDateTime(selected.created_at) },
                { label: "Action", value: <code>{selected.action}</code> },
                { label: "Outcome", value: <StatusBadge status={selected.outcome} /> },
                { label: "Actor", value: selected.actor ? `${selected.actor.display_name} (${selected.actor.email})` : "System / anonymous" },
                { label: "Resource", value: selected.resource_type ? `${humanize(selected.resource_type)} ${selected.resource_id ?? ""}` : "—" },
                { label: "Client", value: selected.ip_address ?? "—" },
                { label: "Request ID", value: selected.request_id ? <code>{selected.request_id}</code> : "—" },
              ]}
            />
            <h3>Details</h3>
            {selected.details && Object.keys(selected.details).length ? <JsonView value={selected.details} /> : <p className="muted">No additional details.</p>}
          </>
        ) : null}
      </Modal>
    </>
  );
}
