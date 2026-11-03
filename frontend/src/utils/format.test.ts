import { describe, expect, it } from "vitest";
import { dayBoundary, EMPTY, formatBytes, formatNumber, formatPercent, formatRisk, humanize, shiftTimeLabel, trendBucketLabel } from "./format";

describe("format helpers", () => {
  it("renders missing values as an em dash, never as zero", () => {
    expect(formatNumber(null)).toBe(EMPTY);
    expect(formatPercent(undefined)).toBe(EMPTY);
    expect(formatRisk(Number.NaN)).toBe(EMPTY);
  });

  it("formats risk scores with one decimal", () => {
    expect(formatRisk(89.432)).toMatch(/89[.,]4/);
  });

  it("formats sizes and identifiers", () => {
    expect(formatBytes(1536)).toMatch(/1[.,]5 KB/);
    expect(humanize("needs_investigation")).toBe("Needs investigation");
  });

  it("turns a date input into local day boundaries", () => {
    const start = new Date(dayBoundary("2026-03-05") as string);
    const end = new Date(dayBoundary("2026-03-05", true) as string);
    expect(start.getHours()).toBe(0);
    expect(end.getHours()).toBe(23);
    expect(end.getTime() - start.getTime()).toBe(24 * 3600_000 - 1);
    expect(dayBoundary("not-a-date")).toBeUndefined();
  });
});

describe("trend buckets", () => {
  it("keeps the UTC calendar day for daily buckets in any time zone", () => {
    expect(trendBucketLabel("2026-11-03 00:00:00+00:00", "day")).toBe("2026-11-03");
    expect(trendBucketLabel("2026-11-03", "day")).toBe("2026-11-03");
  });

  it("shows hourly buckets in local time", () => {
    const local = new Date("2026-11-03T14:00:00+00:00");
    const expected = `${local.getFullYear()}-${String(local.getMonth() + 1).padStart(2, "0")}-${String(local.getDate()).padStart(2, "0")} ${String(local.getHours()).padStart(2, "0")}:00`;
    expect(trendBucketLabel("2026-11-03 14:00:00+00:00", "hour")).toBe(expected);
  });

  it("leaves unparseable buckets unchanged and shifts labels across day boundaries", () => {
    expect(trendBucketLabel("not a date", "day")).toBe("not a date");
    expect(shiftTimeLabel("2026-11-03", 86_400_000)).toBe("2026-11-04 00:00");
    expect(shiftTimeLabel("2026-11-03 00:00", -3_600_000)).toBe("2026-11-02 23:00");
  });
});
