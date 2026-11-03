import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Badge, RoleBadge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { DataTable } from "../components/DataTable";
import { SelectField, TextField } from "../components/FormFields";
import { PageHeader } from "../components/PageHeader";
import { Pagination } from "../components/Pagination";
import { CreateUserDialog, EditUserDialog, ResetPasswordDialog } from "../features/admin/UserDialogs";
import { useAuth } from "../features/auth/AuthContext";
import { ALL_ROLES, ROLE_LABELS } from "../features/auth/roles";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { useSearchState } from "../hooks/useSearchState";
import { listUsers } from "../services/admin";
import { queryKeys } from "../services/queryKeys";
import type { User } from "../types/api";
import { formatDateTime } from "../utils/format";

export function UsersPage() {
  const { user: currentUser } = useAuth();
  const search = useSearchState();
  const [text, setText] = useState(search.get("q"));
  const q = useDebouncedValue(text.trim(), 350);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [resetting, setResetting] = useState<User | null>(null);

  const active = search.get("active");
  const query = {
    q: q || undefined,
    role: search.get("role") || undefined,
    is_active: active === "true" ? true : active === "false" ? false : undefined,
    sort: search.get("sort", "email"),
    limit: search.getNumber("limit", 25),
    offset: search.getNumber("offset", 0),
  };
  const users = useQuery({ queryKey: queryKeys.users(query), queryFn: () => listUsers(query), placeholderData: keepPreviousData });

  return (
    <>
      <PageHeader
        title="User management"
        description="Create accounts, assign roles and deactivate access. Accounts are never deleted so that audit history stays attributable."
        actions={
          <Button variant="primary" icon="plus" onClick={() => setCreating(true)}>
            Create user
          </Button>
        }
      />
      <Card flush>
        <div className="filter-bar">
          <TextField
            className="grow"
            label="Search"
            type="search"
            placeholder="Name or email"
            value={text}
            onChange={(event) => {
              setText(event.target.value);
              search.update({ q: event.target.value });
            }}
          />
          <SelectField
            label="Role"
            placeholder="Any role"
            options={ALL_ROLES.map((role) => ({ value: role, label: ROLE_LABELS[role] }))}
            value={search.get("role")}
            onChange={(event) => search.update({ role: event.target.value })}
          />
          <SelectField
            label="State"
            placeholder="Any state"
            options={[
              { value: "true", label: "Active" },
              { value: "false", label: "Deactivated" },
            ]}
            value={active}
            onChange={(event) => search.update({ active: event.target.value })}
          />
        </div>
        <DataTable<User>
          caption="Users"
          rows={users.data?.items}
          loading={users.isFetching}
          error={users.error}
          onRetry={() => void users.refetch()}
          rowKey={(row) => row.id}
          sort={query.sort}
          onSortChange={(sort) => search.update({ sort })}
          emptyTitle="No users match"
          columns={[
            {
              key: "name",
              header: "Name",
              sortKey: "display_name",
              render: (row) => (
                <span>
                  <strong>{row.display_name}</strong>
                  {row.id === currentUser?.id ? <span className="subtle small"> (you)</span> : null}
                </span>
              ),
            },
            { key: "email", header: "Email", sortKey: "email", render: (row) => <span className="break">{row.email}</span> },
            { key: "role", header: "Role", sortKey: "role", render: (row) => <RoleBadge role={row.role} /> },
            { key: "state", header: "State", render: (row) => (row.is_active ? <Badge tone="success" dot>Active</Badge> : <Badge dot>Deactivated</Badge>) },
            { key: "login", header: "Last sign-in", render: (row) => <span className="nowrap">{formatDateTime(row.last_login_at)}</span> },
            { key: "created", header: "Created", sortKey: "created_at", render: (row) => <span className="nowrap">{formatDateTime(row.created_at)}</span> },
            {
              key: "actions",
              header: <span className="sr-only">Actions</span>,
              align: "right",
              render: (row) => (
                <div className="row" style={{ justifyContent: "flex-end", flexWrap: "nowrap" }}>
                  <Button size="sm" onClick={() => setEditing(row)}>
                    Edit
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setResetting(row)}>
                    Reset password
                  </Button>
                </div>
              ),
            },
          ]}
        />
        {users.data ? (
          <Pagination
            total={users.data.total}
            limit={query.limit}
            offset={query.offset}
            onChange={(offset) => search.update({ offset }, { resetPage: false })}
            onLimitChange={(limit) => search.update({ limit })}
          />
        ) : null}
      </Card>
      <CreateUserDialog open={creating} onClose={() => setCreating(false)} />
      <EditUserDialog user={editing} currentUserId={currentUser?.id} onClose={() => setEditing(null)} />
      <ResetPasswordDialog user={resetting} onClose={() => setResetting(null)} />
    </>
  );
}
