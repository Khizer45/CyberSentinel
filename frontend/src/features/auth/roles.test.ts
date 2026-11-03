import { describe, expect, it } from "vitest";
import { canAnalyze, hasRole, isAdmin } from "./roles";

describe("roles", () => {
  it("grants analysis features to analysts and administrators only", () => {
    expect(canAnalyze({ role: "analyst" })).toBe(true);
    expect(canAnalyze({ role: "admin" })).toBe(true);
    expect(canAnalyze({ role: "viewer" })).toBe(false);
    expect(canAnalyze(null)).toBe(false);
  });

  it("restricts administration to administrators", () => {
    expect(isAdmin({ role: "admin" })).toBe(true);
    expect(isAdmin({ role: "analyst" })).toBe(false);
    expect(hasRole({ role: "viewer" }, ["viewer"])).toBe(true);
  });
});
