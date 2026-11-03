import { describe, expect, it } from "vitest";
import { testMetric } from "./AnalyticsPage";

describe("testMetric", () => {
  it("reads notebook test metrics stored under measured.test", () => {
    expect(testMetric({ measured: { test: { macro_f1: 0.91 } } }, "macro_f1")).toBe(0.91);
  });

  it("accepts the manifest shape directly and reports missing metrics as undefined", () => {
    expect(testMetric({ test: { accuracy: 0.98 } }, "accuracy")).toBe(0.98);
    expect(testMetric({ measured: { note: "test fixture" } }, "macro_f1")).toBeUndefined();
    expect(testMetric(null, "macro_f1")).toBeUndefined();
  });
});
