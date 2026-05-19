import { Routes, Route, Navigate } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import BuilderPage from "./pages/BuilderPage";
import AdminAuditLogPage from "./pages/AdminAuditLogPage";

export default function App() {
  return (
    <>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/builder/:guildId" element={<BuilderPage />} />
        <Route path="/admin/guilds/:guildId/audit-log" element={<AdminAuditLogPage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
      <footer className="site-footer">Empire of Shadows &middot; TheCodex Dashboard</footer>
    </>
  );
}
