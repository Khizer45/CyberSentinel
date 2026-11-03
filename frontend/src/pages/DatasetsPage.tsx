import { useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { Badge, StatusBadge } from "../components/Badge";
import { Button, LinkButton } from "../components/Button";
import { Card } from "../components/Card";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { KeyValueList } from "../components/DataDisplay";
import { DataTable } from "../components/DataTable";
import { Checkbox, SelectField, TextField } from "../components/FormFields";
import { Modal } from "../components/Modal";
import { PageHeader } from "../components/PageHeader";
import { Pagination } from "../components/Pagination";
import { useToast } from "../components/Toast";
import { useAuth } from "../features/auth/AuthContext";
import { isAdmin } from "../features/auth/roles";
import { ValidationReport } from "../features/datasets/ValidationReport";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { useSearchState } from "../hooks/useSearchState";
import { deleteDataset, listDatasets, listDatasetSchemas } from "../services/datasets";
import { queryKeys } from "../services/queryKeys";
import type { Dataset } from "../types/api";
import { formatBytes, formatDateTime, formatNumber, humanize } from "../utils/format";

const STATUS_OPTIONS = ["validated", "rejected", "pending", "deleted"].map((value) => ({ value, label: humanize(value) }));

export function DatasetsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const search = useSearchState();
  const [searchText, setSearchText] = useState(search.get("q"));
  const debouncedText = useDebouncedValue(searchText, 350);
  const [selected, setSelected] = useState<Dataset | null>(null);
  const [toDelete, setToDelete] = useState<Dataset | null>(null);

  const query = {
    q: debouncedText.trim() || undefined,
    status: search.get("status") || undefined,
    schema_version: search.get("schema") || undefined,
    include_deleted: search.get("status") === "deleted" || search.getBoolean("deleted") === true,
    sort: search.get("sort", "-created_at"),
    limit: search.getNumber("limit", 25),
    offset: search.getNumber("offset", 0),
  };
  const datasets = useQuery({ queryKey: queryKeys.datasets(query), queryFn: () => listDatasets(query), placeholderData: keepPreviousData });
  const schemas = useQuery({ queryKey: queryKeys.schemas, queryFn: listDatasetSchemas, staleTime: Infinity });

  const remove = useMutation({
    mutationFn: (dataset: Dataset) => deleteDataset(dataset.id),
    onSuccess: async () => {
      toast.success("Dataset deleted. Its file was removed; metadata is kept for traceability.");
      setToDelete(null);
      await queryClient.invalidateQueries({ queryKey: queryKeys.datasetsAll });
    },
  });

  const canDelete = (dataset: Dataset) => dataset.status !== "deleted" && (isAdmin(user) || dataset.owner?.id === user?.id);

  return (
    <>
      <PageHeader
        title="Datasets"
        description="Uploaded and imported network-flow datasets. Files are validated on upload; only validated datasets can be analysed."
        actions={
          <LinkButton to="/datasets/upload" variant="primary" icon="upload">
            Upload dataset
          </LinkButton>
        }
      />
      <Card flush>
        <div className="filter-bar">
          <TextField
            className="grow"
            label="Search"
            type="search"
            placeholder="Name or file name"
            value={searchText}
            onChange={(event) => {
              setSearchText(event.target.value);
              search.update({ q: event.target.value });
            }}
          />
          <SelectField
            label="Status"
            placeholder="Any status"
            options={STATUS_OPTIONS}
            value={search.get("status")}
            onChange={(event) => search.update({ status: event.target.value })}
          />
          <SelectField
            label="Schema"
            placeholder="Any schema"
            options={(schemas.data ?? []).map((schema) => ({ value: schema.schema_version, label: schema.display_name }))}
            value={search.get("schema")}
            onChange={(event) => search.update({ schema: event.target.value })}
          />
          <Checkbox
            label="Include deleted"
            checked={query.include_deleted}
            disabled={search.get("status") === "deleted"}
            onChange={(event) => search.update({ deleted: event.target.checked })}
          />
        </div>
        <DataTable<Dataset>
          caption="Datasets"
          rows={datasets.data?.items}
          loading={datasets.isFetching}
          error={datasets.error}
          onRetry={() => void datasets.refetch()}
          rowKey={(row) => row.id}
          sort={query.sort}
          onSortChange={(sort) => search.update({ sort })}
          onRowClick={setSelected}
          rowLabel={(row) => `Show details of dataset ${row.name}`}
          emptyTitle="No datasets found"
          emptyMessage="Upload a CICIDS2017 or UNSW-NB15 CSV file to get started, or adjust the filters."
          columns={[
            {
              key: "name",
              header: "Name",
              sortKey: "name",
              render: (row) => (
                <div className="stack-sm" style={{ gap: 0 }}>
                  <strong className="break">{row.name}</strong>
                  {row.original_filename ? <span className="small subtle break">{row.original_filename}</span> : null}
                </div>
              ),
            },
            { key: "schema", header: "Schema", render: (row) => row.schema_version ?? "—" },
            { key: "rows", header: "Rows", sortKey: "row_count", align: "right", render: (row) => formatNumber(row.row_count) },
            { key: "size", header: "Size", align: "right", render: (row) => formatBytes(row.size_bytes) },
            {
              key: "truth",
              header: "Labels",
              render: (row) => (row.has_ground_truth ? <Badge tone="info">Ground truth</Badge> : <span className="subtle">—</span>),
            },
            { key: "status", header: "Status", sortKey: "status", render: (row) => <StatusBadge status={row.status} /> },
            { key: "owner", header: "Owner", render: (row) => row.owner?.display_name ?? <Badge>System</Badge> },
            { key: "created", header: "Added", sortKey: "created_at", render: (row) => <span className="nowrap">{formatDateTime(row.created_at)}</span> },
            {
              key: "actions",
              header: <span className="sr-only">Actions</span>,
              align: "right",
              render: (row) => (
                <div className="row" style={{ justifyContent: "flex-end", flexWrap: "nowrap" }}>
                  {row.status === "validated" ? (
                    <Button size="sm" icon="play" onClick={() => navigate(`/analyses?new=1&dataset=${row.id}`)}>
                      Analyze
                    </Button>
                  ) : null}
                  {canDelete(row) ? (
                    <Button size="sm" variant="ghost" icon="trash" aria-label={`Delete dataset ${row.name}`} onClick={() => setToDelete(row)} />
                  ) : null}
                </div>
              ),
            },
          ]}
        />
        {datasets.data ? (
          <Pagination
            total={datasets.data.total}
            limit={query.limit}
            offset={query.offset}
            onChange={(offset) => search.update({ offset }, { resetPage: false })}
            onLimitChange={(limit) => search.update({ limit })}
          />
        ) : null}
      </Card>

      <Modal open={selected !== null} title={selected?.name ?? "Dataset"} onClose={() => setSelected(null)} wide>
        {selected ? <DatasetDetails dataset={selected} /> : null}
      </Modal>

      <ConfirmDialog
        open={toDelete !== null}
        title="Delete dataset?"
        message={
          <p>
            The stored file of <strong>{toDelete?.name}</strong> is deleted permanently. Its metadata and any analysis results remain for
            traceability.
          </p>
        }
        confirmLabel="Delete dataset"
        busy={remove.isPending}
        error={remove.error}
        onConfirm={() => toDelete && remove.mutate(toDelete)}
        onCancel={() => {
          setToDelete(null);
          remove.reset();
        }}
      />
    </>
  );
}

function DatasetDetails({ dataset }: { dataset: Dataset }) {
  return (
    <div className="stack">
      <KeyValueList
        items={[
          { label: "Status", value: <StatusBadge status={dataset.status} /> },
          { label: "Dataset ID", value: <code>{dataset.id}</code> },
          { label: "Original file", value: dataset.original_filename ?? "—" },
          { label: "Source", value: humanize(dataset.source_type) },
          { label: "Owner", value: dataset.owner ? `${dataset.owner.display_name} (${dataset.owner.email})` : "System (shared)" },
          { label: "Rows", value: formatNumber(dataset.row_count) },
          { label: "Size", value: formatBytes(dataset.size_bytes) },
          { label: "SHA-256", value: <code className="break">{dataset.sha256 ?? "—"}</code> },
          { label: "Added", value: formatDateTime(dataset.created_at) },
          ...(dataset.deleted_at ? [{ label: "Deleted", value: formatDateTime(dataset.deleted_at) }] : []),
        ]}
      />
      <hr />
      <h3>Validation report</h3>
      <ValidationReport report={dataset.validation_report} />
    </div>
  );
}
