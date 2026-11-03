import { LinkButton } from "../components/Button";
import { Card } from "../components/Card";
import { EmptyState } from "../components/States";
import { usePageTitle } from "../hooks/usePageTitle";

export function NotFoundPage() {
  usePageTitle("Page not found");
  return (
    <Card>
      <EmptyState
        title="Page not found"
        message="The page you requested does not exist or has moved."
        action={
          <LinkButton to="/" variant="primary">
            Back to dashboard
          </LinkButton>
        }
      />
    </Card>
  );
}
