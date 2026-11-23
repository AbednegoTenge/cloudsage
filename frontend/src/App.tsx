import { Navigate, Route, Routes } from "react-router-dom";
import { ScopeProvider } from "./context/ScopeContext";
import { AppShell } from "./layouts/AppShell";
import { AssistantPage } from "./pages/AssistantPage";
import { ConnectionsPage } from "./pages/ConnectionsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { InvestigationDetailPage } from "./pages/InvestigationDetailPage";
import { InfrastructurePage } from "./pages/InfrastructurePage";
import { InvestigationsPage } from "./pages/InvestigationsPage";
import { SettingsPage } from "./pages/SettingsPage";

export function App() {
  return (
    <ScopeProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="assistant" element={<AssistantPage />} />
          <Route path="investigations" element={<InvestigationsPage />} />
          <Route path="investigations/:id" element={<InvestigationDetailPage />} />
          <Route path="infrastructure" element={<InfrastructurePage />} />
          <Route path="connections" element={<ConnectionsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </ScopeProvider>
  );
}
