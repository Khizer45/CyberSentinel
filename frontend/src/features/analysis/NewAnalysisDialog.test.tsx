import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as analyses from "../../services/analyses";
import * as datasets from "../../services/datasets";
import * as models from "../../services/models";
import { makeDataset, makeJob, makeModel } from "../../test/fixtures";
import { renderWithProviders } from "../../test/render";
import { NewAnalysisDialog } from "./NewAnalysisDialog";

vi.mock("../../services/analyses", () => ({ createJob: vi.fn() }));
vi.mock("../../services/datasets", () => ({ listDatasets: vi.fn() }));
vi.mock("../../services/models", () => ({ listModels: vi.fn() }));

const unswDataset = makeDataset();
const cicDataset = makeDataset({ id: "20000000-0000-4000-8000-000000000002", name: "cic-flows", schema_version: "cicids2017-v1" });
const unswModel = makeModel();
const cicModel = makeModel({
  id: "10000000-0000-4000-8000-000000000002",
  model_name: "cicids2017-xgboost-multiclass",
  feature_schema_version: "cicids2017-v1",
  dataset_family: "cicids2017",
  supported_modes: ["classification"],
});

describe("NewAnalysisDialog", () => {
  beforeEach(() => {
    vi.mocked(datasets.listDatasets).mockResolvedValue({ items: [unswDataset, cicDataset], total: 2, limit: 100, offset: 0 });
    vi.mocked(models.listModels).mockResolvedValue([unswModel, cicModel]);
    vi.mocked(analyses.createJob).mockResolvedValue(makeJob({ status: "queued" }));
  });

  it("offers only approved models that match the dataset's feature schema", async () => {
    renderWithProviders(<NewAnalysisDialog open initialDatasetId={unswDataset.id} onClose={vi.fn()} onCreated={vi.fn()} />);
    const modelSelect = await screen.findByLabelText("Model");
    await waitFor(() => expect(within(modelSelect).getAllByRole("option")).toHaveLength(2));
    expect(within(modelSelect).getByRole("option", { name: /unsw-nb15-random-forest-multiclass/ })).toBeInTheDocument();
    expect(within(modelSelect).queryByRole("option", { name: /cicids2017/ })).not.toBeInTheDocument();
    expect(models.listModels).toHaveBeenCalledWith({ status: ["approved"] });
  });

  it("limits modes to what the model supports and submits the job", async () => {
    const onCreated = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<NewAnalysisDialog open initialDatasetId={cicDataset.id} onClose={vi.fn()} onCreated={onCreated} />);
    const modelSelect = await screen.findByLabelText("Model");
    await waitFor(() => expect(within(modelSelect).getAllByRole("option")).toHaveLength(2));
    await user.selectOptions(modelSelect, cicModel.id);
    const modeSelect = screen.getByLabelText("Analysis mode");
    expect(within(modeSelect).getAllByRole("option").map((option) => option.getAttribute("value"))).toEqual(["classification"]);
    await user.click(screen.getByRole("button", { name: "Start analysis" }));
    await waitFor(() =>
      expect(analyses.createJob).toHaveBeenCalledWith({ dataset_id: cicDataset.id, model_version_id: cicModel.id, requested_mode: "classification" }),
    );
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
  });
});
