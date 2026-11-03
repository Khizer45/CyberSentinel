import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getAccessToken } from "../../services/apiClient";
import * as authApi from "../../services/auth";
import { ApiError } from "../../services/apiClient";
import { makeUser } from "../../test/fixtures";
import type { TokenResponse } from "../../types/api";
import { AuthProvider, useAuth } from "./AuthContext";

vi.mock("../../services/auth", () => ({
  login: vi.fn(),
  refreshSession: vi.fn(),
  logout: vi.fn(),
  fetchMe: vi.fn(),
  updateProfile: vi.fn(),
  changePassword: vi.fn(),
}));

function Probe() {
  const auth = useAuth();
  return (
    <div>
      <span data-testid="status">{auth.status}</span>
      <span data-testid="user">{auth.user?.email ?? ""}</span>
      <button type="button" onClick={() => void auth.login("analyst@example.org", "pw")}>
        login
      </button>
      <button type="button" onClick={() => void auth.logout()}>
        logout
      </button>
    </div>
  );
}

function renderAuth() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

const tokens: TokenResponse = { access_token: "access-1", token_type: "bearer", expires_in: 900, user: makeUser() };

describe("AuthProvider", () => {
  beforeEach(() => {
    vi.mocked(authApi.refreshSession).mockReset();
    vi.mocked(authApi.login).mockReset();
    vi.mocked(authApi.logout).mockReset();
  });

  it("restores the session silently from the refresh cookie", async () => {
    vi.mocked(authApi.refreshSession).mockResolvedValue(tokens);
    renderAuth();
    expect(screen.getByTestId("status")).toHaveTextContent("loading");
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(screen.getByTestId("user")).toHaveTextContent("analyst@example.org");
    expect(getAccessToken()).toBe("access-1");
    expect(authApi.refreshSession).toHaveBeenCalledTimes(1);
  });

  it("becomes anonymous when there is no valid refresh cookie", async () => {
    vi.mocked(authApi.refreshSession).mockRejectedValue(new ApiError(401, "session_expired", "expired"));
    renderAuth();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));
    expect(getAccessToken()).toBeNull();
  });

  it("signs in and out, clearing the in-memory token", async () => {
    vi.mocked(authApi.refreshSession).mockRejectedValue(new ApiError(401, "session_expired", "expired"));
    vi.mocked(authApi.login).mockResolvedValue({ ...tokens, access_token: "access-2" });
    vi.mocked(authApi.logout).mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderAuth();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));

    await user.click(screen.getByRole("button", { name: "login" }));
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(getAccessToken()).toBe("access-2");

    await user.click(screen.getByRole("button", { name: "logout" }));
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));
    expect(authApi.logout).toHaveBeenCalledTimes(1);
    expect(getAccessToken()).toBeNull();
  });
});
