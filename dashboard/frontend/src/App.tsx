import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import PageSkeleton from "./components/PageSkeleton";

const BuilderPage = lazy(() => import("./pages/BuilderPage"));
const AdminAuditLogPage = lazy(() => import("./pages/AdminAuditLogPage"));

export default function App() {
  return (
    <>
      <Suspense fallback={<PageSkeleton />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/builder/:guildId" element={<BuilderPage />} />
          <Route path="/admin/guilds/:guildId/audit-log" element={<AdminAuditLogPage />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </Suspense>
      <footer className="site-footer">Empire of Shadows &middot; TheCodex Dashboard</footer>
    </>
  );
}
