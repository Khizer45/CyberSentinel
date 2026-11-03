import { useState, type ReactNode } from "react";
import { Button } from "./Button";
import { TextAreaField } from "./FormFields";
import { Modal } from "./Modal";
import { ErrorCallout } from "./States";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  tone?: "danger" | "primary";
  busy?: boolean;
  error?: unknown;
  /** Ask for a free-text reason (required when ``reasonRequired``). */
  reasonLabel?: string;
  reasonRequired?: boolean;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}

export function ConfirmDialog(props: ConfirmDialogProps) {
  // Mounting the inner dialog only while open resets its state for every use.
  return props.open ? <ConfirmDialogInner {...props} /> : null;
}

function ConfirmDialogInner({
  title,
  message,
  confirmLabel = "Confirm",
  tone = "danger",
  busy = false,
  error,
  reasonLabel,
  reasonRequired = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const [reason, setReason] = useState("");
  const blocked = reasonRequired && reason.trim().length === 0;
  return (
    <Modal
      open
      title={title}
      onClose={busy ? () => undefined : onCancel}
      footer={
        <>
          <Button onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button variant={tone} loading={busy} disabled={blocked} onClick={() => onConfirm(reason.trim())}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div>{message}</div>
      {reasonLabel ? (
        <TextAreaField
          label={reasonLabel}
          value={reason}
          maxLength={500}
          required={reasonRequired}
          hint={reasonRequired ? "Required. Recorded in the audit log." : "Optional. Recorded in the audit log."}
          onChange={(event) => setReason(event.target.value)}
        />
      ) : null}
      <ErrorCallout error={error} />
    </Modal>
  );
}
