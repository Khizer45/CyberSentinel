import { useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { RoleBadge, StatusBadge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { KeyValueList } from "../components/DataDisplay";
import { DataTable } from "../components/DataTable";
import { TextField } from "../components/FormFields";
import { PageHeader } from "../components/PageHeader";
import { Callout, ErrorCallout, ErrorState, LoadingState } from "../components/States";
import { TabPanel, Tabs } from "../components/Tabs";
import { useToast } from "../components/Toast";
import { useAuth } from "../features/auth/AuthContext";
import { ROLE_DESCRIPTIONS } from "../features/auth/roles";
import { useTheme, type ThemePreference } from "../features/theme/ThemeProvider";
import { useSearchState } from "../hooks/useSearchState";
import { changePassword, updateProfile } from "../services/auth";
import { queryKeys } from "../services/queryKeys";
import { getHealth, getRiskPolicy, getSystemInfo } from "../services/system";
import { fieldErrors } from "../utils/errors";
import { formatDateTime, formatNumber, humanize } from "../utils/format";

const TABS = [
  { id: "profile", label: "Profile" },
  { id: "security", label: "Password" },
  { id: "appearance", label: "Appearance" },
  { id: "system", label: "System & risk policy" },
];

export function SettingsPage() {
  const search = useSearchState();
  const tab = TABS.some((item) => item.id === search.get("tab")) ? search.get("tab") : "profile";
  return (
    <>
      <PageHeader title="Settings" description="Your profile, password and display preferences, plus read-only system configuration." />
      <Tabs label="Settings sections" tabs={TABS} active={tab} onChange={(id) => search.update({ tab: id })} />
      <TabPanel id={tab}>
        {tab === "profile" ? <ProfileSettings /> : null}
        {tab === "security" ? <PasswordSettings /> : null}
        {tab === "appearance" ? <AppearanceSettings /> : null}
        {tab === "system" ? <SystemSettings /> : null}
      </TabPanel>
    </>
  );
}

function ProfileSettings() {
  const { user, updateUser } = useAuth();
  const toast = useToast();
  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const mutation = useMutation({
    mutationFn: () => updateProfile(displayName.trim()),
    onSuccess: (updated) => {
      updateUser(updated);
      toast.success("Profile updated.");
    },
  });
  if (!user) return null;
  const errors = fieldErrors(mutation.error);
  return (
    <div className="grid-2">
      <Card title="Profile">
        <form
          className="stack"
          onSubmit={(event: FormEvent) => {
            event.preventDefault();
            mutation.mutate();
          }}
        >
          <TextField
            label="Display name"
            value={displayName}
            maxLength={120}
            required
            error={errors.display_name}
            onChange={(event) => setDisplayName(event.target.value)}
          />
          <TextField label="Email" value={user.email} disabled hint="Email addresses are managed by an administrator." />
          {!errors.display_name ? <ErrorCallout error={mutation.error} /> : null}
          <div>
            <Button type="submit" variant="primary" loading={mutation.isPending} disabled={!displayName.trim() || displayName.trim() === user.display_name}>
              Save profile
            </Button>
          </div>
        </form>
      </Card>
      <Card title="Account">
        <KeyValueList
          items={[
            { label: "Role", value: <RoleBadge role={user.role} /> },
            { label: "Permissions", value: ROLE_DESCRIPTIONS[user.role] },
            { label: "Last sign-in", value: formatDateTime(user.last_login_at) },
            { label: "Member since", value: formatDateTime(user.created_at) },
          ]}
        />
      </Card>
    </div>
  );
}

function PasswordSettings() {
  const { endSession } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const mismatch = confirm.length > 0 && next !== confirm;
  const mutation = useMutation({
    mutationFn: () => changePassword(current, next),
    onSuccess: () => endSession("Your password was changed and all sessions were signed out. Sign in with your new password."),
  });
  const errors = fieldErrors(mutation.error);
  return (
    <Card title="Change password" subtitle="Changing your password signs out every session, including this one.">
      <form
        className="stack"
        style={{ maxWidth: 460 }}
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          if (!mismatch) mutation.mutate();
        }}
      >
        <TextField
          label="Current password"
          type="password"
          autoComplete="current-password"
          required
          value={current}
          error={errors.current_password}
          onChange={(event) => setCurrent(event.target.value)}
        />
        <TextField
          label="New password"
          type="password"
          autoComplete="new-password"
          required
          value={next}
          hint="At least 12 characters with letters and digits; must not contain your email name. Long passphrases are encouraged."
          error={errors.new_password}
          onChange={(event) => setNext(event.target.value)}
        />
        <TextField
          label="Confirm new password"
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          error={mismatch ? "The passwords do not match." : null}
          onChange={(event) => setConfirm(event.target.value)}
        />
        {!errors.new_password && !errors.current_password ? <ErrorCallout error={mutation.error} /> : null}
        <div>
          <Button type="submit" variant="primary" loading={mutation.isPending} disabled={!current || !next || mismatch}>
            Change password
          </Button>
        </div>
      </form>
    </Card>
  );
}

function AppearanceSettings() {
  const { preference, setPreference } = useTheme();
  const options: { value: ThemePreference; label: string; hint: string }[] = [
    { value: "system", label: "Match system", hint: "Follow your operating system setting." },
    { value: "light", label: "Light", hint: "Best for bright environments and printing." },
    { value: "dark", label: "Dark", hint: "Reduced glare for SOC displays." },
  ];
  return (
    <Card title="Theme" subtitle="Stored in this browser only.">
      <fieldset className="stack-sm" style={{ border: 0, padding: 0, margin: 0 }}>
        <legend className="sr-only">Theme</legend>
        {options.map((option) => (
          <label key={option.value} className="checkbox">
            <input type="radio" name="theme" value={option.value} checked={preference === option.value} onChange={() => setPreference(option.value)} />
            <span>
              <strong>{option.label}</strong> <span className="muted small">— {option.hint}</span>
            </span>
          </label>
        ))}
      </fieldset>
    </Card>
  );
}

function SystemSettings() {
  const system = useQuery({ queryKey: queryKeys.systemInfo, queryFn: getSystemInfo });
  const policy = useQuery({ queryKey: queryKeys.riskPolicy, queryFn: getRiskPolicy });
  const health = useQuery({ queryKey: queryKeys.health, queryFn: getHealth, staleTime: 10_000 });

  return (
    <div className="stack">
      <div className="grid-2">
        <Card title="System">
          {system.isPending ? (
            <LoadingState />
          ) : system.isError ? (
            <ErrorState error={system.error} onRetry={() => void system.refetch()} />
          ) : (
            <KeyValueList
              items={[
                { label: "Application", value: `${system.data.app_name} ${system.data.version}` },
                { label: "Environment", value: system.data.environment },
                { label: "Supported schemas", value: system.data.supported_schemas.join(", ") },
                { label: "Explanations", value: humanize(system.data.explain_scope) },
                ...Object.entries(system.data.limits).map(([key, value]) => ({
                  label: humanize(key),
                  value: typeof value === "number" ? formatNumber(value) : String(value),
                })),
              ]}
            />
          )}
        </Card>
        <Card title="Service health" actions={<Button size="sm" icon="refresh" onClick={() => void health.refetch()} loading={health.isFetching}>Check</Button>}>
          {health.isPending ? (
            <LoadingState />
          ) : health.isError ? (
            <ErrorState error={health.error} />
          ) : (
            <KeyValueList
              items={[
                { label: "Overall", value: <StatusBadge status={health.data.status === "ok" ? "success" : "failure"} /> },
                ...Object.entries(health.data.checks).map(([key, value]) => ({ label: humanize(key), value })),
              ]}
            />
          )}
        </Card>
      </div>

      <Card
        title="Risk policy"
        subtitle="How model outputs become 0–100 policy risk scores. Changes are versioned and made by editing the policy file on the server."
      >
        {policy.isPending ? (
          <LoadingState />
        ) : policy.isError ? (
          <ErrorState error={policy.error} onRetry={() => void policy.refetch()} />
        ) : (
          <div className="stack">
            <p>{policy.data.policy.description}</p>
            <KeyValueList
              items={[
                { label: "Policy version", value: policy.data.policy.policy_version },
                { label: "SHA-256", value: <code className="break">{policy.data.sha256}</code> },
                {
                  label: "Component weights",
                  value: `classifier ${policy.data.policy.weights.classifier} · anomaly ${policy.data.policy.weights.anomaly}`,
                },
                {
                  label: "Score floors",
                  value: `anomaly ${policy.data.policy.floors?.anomaly ?? "—"} · needs review ${policy.data.policy.floors?.needs_review ?? "—"}`,
                },
                {
                  label: "Alert when",
                  value: `band ≥ ${policy.data.policy.alerting?.min_band ?? "high"}${policy.data.policy.alerting?.alert_on_anomaly ? ", or anomalous" : ""}${
                    policy.data.policy.alerting?.alert_on_needs_review ? ", or needs review" : ""
                  }`,
                },
                { label: "Default category weight", value: String(policy.data.policy.category_weights?.default ?? "—") },
              ]}
            />
            <div className="grid-2">
              <DataTable
                caption="Risk bands"
                compact
                rowKey={(row) => row.name}
                rows={policy.data.policy.bands}
                columns={[
                  { key: "band", header: "Band", render: (row) => humanize(row.name) },
                  { key: "min", header: "Minimum score", align: "right", render: (row) => formatNumber(row.min_score, 1) },
                ]}
              />
              <DataTable
                caption="Category weight overrides"
                compact
                emptyTitle="No category overrides"
                rowKey={(row) => row[0]}
                rows={Object.entries(policy.data.policy.category_weights?.overrides ?? {})}
                columns={[
                  { key: "category", header: "Attack category", render: (row) => row[0] },
                  { key: "weight", header: "Weight", align: "right", render: (row) => formatNumber(row[1], 2) },
                ]}
              />
            </div>
            <Callout tone="info">Risk scores prioritise review. They are not probabilities and do not prove that a flow is malicious.</Callout>
          </div>
        )}
      </Card>
    </div>
  );
}
