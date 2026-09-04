import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { ToastProvider } from "./hooks/useToast";
import { DataModeProvider, useDataMode } from "./context/DataModeContext";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ToastViewport, Skeleton } from "./components";
import { AppShell } from "./layout/AppShell";
import { OverviewPage } from "./pages/OverviewPage";
import { OpportunitiesPage, OpportunityDetailPage } from "./pages/OpportunitiesPage";
import { CustomersPage, CustomerDetailPage } from "./pages/CustomersPage";
import { WorkPage } from "./pages/WorkPage";
import { MoneyPage } from "./pages/MoneyPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { ReportsPage } from "./pages/ReportsPage";
import { SettingsLayout, SettingsGeneralPage } from "./pages/SettingsLayout";
import { SystemControlsPage } from "./pages/SystemControlsPage";
import { AiTeamPage, AdvancedSettingsPage } from "./pages/AiTeamPage";
import { LoginPage } from "./pages/LoginPage";

/**
 * Live mode requires session auth or emergency API key.
 * Demo mode stays open without sign-in.
 */
function LiveAuthGate({ children }) {
  const { isLive } = useDataMode();
  const { canUseLiveApi, loading } = useAuth();
  const location = useLocation();

  if (!isLive) return children;
  if (loading) {
    return (
      <div className="stack" style={{ padding: "2rem" }}>
        <Skeleton rows={3} />
      </div>
    );
  }
  if (!canUseLiveApi) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return children;
}

export default function App() {
  return (
    <ToastProvider>
      <DataModeProvider>
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route
                element={
                  <LiveAuthGate>
                    <AppShell />
                  </LiveAuthGate>
                }
              >
                <Route index element={<OverviewPage />} />
                <Route path="opportunities" element={<OpportunitiesPage />} />
                <Route path="opportunities/:id" element={<OpportunityDetailPage />} />
                <Route path="customers" element={<CustomersPage />} />
                <Route path="customers/:id" element={<CustomerDetailPage />} />
                <Route path="work" element={<WorkPage />} />
                <Route path="money" element={<MoneyPage />} />
                <Route path="approvals" element={<ApprovalsPage />} />
                <Route path="reports" element={<ReportsPage />} />

                <Route path="settings" element={<SettingsLayout />}>
                  <Route index element={<SettingsGeneralPage />} />
                  <Route path="system" element={<SystemControlsPage />} />
                  <Route path="ai-team" element={<AiTeamPage />} />
                  <Route path="advanced" element={<AdvancedSettingsPage />} />
                </Route>

                {/* Legacy routes — repositioned, not deleted */}
                <Route path="agents" element={<Navigate to="/settings/ai-team" replace />} />
                <Route path="system" element={<Navigate to="/settings/system" replace />} />
                <Route path="finance" element={<Navigate to="/money" replace />} />
                <Route path="projects" element={<Navigate to="/work" replace />} />
                <Route path="goals" element={<Navigate to="/" replace />} />
                <Route path="companies" element={<Navigate to="/opportunities" replace />} />
                <Route path="leads" element={<Navigate to="/opportunities" replace />} />
                <Route path="audits" element={<Navigate to="/opportunities" replace />} />
                <Route path="outreach" element={<Navigate to="/opportunities" replace />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Routes>
          </BrowserRouter>
          <ToastViewport />
        </AuthProvider>
      </DataModeProvider>
    </ToastProvider>
  );
}
