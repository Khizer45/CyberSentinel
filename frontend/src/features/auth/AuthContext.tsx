/**
 * Session management.
 *
 * - On load, a silent ``POST /auth/refresh`` uses the HttpOnly refresh cookie to restore the session.
 * - The short-lived access token is held in memory by the API client and refreshed shortly before expiry,
 *   or on demand after a 401 (single-flight).
 * - Sign-out revokes all of the user's tokens server-side and clears every cached query.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { refreshAccessToken, setAccessToken, setRefreshHandler } from "../../services/apiClient";
import * as authApi from "../../services/auth";
import type { TokenResponse, User } from "../../types/api";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

export interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  /** Message for the sign-in page (e.g. "session expired"). */
  notice: string | null;
  login: (email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  /** Clear the local session without calling the API (after a password change revoked all tokens). */
  endSession: (notice?: string) => void;
  updateUser: (user: User) => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

interface AuthState {
  status: AuthStatus;
  user: User | null;
  notice: string | null;
}

const SESSION_EXPIRED = "Your session has expired. Please sign in again.";

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<AuthState>({ status: "loading", user: null, notice: null });
  const timer = useRef<number | null>(null);

  const clearTimer = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  const applyTokens = useCallback(
    (tokens: TokenResponse) => {
      setAccessToken(tokens.access_token);
      setState({ status: "authenticated", user: tokens.user, notice: null });
      clearTimer();
      // Refresh one minute before the access token expires (never more often than every 30 s).
      const delayMs = Math.max(30, tokens.expires_in - 60) * 1000;
      timer.current = window.setTimeout(() => void refreshAccessToken(), delayMs);
    },
    [clearTimer],
  );

  const signOutLocally = useCallback(
    (notice: string | null) => {
      clearTimer();
      setAccessToken(null);
      queryClient.clear();
      setState({ status: "anonymous", user: null, notice });
    },
    [clearTimer, queryClient],
  );

  useEffect(() => {
    setRefreshHandler(async () => {
      try {
        const tokens = await authApi.refreshSession();
        applyTokens(tokens);
        return tokens.access_token;
      } catch {
        clearTimer();
        setAccessToken(null);
        queryClient.clear();
        setState((previous) => ({
          status: "anonymous",
          user: null,
          notice: previous.status === "authenticated" ? SESSION_EXPIRED : null,
        }));
        return null;
      }
    });
    return () => setRefreshHandler(null);
  }, [applyTokens, clearTimer, queryClient]);

  // Silent sign-in from the refresh cookie. Concurrent calls (e.g. React StrictMode) share one request.
  useEffect(() => {
    void refreshAccessToken();
    return clearTimer;
  }, [clearTimer]);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await authApi.login(email, password);
      queryClient.clear();
      applyTokens(tokens);
      return tokens.user;
    },
    [applyTokens, queryClient],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // The local session is cleared regardless; the refresh cookie expires on its own.
    }
    signOutLocally(null);
  }, [signOutLocally]);

  const value = useMemo<AuthContextValue>(
    () => ({
      ...state,
      login,
      logout,
      endSession: (notice?: string) => signOutLocally(notice ?? null),
      updateUser: (user: User) => setState((previous) => ({ ...previous, user })),
    }),
    [state, login, logout, signOutLocally],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
