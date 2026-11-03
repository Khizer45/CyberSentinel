import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "../test/render";
import { Chart, countsToSeries } from "./Chart";

describe("Chart", () => {
  it("shows an empty state instead of an empty chart", () => {
    renderWithProviders(<Chart title="Empty" kind="bar" series={[{ name: "Records", x: ["a"], y: [0] }]} />);
    expect(screen.getByText("No data")).toBeInTheDocument();
  });

  it("always provides an accessible data table", () => {
    renderWithProviders(<Chart title="Labels" kind="hbar" series={[countsToSeries("Records", { DoS: 42, Benign: 7 })]} />);
    expect(screen.getByRole("img", { name: "Labels" })).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: "DoS" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "42" })).toBeInTheDocument();
  });

  it("orders categories when an order is given", () => {
    const series = countsToSeries("Records", { critical: 1, low: 5, high: 2 }, ["low", "medium", "high", "critical"]);
    expect(series.x).toEqual(["low", "high", "critical"]);
  });
});
