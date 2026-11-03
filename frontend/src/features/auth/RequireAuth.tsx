import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { FullPageLoader } from "../../components/States";
import { useAuth } from "./AuthContext";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "loading") return <FullPageLoader label="Restoring your session…" />;
  if (status === "anonymous") return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
  return <>{children}</>;
}
