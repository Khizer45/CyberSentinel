import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { vi } from "vitest";
import { ToastProvider } from "../components/Toast";
import { AuthContext, type AuthContextValue } from "../features/auth/AuthContext";
import { ThemeProvider } from "../features/theme/ThemeProvider";
import { makeUser } from "./fixtures";

export function fakeAuth(overrides: Partial<AuthContextValue> = {}): AuthContextValue {
  return {
    status: "authenticated",
    user: makeUser(),
    notice: null,
    login: vi.fn(),
    logout: vi.fn(() => Promise.resolve()),
    endSession: vi.fn(),
    updateUser: vi.fn(),
    ...overrides,
  };
}

interface RenderOptions {
  route?: string;
  /** Route pattern so that ``useParams`` works, e.g. ``/alerts/:alertId``. */
  path?: string;
  auth?: Partial<AuthContextValue>;
}

/** Render with the same providers as the app, a fake auth session and a fresh query cache (no retries). */
export function renderWithProviders(ui: ReactElement, options: RenderOptions = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const auth = fakeAuth(options.auth);
  const element = options.path ? (
    <Routes>
      <Route path={options.path} element={ui} />
      <Route path="*" element={<div>other route</div>} />
    </Routes>
  ) : (
    ui
  );
  const result = render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ToastProvider>
          <MemoryRouter initialEntries={[options.route ?? "/"]} useTransitions={false}>
            <AuthContext.Provider value={auth}>{element}</AuthContext.Provider>
          </MemoryRouter>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
  return { ...result, auth, queryClient };
}
