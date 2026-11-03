import { describe, expect, it } from "vitest";
import { experimentSeries } from "./ExperimentsPanel";

describe("experimentSeries", () => {
  it("averages repeated runs per label budget and method", () => {
    const result = experimentSeries({
      experiment_type: "semi_supervised_label_budget",
      rows: [
        { method: "label_spreading", label_budget: 0.05, seed: 1, macro_f1: 0.6 },
        { method: "label_spreading", label_budget: 0.05, seed: 2, macro_f1: 0.8 },
        { method: "label_spreading", label_budget: 0.01, seed: 1, macro_f1: 0.5 },
        { method: "supervised_random_forest", label_budget: 0.05, seed: 1, macro_f1: 0.9 },
      ],
    });
    expect(result?.kind).toBe("line");
    const spreading = result?.series.find((series) => series.name === "label_spreading");
    expect(spreading?.x).toEqual([0.01, 0.05]);
    expect(spreading?.y[0]).toBeCloseTo(0.5);
    expect(spreading?.y[1]).toBeCloseTo(0.7);
  });

  it("returns null when the recorded columns are not recognised", () => {
    expect(experimentSeries({ experiment_type: "supervised_comparison", rows: [{ something: 1 }] })).toBeNull();
    expect(experimentSeries({ experiment_type: "unknown" as never, rows: [{ model: "x", macro_f1: 1 }] })).toBeNull();
  });
});
