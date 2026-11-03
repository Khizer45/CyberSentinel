import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as alerts from "../services/alerts";
import * as analyses from "../services/analyses";
import { makePredictionDetail, makeUser } from "../test/fixtures";
import { renderWithProviders } from "../test/render";
import { AlertDetailsPage } from "./AlertDetailsPage";

vi.mock("../services/alerts", () => ({ getAlert: vi.fn() }));
vi.mock("../services/analyses", () => ({ getPrediction: vi.fn(), addReview: vi.fn() }));

const detail = makePredictionDetail();
const route = `/alerts/${detail.id}`;

describe("AlertDetailsPage", () => {
  beforeEach(() => {
    vi.mocked(alerts.getAlert).mockResolvedValue(detail);
    vi.mocked(analyses.addReview).mockReset();
  });

  it("never shows a probability for an uncalibrated model", async () => {
    renderWithProviders(<AlertDetailsPage kind="alert" />, { route, path: "/alerts/:alertId" });
    expect(await screen.findByText("Model not calibrated")).toBeInTheDocument();
    expect(screen.getByText("Uncalibrated · 1 − benign score")).toBeInTheDocument();
    expect(screen.getAllByText("n/a").length).toBeGreaterThan(0);
  });

  it("renders the explanation, reason codes and risk breakdown", async () => {
    renderWithProviders(<AlertDetailsPage kind="alert" />, { route, path: "/alerts/:alertId" });
    expect(await screen.findByText("Tree-path attribution (Saabas)")).toBeInTheDocument();
    expect(screen.getByText(/increased the model's score for 'DoS'/)).toBeInTheDocument();
    expect(screen.getByText("Risk score breakdown")).toBeInTheDocument();
    expect(screen.getByText("Attributions describe model behaviour, not causality.")).toBeInTheDocument();
  });

  it("records an analyst review", async () => {
    vi.mocked(analyses.addReview).mockResolvedValue({
      id: "r1",
      prediction_id: detail.id,
      disposition: "true_positive",
      notes: "Confirmed with firewall logs",
      reviewer: { id: makeUser().id, email: makeUser().email, display_name: makeUser().display_name },
      created_at: "2026-11-01T11:00:00Z",
    });
    const user = userEvent.setup();
    renderWithProviders(<AlertDetailsPage kind="alert" />, { route, path: "/alerts/:alertId" });
    await screen.findByText("Analyst review");
    await user.selectOptions(screen.getByLabelText("Disposition"), "true_positive");
    await user.type(screen.getByLabelText("Notes"), "Confirmed with firewall logs");
    await user.click(screen.getByRole("button", { name: "Record review" }));
    await waitFor(() =>
      expect(analyses.addReview).toHaveBeenCalledWith(detail.id, { disposition: "true_positive", notes: "Confirmed with firewall logs" }),
    );
  });

  it("does not offer reviews to viewers", async () => {
    renderWithProviders(<AlertDetailsPage kind="alert" />, { route, path: "/alerts/:alertId", auth: { user: makeUser({ role: "viewer" }) } });
    await screen.findByText("Analyst review");
    expect(screen.queryByRole("button", { name: "Record review" })).not.toBeInTheDocument();
  });
});
