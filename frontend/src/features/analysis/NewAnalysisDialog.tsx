import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, LinkButton } from "../../components/Button";
import { SelectField } from "../../components/FormFields";
import { Modal } from "../../components/Modal";
import { Callout, ErrorCallout } from "../../components/States";
import { createJob } from "../../services/analyses";
import { listDatasets } from "../../services/datasets";
import { listModels } from "../../services/models";
import { queryKeys } from "../../services/queryKeys";
import type { AnalysisJob, AnalysisMode } from "../../types/api";
import { formatNumber } from "../../utils/format";
import { MODE_HINTS, MODE_LABELS, preferredMode } from "./modes";

interface NewAnalysisDialogProps {
  open: boolean;
  initialDatasetId?: string;
  onClose: () => void;
  onCreated: (job: AnalysisJob) => void;
}

export function NewAnalysisDialog(props: NewAnalysisDialogProps) {
  return props.open ? <NewAnalysisForm {...props} /> : null;
}

function NewAnalysisForm({ initialDatasetId, onClose, onCreated }: NewAnalysisDialogProps) {
  const queryClient = useQueryClient();
  const datasetQuery = { status: "validated", sort: "-created_at", limit: 100 };
  const datasets = useQuery({ queryKey: queryKeys.datasets(datasetQuery), queryFn: () => listDatasets(datasetQuery) });
  const models = useQuery({ queryKey: queryKeys.models({ status: ["approved"] }), queryFn: () => listModels({ status: ["approved"] }) });
  const [datasetId, setDatasetId] = useState(initialDatasetId ?? "");
  const [modelId, setModelId] = useState("");
  const [mode, setMode] = useState<AnalysisMode | "">("");

  const dataset = datasets.data?.items.find((item) => item.id === datasetId);
  const compatibleModels = useMemo(
    () => (models.data ?? []).filter((model) => !dataset || model.feature_schema_version === dataset.schema_version),
    [models.data, dataset],
  );
  const model = compatibleModels.find((item) => item.id === modelId);
  const effectiveMode: AnalysisMode | "" = model ? (mode && model.supported_modes.includes(mode) ? mode : preferredMode(model.supported_modes)) : "";

  const create = useMutation({
    mutationFn: () => createJob({ dataset_id: datasetId, model_version_id: modelId, requested_mode: effectiveMode as AnalysisMode }),
    onSuccess: async (job) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.jobsAll });
      onCreated(job);
    },
  });

  const noModels = models.isSuccess && (models.data?.length ?? 0) === 0;
  return (
    <Modal
      open
      title="New analysis job"
      onClose={create.isPending ? () => undefined : onClose}
      footer={
        <>
          <Button onClick={onClose} disabled={create.isPending}>
            Cancel
          </Button>
          <Button variant="primary" icon="play" loading={create.isPending} disabled={!dataset || !model || !effectiveMode} onClick={() => create.mutate()}>
            Start analysis
          </Button>
        </>
      }
    >
      <p className="muted">
        Jobs run in the background on the server. Inference uses the selected approved model exactly as packaged — models are never trained
        or replaced automatically.
      </p>
      <SelectField
        label="Dataset"
        placeholder={datasets.isPending ? "Loading datasets…" : "Select a validated dataset"}
        value={datasetId}
        onChange={(event) => {
          setDatasetId(event.target.value);
          setModelId("");
          setMode("");
        }}
        options={(datasets.data?.items ?? []).map((item) => ({
          value: item.id,
          label: `${item.name} · ${item.schema_version ?? "?"} · ${formatNumber(item.row_count)} rows`,
        }))}
        hint={datasets.data && datasets.data.total > datasets.data.items.length ? "Showing the 100 most recent validated datasets." : undefined}
      />
      {noModels ? (
        <Callout tone="warning" title="No approved models">
          An administrator must register and approve a model bundle before analyses can run (see the Model Artifact Integration Guide).
        </Callout>
      ) : (
        <SelectField
          label="Model"
          placeholder={!dataset ? "Select a dataset first" : compatibleModels.length ? "Select an approved model" : "No approved model for this schema"}
          value={modelId}
          disabled={!dataset || compatibleModels.length === 0}
          onChange={(event) => {
            setModelId(event.target.value);
            setMode("");
          }}
          options={compatibleModels.map((item) => ({
            value: item.id,
            label: `${item.model_name} ${item.version} (${item.model_type.replace("_", " ")})`,
          }))}
          hint={dataset ? `Only models trained on the ${dataset.schema_version} feature schema are listed.` : undefined}
        />
      )}
      {model ? (
        <SelectField
          label="Analysis mode"
          value={effectiveMode}
          onChange={(event) => setMode(event.target.value as AnalysisMode)}
          options={model.supported_modes.map((value) => ({ value, label: MODE_LABELS[value as AnalysisMode] ?? value }))}
          hint={effectiveMode ? MODE_HINTS[effectiveMode] : undefined}
        />
      ) : null}
      {model && !model.probability_calibrated ? (
        <Callout tone="info">This model's scores are not calibrated, so results show classifier scores rather than probabilities.</Callout>
      ) : null}
      <ErrorCallout error={create.error} />
      {create.error && (create.error as { code?: string }).code === "model_unavailable" ? (
        <p className="small">
          <LinkButton to="/models" size="sm">
            Open model information
          </LinkButton>
        </p>
      ) : null}
    </Modal>
  );
}
