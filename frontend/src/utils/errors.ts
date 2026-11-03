/** Turn API errors into user-facing text. Messages come from the API's error envelope, never from stack traces. */
import { ApiError, toApiError } from "../services/apiClient";

const FRIENDLY: Record<string, string> = {
  network_error: "The CyberSentinel API cannot be reached. Check that the backend is running and try again.",
  timeout: "The request timed out. Try again, or narrow the request.",
  model_unavailable:
    "The selected model is unavailable: its artifacts are missing, incompatible or failed verification. An administrator must fix the model registry — no substitute model is used.",
  session_expired: "Your session has expired. Please sign in again.",
  permission_denied: "You do not have permission to perform this action.",
  origin_not_allowed: "This site's address is not an allowed origin for the API (check CORS_ORIGINS in the backend configuration).",
};

export function errorMessage(error: unknown): string {
  const apiError = toApiError(error);
  if (apiError.code === "rate_limited") {
    const seconds = retryAfterSeconds(apiError);
    return seconds ? `Too many requests. Try again in ${seconds} seconds.` : "Too many requests. Try again shortly.";
  }
  return FRIENDLY[apiError.code] ?? apiError.message;
}

export function retryAfterSeconds(error: ApiError): number | null {
  const details = error.details as { retry_after_seconds?: unknown } | null;
  return typeof details?.retry_after_seconds === "number" ? details.retry_after_seconds : null;
}

/**
 * Field-level messages keyed by the last path segment of the field (``body.email`` → ``email``).
 * Supports the API's ``validation_error`` details and the ``weak_password`` policy details.
 */
export function fieldErrors(error: unknown): Record<string, string> {
  const apiError = toApiError(error);
  const result: Record<string, string> = {};
  if (apiError.code === "validation_error" && Array.isArray(apiError.details)) {
    for (const item of apiError.details as { field?: unknown; message?: unknown }[]) {
      if (typeof item?.field !== "string" || typeof item.message !== "string") continue;
      const key = item.field.split(".").pop() ?? item.field;
      result[key] ??= item.message.replace(/^Value error, /, "");
    }
  }
  if (apiError.code === "weak_password") {
    const details = apiError.details as { password?: unknown } | null;
    if (Array.isArray(details?.password)) {
      const text = `Password ${(details.password as string[]).join("; ")}.`;
      result.password = text;
      result.new_password = text;
    }
  }
  return result;
}

/** Row-level problems reported by quick analysis / dataset validation (``details.errors``). */
export function detailErrors(error: unknown): { record?: number; feature?: string; error?: string }[] {
  const details = toApiError(error).details as { errors?: unknown } | null;
  return Array.isArray(details?.errors) ? (details.errors as { record?: number; feature?: string; error?: string }[]) : [];
}

export function requestIdOf(error: unknown): string | null {
  return toApiError(error).requestId;
}
