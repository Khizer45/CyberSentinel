import { useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { StatusBadge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ProgressBar } from "../components/DataDisplay";
import { DataTable } from "../components/DataTable";
import { SelectField } from "../components/FormFields";
import { PageHeader } from "../components/PageHeader";
import { Pagination } from "../components/Pagination";
import { TabPanel, Tabs } from "../components/Tabs";
import { useToast } from "../components/Toast";
import { MODE_LABELS } from "../features/analysis/modes";
import { NewAnalysisDialog } from "../features/analysis/NewAnalysisDialog";
import { QuickAnalysisPanel } from "../features/analysis/QuickAnalysisPanel";
import { useSearchState } from "../hooks/useSearchState";
import { cancelJob, listJobs } from "../services/analyses";
import { queryKeys } from "../services/queryKeys";
import { ACTIVE_JOB_STATUSES, type AnalysisJob } from "../types/api";
import { formatDateTime, formatNumber, humanize } from "../utils/format";

const STATUS_OPTIONS = ["queued", "validating", "running", "completed", "failed", "cancelled"].map((value) => ({ value, label: humanize(value) }));
const TABS = [
  { id: "jobs", label: "Analysis jobs" },
  { id: "quick", label: "Quick analysis" },
];

export function isActive(job: Pick<AnalysisJob, "status">): boolean {
  return ACTIVE_JOB_STATUSES.includes(job.status);
}

export function AnalysisJobsPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const search = useSearchState();
  const tab = search.get("tab") === "quick" ? "quick" : "jobs";
  const [toCancel, setToCancel] = useState<AnalysisJob | null>(null);

  const query = {
    status: search.get("status") || undefined,
    dataset_id: search.get("dataset_id") || undefined,
    sort: search.get("sort", "-created_at"),
    limit: search.getNumber("limit", 25),
    offset: search.getNumber("offset", 0),
  };
  const jobs = useQuery({
    queryKey: queryKeys.jobs(query),
    queryFn: () => listJobs(query),
    placeholderData: keepPreviousData,
    enabled: tab === "jobs",
    // Poll while any visible job is still queued or running.
    refetchInterval: (state) => (state.state.data?.items.some(isActive) ? 3000 : false),
  });

  const cancel = useMutation({
    mutationFn: (job: AnalysisJob) => cancelJob(job.id),
    onSuccess: async () => {
      toast.info("Cancellation requested. Partial results are discarded.");
      setToCancel(null);
      await queryClient.invalidateQueries({ queryKey: queryKeys.jobsAll });
    },
  });

  return (
    <>
      <PageHeader
        title="Analysis"
        description="Run approved models over validated datasets. Jobs are processed asynchronously; results appear when a job completes."
        actions={
          <Button variant="primary" icon="play" onClick={() => search.update({ new: "1", tab: null })}>
            New analysis
          </Button>
        }
      />
      <Tabs label="Analysis views" tabs={TABS} active={tab} onChange={(id) => search.update({ tab: id === "jobs" ? null : id })} />
      <TabPanel id={tab}>
        {tab === "quick" ? (
          <QuickAnalysisPanel />
        ) : (
          <Card flush>
            <div className="filter-bar">
              <SelectField
                label="Status"
                placeholder="Any status"
                options={STATUS_OPTIONS}
                value={search.get("status")}
                onChange={(event) => search.update({ status: event.target.value })}
              />
              {query.dataset_id ? (
                <Button size="sm" variant="ghost" icon="close" onClick={() => search.update({ dataset_id: null })}>
                  Clear dataset filter
                </Button>
              ) : null}
            </div>
            <DataTable<AnalysisJob>
              caption="Analysis jobs"
              rows={jobs.data?.items}
              loading={jobs.isPending}
              error={jobs.error}
              onRetry={() => void jobs.refetch()}
              rowKey={(row) => row.id}
              sort={query.sort}
              onSortChange={(sort) => search.update({ sort })}
              onRowClick={(row) => navigate(`/analyses/${row.id}`)}
              rowLabel={(row) => `Open analysis of ${row.dataset.name}`}
              emptyTitle="No analysis jobs"
              emptyMessage="Start a new analysis on a validated dataset."
              columns={[
                {
                  key: "dataset",
                  header: "Dataset",
                  render: (row) => (
                    <div className="stack-sm" style={{ gap: 0 }}>
                      <strong className="break">{row.dataset.name}</strong>
                      <span className="small subtle">{row.dataset.schema_version}</span>
                    </div>
                  ),
                },
                {
                  key: "model",
                  header: "Model",
                  render: (row) => (
                    <span className="break">
                      {row.model_version.model_name} <span className="subtle">{row.model_version.version}</span>
                    </span>
                  ),
                },
                { key: "mode", header: "Mode", render: (row) => MODE_LABELS[row.requested_mode].split(" (")[0] },
                { key: "status", header: "Status", sortKey: "status", render: (row) => <StatusBadge status={row.status} /> },
                {
                  key: "progress",
                  header: "Progress",
                  render: (row) =>
                    isActive(row) ? (
                      <div style={{ minWidth: 120 }}>
                        <ProgressBar value={row.progress} label={`Progress of analysis on ${row.dataset.name}`} />
                        <span className="small subtle">
                          {formatNumber(row.processed_rows)} / {formatNumber(row.input_rows)}
                        </span>
                      </div>
                    ) : (
                      <span className="small">{formatNumber(row.processed_rows)} rows</span>
                    ),
                },
                { key: "submitter", header: "Submitted by", render: (row) => row.submitter.display_name },
                { key: "created", header: "Submitted", sortKey: "created_at", render: (row) => <span className="nowrap">{formatDateTime(row.created_at)}</span> },
                {
                  key: "actions",
                  header: <span className="sr-only">Actions</span>,
                  align: "right",
                  render: (row) =>
                    isActive(row) ? (
                      <Button size="sm" variant="ghost" icon="stop" onClick={() => setToCancel(row)}>
                        Cancel
                      </Button>
                    ) : null,
                },
              ]}
            />
            {jobs.data ? (
              <Pagination
                total={jobs.data.total}
                limit={query.limit}
                offset={query.offset}
                onChange={(offset) => search.update({ offset }, { resetPage: false })}
                onLimitChange={(limit) => search.update({ limit })}
              />
            ) : null}
          </Card>
        )}
      </TabPanel>

      <NewAnalysisDialog
        open={search.get("new") === "1"}
        initialDatasetId={search.get("dataset") || undefined}
        onClose={() => search.update({ new: null, dataset: null }, { resetPage: false })}
        onCreated={(job) => {
          toast.success("Analysis job queued.");
          navigate(`/analyses/${job.id}`);
        }}
      />
      <ConfirmDialog
        open={toCancel !== null}
        title="Cancel analysis?"
        message={<p>The job stops at the next checkpoint and any partial predictions are deleted (results are all-or-nothing).</p>}
        confirmLabel="Cancel job"
        busy={cancel.isPending}
        error={cancel.error}
        onConfirm={() => toCancel && cancel.mutate(toCancel)}
        onCancel={() => {
          setToCancel(null);
          cancel.reset();
        }}
      />
    </>
  );
}
