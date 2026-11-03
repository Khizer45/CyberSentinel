import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../services/apiClient";
import { makeUser } from "../test/fixtures";
import { renderWithProviders } from "../test/render";
import { LoginPage, safeRedirect } from "./LoginPage";

describe("LoginPage", () => {
  it("submits trimmed credentials", async () => {
    const login = vi.fn().mockResolvedValue(makeUser());
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />, { route: "/login", auth: { status: "anonymous", user: null, login } });
    await user.type(screen.getByLabelText("Email"), "  analyst@example.org ");
    await user.type(screen.getByLabelText("Password"), "Correct-Horse-9-Battery");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(login).toHaveBeenCalledWith("analyst@example.org", "Correct-Horse-9-Battery");
  });

  it("shows the API's message and clears the password after a failure", async () => {
    const login = vi.fn().mockRejectedValue(new ApiError(401, "invalid_credentials", "Invalid email or password.", null, "req-9"));
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />, { route: "/login", auth: { status: "anonymous", user: null, login } });
    await user.type(screen.getByLabelText("Email"), "analyst@example.org");
    await user.type(screen.getByLabelText("Password"), "wrong-password-1");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Invalid email or password.")).toBeInTheDocument();
    expect(screen.getByText("Request ID: req-9")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Password")).toHaveValue(""));
  });

  it("shows why the user was signed out", () => {
    renderWithProviders(<LoginPage />, {
      route: "/login",
      auth: { status: "anonymous", user: null, notice: "Your session has expired. Please sign in again." },
    });
    expect(screen.getByText("Your session has expired. Please sign in again.")).toBeInTheDocument();
  });

  it("only redirects to same-origin paths after sign-in", () => {
    expect(safeRedirect("/alerts?status=open")).toBe("/alerts?status=open");
    expect(safeRedirect("//evil.example")).toBe("/");
    expect(safeRedirect("https://evil.example")).toBe("/");
    expect(safeRedirect("/\\evil.example")).toBe("/");
    expect(safeRedirect(undefined)).toBe("/");
  });
});
