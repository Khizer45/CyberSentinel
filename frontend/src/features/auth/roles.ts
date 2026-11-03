/**
 * Client-side role checks decide what the UI *offers*. Authorization is enforced by the API on every request
 * (RBAC + ownership scoping); hiding a link is a convenience, not a security control.
 */
import type { User, UserRole } from "../../types/api";

export const ALL_ROLES: readonly UserRole[] = ["admin", "analyst", "viewer"];
export const ANALYST_ROLES: readonly UserRole[] = ["admin", "analyst"];
export const ADMIN_ROLES: readonly UserRole[] = ["admin"];

export const ROLE_LABELS: Record<UserRole, string> = {
  admin: "Administrator",
  analyst: "Security analyst",
  viewer: "Viewer",
};

export const ROLE_DESCRIPTIONS: Record<UserRole, string> = {
  admin: "Full access: users, model approval, audit logs, all datasets and results.",
  analyst: "Uploads datasets, runs analyses, reviews alerts and exports their own results.",
  viewer: "Read-only access to aggregate dashboards, reports and approved model information.",
};

export function hasRole(user: Pick<User, "role"> | null | undefined, roles: readonly UserRole[]): boolean {
  return Boolean(user && roles.includes(user.role));
}

export function canAnalyze(user: Pick<User, "role"> | null | undefined): boolean {
  return hasRole(user, ANALYST_ROLES);
}

export function isAdmin(user: Pick<User, "role"> | null | undefined): boolean {
  return hasRole(user, ADMIN_ROLES);
}
