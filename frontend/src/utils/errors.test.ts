import { describe, expect, it } from "vitest";
import { ApiError } from "../services/apiClient";
import { detailErrors, errorMessage, fieldErrors } from "./errors";

describe("errors", () => {
  it("maps validation details to field names", () => {
    const error = new ApiError(400, "validation_error", "The request failed validation.", [
      { field: "body.email", message: "Value error, value is not a valid email address", type: "value_error" },
    ]);
    expect(fieldErrors(error)).toEqual({ email: "value is not a valid email address" });
  });

  it("maps password policy failures to password fields", () => {
    const error = new ApiError(422, "weak_password", "The new password does not meet the password policy.", {
      password: ["must be at least 12 characters long"],
    });
    expect(fieldErrors(error).new_password).toBe("Password must be at least 12 characters long.");
  });

  it("explains rate limiting and unavailable models", () => {
    expect(errorMessage(new ApiError(429, "rate_limited", "Too many requests.", { retry_after_seconds: 30 }))).toContain("30 seconds");
    expect(errorMessage(new ApiError(503, "model_unavailable", "x"))).toContain("no substitute model is used");
  });

  it("extracts record-level problems", () => {
    const error = new ApiError(422, "feature_schema_error", "x", { errors: [{ record: 0, feature: "dur", error: "must be a number" }] });
    expect(detailErrors(error)).toEqual([{ record: 0, feature: "dur", error: "must be a number" }]);
  });
});
