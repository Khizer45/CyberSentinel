import { useState } from "react";
import { NavLink, Outlet } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Badge, RoleBadge } from "../components/Badge";
import { Button } from "../components/Button";
import { BrandMark, Icon, type IconName } from "../components/Icon";
import { useAuth } from "../features/auth/AuthContext";
import { ADMIN_ROLES, ALL_ROLES, ANALYST_ROLES, hasRole } from "../features/auth/roles";
import { useTheme } from "../features/theme/ThemeProvider";
import { queryKeys } from "../services/queryKeys";
import { getSystemInfo } from "../services/system";
import type { UserRole } from "../types/api";
import { cx } from "../utils/cx";

interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  roles: readonly UserRole[];
  end?: boolean;
}

const NAVIGATION: { section: string; items: NavItem[] }[] = [
  { section: "Overview", items: [{ to: "/", label: "Dashboard", icon: "dashboard", roles: ALL_ROLES, end: true }] },
  {
    section: "Detection",
    items: [
      { to: "/datasets", label: "Datasets", icon: "database", roles: ANALYST_ROLES, end: true },
      { to: "/datasets/upload", label: "Upload dataset", icon: "upload", roles: ANALYST_ROLES },
      { to: "/analyses", label: "Analysis jobs", icon: "activity", roles: ANALYST_ROLES },
      { to: "/alerts", label: "Alerts", icon: "shield", roles: ANALYST_ROLES },
    ],
  },
  {
    section: "Insights",
    items: [
      { to: "/models", label: "Models", icon: "cpu", roles: ALL_ROLES },
      { to: "/analytics", label: "Analytics & reports", icon: "chart", roles: ALL_ROLES },
    ],
  },
  {
    section: "Administration",
    items: [
      { to: "/admin/users", label: "Users", icon: "users", roles: ADMIN_ROLES },
      { to: "/admin/audit-logs", label: "Audit logs", icon: "file", roles: ADMIN_ROLES },
    ],
  },
  { section: "Account", items: [{ to: "/settings", label: "Settings", icon: "settings", roles: ALL_ROLES }] },
];

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}

export function AppLayout() {
  const { user, logout } = useAuth();
  const { resolved, setPreference } = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const { data: system } = useQuery({ queryKey: queryKeys.systemInfo, queryFn: getSystemInfo, staleTime: 5 * 60_000 });

  const sections = NAVIGATION.map((section) => ({ ...section, items: section.items.filter((item) => hasRole(user, item.roles)) })).filter(
    (section) => section.items.length > 0,
  );

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <aside className={cx("sidebar", menuOpen && "open")} aria-label="Primary">
        <NavLink to="/" className="brand" onClick={() => setMenuOpen(false)}>
          <BrandMark />
          <span>
            CyberSentinel
            <small>Network threat detection</small>
          </span>
        </NavLink>
        <nav className="nav">
          {sections.map((section) => (
            <div key={section.section} className="stack-sm" style={{ gap: 2 }}>
              <span className="nav-section">{section.section}</span>
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) => cx("nav-link", isActive && "active")}
                  onClick={() => setMenuOpen(false)}
                >
                  <Icon name={item.icon} />
                  {item.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          {system ? `v${system.version} · risk policy ${system.risk_policy_version}` : "CyberSentinel"}
          <br />
          Decision support only — verify before acting.
        </div>
      </aside>
      {menuOpen ? <div className="sidebar-backdrop" onClick={() => setMenuOpen(false)} aria-hidden="true" /> : null}

      <div className="main-column">
        <header className="topbar">
          <Button variant="ghost" icon="menu" className="menu-button" aria-label="Open navigation" onClick={() => setMenuOpen(true)} />
          {system && system.environment !== "production" ? <Badge tone="warning">{system.environment}</Badge> : null}
          <span className="spacer" />
          <Button
            variant="ghost"
            icon={resolved === "dark" ? "sun" : "moon"}
            aria-label={resolved === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            onClick={() => setPreference(resolved === "dark" ? "light" : "dark")}
          />
          {user ? (
            <div className="user-chip">
              <span className="avatar" aria-hidden="true">
                {initials(user.display_name)}
              </span>
              <span className="user-meta">
                <span>{user.display_name}</span>
                <span className="subtle small">{user.email}</span>
              </span>
              <RoleBadge role={user.role} />
            </div>
          ) : null}
          <Button
            variant="ghost"
            icon="logout"
            loading={signingOut}
            onClick={async () => {
              setSigningOut(true);
              await logout();
            }}
          >
            Sign out
          </Button>
        </header>
        <main id="main-content" className="content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
