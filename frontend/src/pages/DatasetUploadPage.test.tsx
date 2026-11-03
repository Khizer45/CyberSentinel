import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../services/apiClient";
import * as datasets from "../services/datasets";
import * as system from "../services/system";
import { makeDataset, makeSchema, makeSystemInfo } from "../test/fixtures";
import { renderWithProviders } from "../test/render";
import { DatasetUploadPage } from "./DatasetUploadPage";

vi.mock("../services/datasets", () => ({ listDatasetSchemas: vi.fn(), uploadDataset: vi.fn() }));
vi.mock("../services/system", () => ({ getSystemInfo: vi.fn() }));

const CSV = "dur,proto,sbytes,label\n0.1,tcp,100,0\n0.2,udp,200,1\n";

describe("DatasetUploadPage", () => {
  beforeEach(() => {
    vi.mocked(datasets.listDatasetSchemas).mockResolvedValue([makeSchema()]);
    vi.mocked(system.getSystemInfo).mockResolvedValue(makeSystemInfo());
    vi.mocked(datasets.uploadDataset).mockReset();
  });

  it("rejects non-CSV files before anything is uploaded", async () => {
    const user = userEvent.setup({ applyAccept: false });
    renderWithProviders(<DatasetUploadPage />);
    await user.upload(screen.getByLabelText("CSV file"), new File(["not,a,csv"], "notes.txt", { type: "text/plain" }));
    expect(await screen.findByText("Only .csv files are accepted.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload and validate" })).toBeDisabled();
    expect(datasets.uploadDataset).not.toHaveBeenCalled();
  });

  it("previews locally, uploads, and shows the validation result", async () => {
    vi.mocked(datasets.uploadDataset).mockResolvedValue(makeDataset({ name: "flows", row_count: 2 }));
    const user = userEvent.setup();
    renderWithProviders(<DatasetUploadPage />);
    await user.upload(screen.getByLabelText("CSV file"), new File([CSV], "flows.csv", { type: "text/csv" }));
    expect(await screen.findByText("Local preview")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "proto" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/100% of UNSW-NB15 features/)).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Upload and validate" }));
    expect(await screen.findByText("Validation passed")).toBeInTheDocument();
    const [file, options] = vi.mocked(datasets.uploadDataset).mock.calls[0] ?? [];
    expect((file as File).name).toBe("flows.csv");
    expect(options).toEqual({ name: "flows", schemaVersion: "auto" });
  });

  it("explains a server-side rejection", async () => {
    vi.mocked(datasets.uploadDataset).mockRejectedValue(
      new ApiError(422, "dataset_rejected", "the columns do not match any supported dataset schema", {
        dataset_id: "x",
        reason: "feature_schema_error",
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<DatasetUploadPage />);
    await user.upload(screen.getByLabelText("CSV file"), new File([CSV], "flows.csv", { type: "text/csv" }));
    await screen.findByText("Local preview");
    await user.click(screen.getByRole("button", { name: "Upload and validate" }));
    expect(await screen.findByText("The server rejected the file")).toBeInTheDocument();
    expect(screen.getByText("the columns do not match any supported dataset schema")).toBeInTheDocument();
    expect(screen.getByText(/feature_schema_error/)).toBeInTheDocument();
  });
});
