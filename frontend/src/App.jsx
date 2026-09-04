import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { ToastProvider } from './hooks/useToast'
import { ToastViewport } from './components'
import { AppShell } from './layout/AppShell'
import { OverviewPage } from './pages/OverviewPage'
import { GoalsPage } from './pages/GoalsPage'
import { AgentsPage } from './pages/AgentsPage'
import { CompaniesPage } from './pages/CompaniesPage'
import { LeadsPage } from './pages/LeadsPage'
import { AuditsPage } from './pages/AuditsPage'
import { OutreachPage } from './pages/OutreachPage'
import { CustomersPage } from './pages/CustomersPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { FinancePage } from './pages/FinancePage'
import { ApprovalsPage } from './pages/ApprovalsPage'
import { ReportsPage } from './pages/ReportsPage'
import { SystemHealthPage } from './pages/SystemHealthPage'
import { SettingsPage } from './pages/SettingsPage'

export default function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<OverviewPage />} />
            <Route path="goals" element={<GoalsPage />} />
            <Route path="agents" element={<AgentsPage />} />
            <Route path="companies" element={<CompaniesPage />} />
            <Route path="leads" element={<LeadsPage />} />
            <Route path="audits" element={<AuditsPage />} />
            <Route path="outreach" element={<OutreachPage />} />
            <Route path="customers" element={<CustomersPage />} />
            <Route path="projects" element={<ProjectsPage />} />
            <Route path="finance" element={<FinancePage />} />
            <Route path="approvals" element={<ApprovalsPage />} />
            <Route path="reports" element={<ReportsPage />} />
            <Route path="system" element={<SystemHealthPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <ToastViewport />
    </ToastProvider>
  )
}
