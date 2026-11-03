import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import * as alerts from "./services/alerts";
import * as analyses from "./services/analyses";
import * as metrics from "./services/metrics";
import * as system from "./services/system";
import { makeSystemInfo, makeUser } from "./test/fixtures";
import { renderWithProviders } from "./test/render";

vi.mock("./services/system", () => ({ getSystemInfo: vi.fn(), getRiskPolicy: vi.fn(), getHealth: vi.fn() }));
vi.mock("./services/metrics", () => ({ getSummary: vi.fn(), getTrends: vi.fn(), getSummaryReport: vi.fn(), downloadSummaryReport: vi.fn() }));
vi.mock("./services/alerts", () => ({ listAlerts: vi.fn(), getAlert: vi.fn(), exportAlerts: vi.fn() }));
vi.mock("./services/analyses", () => ({ listJobs: vi.fn(), getJob: vi.fn() }));

const summary = {
  scope: "organization" as const,
  window: { date_from: null, date_to: null },
  total_records: 12000,
  malicious_count: 4800,
  benign_count: 7000,
  needs_review_count: 150,
  unclassified_count: 0,
  anomaly_count: 900,
  alert_count: 4733,
  open_alert_count: 4700,
  high_risk_count: 4733,
  completed_jobs: 1,
  approved_models: 1,
  active_datasets: 2,
  jobs_by_status: { completed: 1 },
  label_distribution: { Benign: 7000, DoS: 4800 },
  risk_band_distribution: { low: 7000, critical: 4733 },
};

describe("App routing and role-aware navigation", () => {
  beforeEach(() => {
    vi.mocked(system.getSystemInfo).mockResolvedValue(makeSystemInfo());
    vi.mocked(metrics.getSummary).mockResolvedValue(summary);
    vi.mocked(metrics.getTrends).mockResolvedValue({ bucket: "day", points: [] });
    vi.mocked(alerts.listAlerts).mockResolvedValue({ items: [], total: 0, limit: 6, offset: 0 });
    vi.mocked(analyses.listJobs).mockResolvedValue({ items: [], total: 0, limit: 6, offset: 0 });
  });

  it("sends anonymous visitors to the sign-in page", async () => {
    renderWithProviders(<App />, { route: "/datasets", auth: { status: "anonymous", user: null } });
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("hides analyst and admin navigation from viewers and blocks admin pages", async () => {
    renderWithProviders(<App />, { route: "/admin/users", auth: { user: makeUser({ role: "viewer" }) } });
    expect(await screen.findByText("You do not have access to this page")).toBeInTheDocument();
    const nav = screen.getByRole("complementary", { name: "Primary" });
    expect(within(nav).getByRole("link", { name: /Models/ })).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: /Datasets/ })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: /Users/ })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: /Audit logs/ })).not.toBeInTheDocument();
  });

  it("shows aggregate KPIs to viewers without per-alert data", async () => {
    renderWithProviders(<App />, { route: "/", auth: { user: makeUser({ role: "viewer" }) } });
    expect(await screen.findByText("Analysed records")).toBeInTheDocument();
    expect(screen.getByText("4,700")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Latest high-severity alerts" })).not.toBeInTheDocument();
    expect(alerts.listAlerts).not.toHaveBeenCalled();
  });

  it("offers administration links to administrators", async () => {
    renderWithProviders(<App />, { route: "/", auth: { user: makeUser({ role: "admin" }) } });
    const nav = screen.getByRole("complementary", { name: "Primary" });
    expect(within(nav).getByRole("link", { name: /Users/ })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /Audit logs/ })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Latest high-severity alerts" })).toBeInTheDocument();
  });
});
