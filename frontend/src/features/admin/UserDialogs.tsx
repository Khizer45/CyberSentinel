import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "../../components/Button";
import { Checkbox, SelectField, TextField } from "../../components/FormFields";
import { Modal } from "../../components/Modal";
import { Callout, ErrorCallout } from "../../components/States";
import { useToast } from "../../components/Toast";
import { createUser, resetPassword, updateUser } from "../../services/admin";
import { queryKeys } from "../../services/queryKeys";
import type { User, UserRole } from "../../types/api";
import { fieldErrors } from "../../utils/errors";
import { ALL_ROLES, ROLE_DESCRIPTIONS, ROLE_LABELS } from "../auth/roles";

const ROLE_OPTIONS = ALL_ROLES.map((role) => ({ value: role, label: ROLE_LABELS[role] }));
const PASSWORD_HINT = "At least 12 characters with letters and digits; must not contain the e-mail name.";

export function CreateUserDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return open ? <CreateUserForm onClose={onClose} /> : null;
}

function CreateUserForm({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState<UserRole>("analyst");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const mismatch = confirm.length > 0 && password !== confirm;
  const mutation = useMutation({
    mutationFn: () => createUser({ email: email.trim(), display_name: displayName.trim(), role, password }),
    onSuccess: async (user) => {
      toast.success(`Account created for ${user.email}. Share the initial password through a secure channel.`);
      await queryClient.invalidateQueries({ queryKey: queryKeys.usersAll });
      onClose();
    },
  });
  const errors = fieldErrors(mutation.error);
  const showGeneric = mutation.error && Object.keys(errors).length === 0;
  return (
    <Modal
      open
      title="Create user"
      onClose={mutation.isPending ? () => undefined : onClose}
      footer={
        <>
          <Button onClick={onClose} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={mutation.isPending}
            disabled={!email.trim() || !displayName.trim() || !password || mismatch}
            onClick={() => mutation.mutate()}
          >
            Create user
          </Button>
        </>
      }
    >
      <TextField label="Email" type="email" autoComplete="off" value={email} error={errors.email} onChange={(event) => setEmail(event.target.value)} />
      <TextField label="Display name" value={displayName} maxLength={120} error={errors.display_name} onChange={(event) => setDisplayName(event.target.value)} />
      <SelectField label="Role" value={role} options={ROLE_OPTIONS} hint={ROLE_DESCRIPTIONS[role]} onChange={(event) => setRole(event.target.value as UserRole)} />
      <TextField label="Initial password" type="password" autoComplete="new-password" value={password} hint={PASSWORD_HINT} error={errors.password} onChange={(event) => setPassword(event.target.value)} />
      <TextField
        label="Confirm password"
        type="password"
        autoComplete="new-password"
        value={confirm}
        error={mismatch ? "The passwords do not match." : null}
        onChange={(event) => setConfirm(event.target.value)}
      />
      {showGeneric ? <ErrorCallout error={mutation.error} /> : null}
    </Modal>
  );
}

export function EditUserDialog({ user, currentUserId, onClose }: { user: User | null; currentUserId: string | undefined; onClose: () => void }) {
  return user ? <EditUserForm key={user.id} user={user} self={user.id === currentUserId} onClose={onClose} /> : null;
}

function EditUserForm({ user, self, onClose }: { user: User; self: boolean; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [displayName, setDisplayName] = useState(user.display_name);
  const [role, setRole] = useState<UserRole>(user.role);
  const [active, setActive] = useState(user.is_active);
  const mutation = useMutation({
    mutationFn: () =>
      updateUser(user.id, {
        display_name: displayName.trim() !== user.display_name ? displayName.trim() : undefined,
        role: role !== user.role ? role : undefined,
        is_active: active !== user.is_active ? active : undefined,
      }),
    onSuccess: async (updated) => {
      toast.success(`${updated.email} updated.`);
      await queryClient.invalidateQueries({ queryKey: queryKeys.usersAll });
      onClose();
    },
  });
  const errors = fieldErrors(mutation.error);
  const changed = displayName.trim() !== user.display_name || role !== user.role || active !== user.is_active;
  return (
    <Modal
      open
      title={`Edit ${user.email}`}
      onClose={mutation.isPending ? () => undefined : onClose}
      footer={
        <>
          <Button onClick={onClose} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button variant="primary" loading={mutation.isPending} disabled={!changed || !displayName.trim()} onClick={() => mutation.mutate()}>
            Save changes
          </Button>
        </>
      }
    >
      <TextField label="Display name" value={displayName} maxLength={120} error={errors.display_name} onChange={(event) => setDisplayName(event.target.value)} />
      <SelectField label="Role" value={role} options={ROLE_OPTIONS} hint={ROLE_DESCRIPTIONS[role]} onChange={(event) => setRole(event.target.value as UserRole)} />
      <Checkbox label="Account is active (can sign in)" checked={active} onChange={(event) => setActive(event.target.checked)} />
      {self ? <Callout tone="warning">You are editing your own account. The last active administrator cannot be demoted or deactivated.</Callout> : null}
      {role !== user.role || active !== user.is_active ? (
        <Callout tone="info">Role and activation changes sign the user out of all sessions.</Callout>
      ) : null}
      <ErrorCallout error={Object.keys(errors).length ? null : mutation.error} />
    </Modal>
  );
}

export function ResetPasswordDialog({ user, onClose }: { user: User | null; onClose: () => void }) {
  return user ? <ResetPasswordForm key={user.id} user={user} onClose={onClose} /> : null;
}

function ResetPasswordForm({ user, onClose }: { user: User; onClose: () => void }) {
  const toast = useToast();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const mismatch = confirm.length > 0 && password !== confirm;
  const mutation = useMutation({
    mutationFn: () => resetPassword(user.id, password),
    onSuccess: () => {
      toast.success(`Password reset for ${user.email}. Their sessions were signed out.`);
      onClose();
    },
  });
  const errors = fieldErrors(mutation.error);
  return (
    <Modal
      open
      title={`Reset password · ${user.email}`}
      onClose={mutation.isPending ? () => undefined : onClose}
      footer={
        <>
          <Button onClick={onClose} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button variant="danger" loading={mutation.isPending} disabled={!password || mismatch} onClick={() => mutation.mutate()}>
            Reset password
          </Button>
        </>
      }
    >
      <p className="muted">The user's existing sessions are revoked. Share the new password through a secure channel and ask them to change it.</p>
      <TextField label="New password" type="password" autoComplete="new-password" value={password} hint={PASSWORD_HINT} error={errors.new_password} onChange={(event) => setPassword(event.target.value)} />
      <TextField
        label="Confirm new password"
        type="password"
        autoComplete="new-password"
        value={confirm}
        error={mismatch ? "The passwords do not match." : null}
        onChange={(event) => setConfirm(event.target.value)}
      />
      <ErrorCallout error={errors.new_password ? null : mutation.error} />
    </Modal>
  );
}
