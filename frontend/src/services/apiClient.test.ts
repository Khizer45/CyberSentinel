import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, filenameFromDisposition, params, setAccessToken, setRefreshHandler, toApiError } from "./apiClient";

function response(config: InternalAxiosRequestConfig, status: number, data: unknown) {
  return { data, status, statusText: String(status), headers: new AxiosHeaders({ "x-request-id": "req-1" }), config };
}

function reject(config: InternalAxiosRequestConfig, status: number, data: unknown): Promise<never> {
  return Promise.reject(new AxiosError(`HTTP ${status}`, "ERR_BAD_RESPONSE", config, null, response(config, status, data)));
}

describe("toApiError", () => {
  it("maps the API error envelope", () => {
    const config = { headers: new AxiosHeaders() } as InternalAxiosRequestConfig;
    const error = new AxiosError("bad", "ERR_BAD_REQUEST", config, null, response(config, 409, {
      error: { code: "duplicate_dataset", message: "An identical dataset has already been uploaded.", details: { dataset_id: "x" }, request_id: "abc" },
    }));
    const apiError = toApiError(error);
    expect(apiError).toBeInstanceOf(ApiError);
    expect(apiError.status).toBe(409);
    expect(apiError.code).toBe("duplicate_dataset");
    expect(apiError.message).toBe("An identical dataset has already been uploaded.");
    expect(apiError.details).toEqual({ dataset_id: "x" });
    expect(apiError.requestId).toBe("abc");
  });

  it("reports an unreachable API as a network error", () => {
    const apiError = toApiError(new AxiosError("Network Error", "ERR_NETWORK"));
    expect(apiError.code).toBe("network_error");
    expect(apiError.status).toBe(0);
  });

  it("falls back to the HTTP status for non-envelope bodies", () => {
    const config = { headers: new AxiosHeaders() } as InternalAxiosRequestConfig;
    const apiError = toApiError(new AxiosError("x", "ERR_BAD_RESPONSE", config, null, response(config, 502, "<html>")));
    expect(apiError.code).toBe("http_502");
    expect(apiError.requestId).toBe("req-1");
  });
});

describe("params", () => {
  it("drops empty values and repeats array keys", () => {
    const search = params({ status: ["open", "closed"], q: "", limit: 25, missing: undefined, nothing: null, flag: false });
    expect(search.getAll("status")).toEqual(["open", "closed"]);
    expect(search.has("q")).toBe(false);
    expect(search.get("limit")).toBe("25");
    expect(search.get("flag")).toBe("false");
    expect(search.has("missing")).toBe(false);
  });
});

describe("filenameFromDisposition", () => {
  it("reads quoted and RFC 5987 file names", () => {
    expect(filenameFromDisposition('attachment; filename="cybersentinel-alerts.csv"', "x")).toBe("cybersentinel-alerts.csv");
    expect(filenameFromDisposition("attachment; filename*=UTF-8''report%20one.json", "x")).toBe("report one.json");
    expect(filenameFromDisposition(null, "fallback.csv")).toBe("fallback.csv");
  });
});

describe("401 handling", () => {
  const originalAdapter = api.defaults.adapter;
  let seenAuthorization: string[];

  beforeEach(() => {
    seenAuthorization = [];
    setAccessToken("expired-token");
    const adapter: AxiosAdapter = (config) => {
      const authorization = String(config.headers.get("Authorization") ?? "");
      seenAuthorization.push(`${config.url} ${authorization}`);
      if (config.url === "/auth/login") return reject(config, 401, { error: { code: "invalid_credentials", message: "Invalid email or password." } });
      if (authorization === "Bearer fresh-token") return Promise.resolve(response(config, 200, { ok: config.url }));
      return reject(config, 401, { error: { code: "authentication_required", message: "Authentication is required." } });
    };
    api.defaults.adapter = adapter;
  });

  afterEach(() => {
    api.defaults.adapter = originalAdapter;
    setRefreshHandler(null);
    setAccessToken(null);
  });

  it("refreshes once for concurrent requests and retries each with the new token", async () => {
    const refresh = vi.fn(async () => {
      await new Promise((resolve) => setTimeout(resolve, 10));
      setAccessToken("fresh-token");
      return "fresh-token";
    });
    setRefreshHandler(refresh);
    const [a, b] = await Promise.all([api.get("/alerts"), api.get("/datasets")]);
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(a.data).toEqual({ ok: "/alerts" });
    expect(b.data).toEqual({ ok: "/datasets" });
    expect(seenAuthorization).toContain("/alerts Bearer fresh-token");
  });

  it("does not try to refresh after a failed login", async () => {
    const refresh = vi.fn(async () => "fresh-token");
    setRefreshHandler(refresh);
    await expect(api.post("/auth/login", {})).rejects.toMatchObject({ code: "invalid_credentials", status: 401 });
    expect(refresh).not.toHaveBeenCalled();
  });

  it("surfaces the 401 when the refresh fails", async () => {
    setRefreshHandler(async () => null);
    await expect(api.get("/alerts")).rejects.toMatchObject({ status: 401, code: "authentication_required" });
  });
});
