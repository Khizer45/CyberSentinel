import type { ReactNode } from "react";
import { LinkButton } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/States";
import { usePageTitle } from "../../hooks/usePageTitle";
import type { UserRole } from "../../types/api";
import { useAuth } from "./AuthContext";
import { hasRole, ROLE_LABELS } from "./roles";

export function RequireRole({ roles, children }: { roles: readonly UserRole[]; children: ReactNode }) {
  const { user } = useAuth();
  if (!hasRole(user, roles)) return <Forbidden />;
  return <>{children}</>;
}

function Forbidden() {
  const { user } = useAuth();
  usePageTitle("Access denied");
  return (
    <Card>
      <EmptyState
        title="You do not have access to this page"
        message={`Your role (${user ? ROLE_LABELS[user.role] : "unknown"}) does not include this feature. Ask an administrator if you need access.`}
        action={
          <LinkButton to="/" variant="primary">
            Back to dashboard
          </LinkButton>
        }
      />
    </Card>
  );
}
