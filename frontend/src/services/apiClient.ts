/**
 * Single Axios instance for the CyberSentinel API.
 *
 * - The access token lives only in memory (never in localStorage/sessionStorage); the refresh token is an
 *   HttpOnly cookie scoped to /api/v1/auth that JavaScript cannot read.
 * - On a 401 the client performs one shared ("single-flight") refresh and retries the original request once.
 * - Every failure is normalized to {@link ApiError}, carrying the API's error code, message and request ID.
 *   Server stack traces are never part of the API contract, so nothing sensitive can reach the UI.
 */
import axios, { AxiosHeaders, type AxiosError, type InternalAxiosRequestConfig } from "axios";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  readonly requestId: string | null;

  constructor(status: number, code: string, message: string, details: unknown = null, requestId: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

interface ErrorEnvelope {
  error?: { code?: string; message?: string; details?: unknown; request_id?: string | null };
}

function headerValue(headers: unknown, name: string): string | null {
  if (headers instanceof AxiosHeaders) {
    const value = headers.get(name);
    return typeof value === "string" ? value : null;
  }
  if (headers && typeof headers === "object") {
    const value = (headers as Record<string, unknown>)[name.toLowerCase()];
    return typeof value === "string" ? value : null;
  }
  return null;
}

/** Convert anything thrown by Axios (or our own code) into an {@link ApiError}. */
export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<ErrorEnvelope>;
    if (axiosError.code === "ECONNABORTED" || axiosError.code === "ETIMEDOUT") {
      return new ApiError(0, "timeout", "The request timed out. Try again or reduce the amount of data requested.");
    }
    if (!axiosError.response) {
      return new ApiError(0, "network_error", "The CyberSentinel API cannot be reached. Check that the backend is running.");
    }
    const { status, data, headers } = axiosError.response;
    const envelope = data && typeof data === "object" && "error" in data ? data.error : undefined;
    return new ApiError(
      status,
      envelope?.code ?? `http_${status}`,
      envelope?.message ?? "The request could not be completed.",
      envelope?.details ?? null,
      envelope?.request_id ?? headerValue(headers, "x-request-id"),
    );
  }
  return new ApiError(0, "client_error", error instanceof Error ? error.message : "Unexpected client error.");
}

let accessToken: string | null = null;
let refreshHandler: (() => Promise<string | null>) | null = null;
let refreshInFlight: Promise<string | null> | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

/** Registered by the auth provider: performs the cookie-based refresh and resolves to the new access token. */
export function setRefreshHandler(handler: (() => Promise<string | null>) | null): void {
  refreshHandler = handler;
}

/** Run the registered refresh at most once at a time; concurrent callers share the same promise. */
export function refreshAccessToken(): Promise<string | null> {
  if (!refreshHandler) return Promise.resolve(null);
  refreshInFlight ??= refreshHandler().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

export const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  timeout: 60_000,
});

api.interceptors.request.use((config) => {
  if (accessToken && !config.headers.has("Authorization")) {
    config.headers.set("Authorization", `Bearer ${accessToken}`);
  }
  return config;
});

type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean };
const NO_REFRESH_PATHS = ["/auth/login", "/auth/refresh", "/auth/logout"];

api.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (axios.isAxiosError(error)) {
      const response = error.response;
      // Error bodies of blob downloads (exports) arrive as Blobs: decode the JSON envelope for a useful message.
      if (response && typeof Blob !== "undefined" && response.data instanceof Blob) {
        try {
          response.data = JSON.parse(await response.data.text()) as unknown;
        } catch {
          response.data = null;
        }
      }
      const config = error.config as RetriableConfig | undefined;
      const url = config?.url ?? "";
      if (response?.status === 401 && config && !config._retried && !NO_REFRESH_PATHS.some((path) => url.includes(path))) {
        config._retried = true;
        const token = await refreshAccessToken();
        if (token) {
          const headers = AxiosHeaders.from(config.headers);
          headers.set("Authorization", `Bearer ${token}`);
          config.headers = headers;
          return api.request(config);
        }
      }
    }
    return Promise.reject(toApiError(error));
  },
);

/** Build query parameters: empty values are dropped; arrays become repeated keys (?a=1&a=2) as FastAPI expects. */
export function params(values: Record<string, unknown>): URLSearchParams {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      value.filter((item) => item !== undefined && item !== null && item !== "").forEach((item) => search.append(key, String(item)));
    } else {
      search.append(key, String(value));
    }
  }
  return search;
}

/** Extract the file name from a Content-Disposition header, falling back to ``fallback``. */
export function filenameFromDisposition(header: string | null | undefined, fallback: string): string {
  if (!header) return fallback;
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1]);
    } catch {
      return fallback;
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain?.[1] ?? fallback;
}

export interface DownloadedFile {
  blob: Blob;
  filename: string;
  /** True when the server capped the export at EXPORT_MAX_ROWS (header ``X-Export-Truncated``). */
  truncated: boolean;
}

/** GET a file download (CSV/JSON export) as a Blob together with its server-provided name. */
export async function downloadFile(url: string, query: URLSearchParams, fallbackName: string): Promise<DownloadedFile> {
  const response = await api.get<Blob>(url, { params: query, responseType: "blob", timeout: 10 * 60_000 });
  return {
    blob: response.data,
    filename: filenameFromDisposition(headerValue(response.headers, "content-disposition"), fallbackName),
    truncated: headerValue(response.headers, "x-export-truncated") === "true",
  };
}
