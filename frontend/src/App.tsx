import type { ReactNode } from "react";
import { Route, Routes } from "react-router";
import { RequireAuth } from "./features/auth/RequireAuth";
import { RequireRole } from "./features/auth/RequireRole";
import { ADMIN_ROLES, ANALYST_ROLES } from "./features/auth/roles";
import { AppLayout } from "./layouts/AppLayout";
import { AlertDetailsPage } from "./pages/AlertDetailsPage";
import { AlertsPage } from "./pages/AlertsPage";
import { AnalysisJobsPage } from "./pages/AnalysisJobsPage";
import { AnalysisResultsPage } from "./pages/AnalysisResultsPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { AuditLogsPage } from "./pages/AuditLogsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DatasetsPage } from "./pages/DatasetsPage";
import { DatasetUploadPage } from "./pages/DatasetUploadPage";
import { LoginPage } from "./pages/LoginPage";
import { ModelsPage } from "./pages/ModelsPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { SettingsPage } from "./pages/SettingsPage";
import { UsersPage } from "./pages/UsersPage";

const analyst = (page: ReactNode) => <RequireRole roles={ANALYST_ROLES}>{page}</RequireRole>;
const admin = (page: ReactNode) => <RequireRole roles={ADMIN_ROLES}>{page}</RequireRole>;

/** Route map. Role guards mirror the API's RBAC for usability; the API enforces it on every request. */
export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="datasets" element={analyst(<DatasetsPage />)} />
        <Route path="datasets/upload" element={analyst(<DatasetUploadPage />)} />
        <Route path="analyses" element={analyst(<AnalysisJobsPage />)} />
        <Route path="analyses/:jobId" element={analyst(<AnalysisResultsPage />)} />
        <Route path="predictions/:predictionId" element={analyst(<AlertDetailsPage kind="prediction" />)} />
        <Route path="alerts" element={analyst(<AlertsPage />)} />
        <Route path="alerts/:alertId" element={analyst(<AlertDetailsPage kind="alert" />)} />
        <Route path="models" element={<ModelsPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="admin/users" element={admin(<UsersPage />)} />
        <Route path="admin/audit-logs" element={admin(<AuditLogsPage />)} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
