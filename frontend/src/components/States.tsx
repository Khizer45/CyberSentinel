import type { ReactNode } from "react";
import { toApiError } from "../services/apiClient";
import { errorMessage } from "../utils/errors";
import { Button } from "./Button";
import { Icon } from "./Icon";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function FullPageLoader({ label }: { label: string }) {
  return (
    <div className="full-page-state">
      <LoadingState label={label} />
    </div>
  );
}

export function EmptyState({ title, message, action }: { title: string; message?: ReactNode; action?: ReactNode }) {
  return (
    <div className="state">
      <span className="state-title">{title}</span>
      {message ? <span>{message}</span> : null}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry, title = "Something went wrong" }: { error: unknown; onRetry?: () => void; title?: string }) {
  const apiError = toApiError(error);
  return (
    <div className="state" role="alert">
      <span className="state-title">{title}</span>
      <span>{errorMessage(error)}</span>
      {apiError.requestId ? <span className="subtle small">Request ID: {apiError.requestId}</span> : null}
      {onRetry ? (
        <Button size="sm" icon="refresh" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}

type CalloutTone = "info" | "warning" | "danger" | "success";

export function Callout({ tone = "info", title, children }: { tone?: CalloutTone; title?: ReactNode; children?: ReactNode }) {
  const icon = tone === "danger" || tone === "warning" ? "warning" : tone === "success" ? "check" : "info";
  return (
    <div className={`callout callout-${tone}`} role={tone === "danger" ? "alert" : undefined}>
      <Icon name={icon} />
      <div className="stack-sm" style={{ gap: 4 }}>
        {title ? <span className="callout-title">{title}</span> : null}
        {children ? <div>{children}</div> : null}
      </div>
    </div>
  );
}

/** Inline API error with optional request ID for support. */
export function ErrorCallout({ error, title }: { error: unknown; title?: string }) {
  if (!error) return null;
  const apiError = toApiError(error);
  return (
    <Callout tone="danger" title={title ?? errorMessage(error)}>
      {title ? <p>{errorMessage(error)}</p> : null}
      {apiError.requestId ? <p className="small subtle">Request ID: {apiError.requestId}</p> : null}
    </Callout>
  );
}
