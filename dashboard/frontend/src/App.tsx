import { lazy, Suspense } from "react";
import { Routes, Route, Navigate, Link, useParams } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import PageSkeleton from "./components/PageSkeleton";

const BuilderPage = lazy(() => import("./pages/BuilderPage"));
const AdminAuditLogPage = lazy(() => import("./pages/AdminAuditLogPage"));
const AdminSettingsPage = lazy(() => import("./pages/AdminSettingsPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const PrivacyPage = lazy(() => import("./pages/PrivacyPage"));
const TermsPage = lazy(() => import("./pages/TermsPage"));
const PrivacyPolicyPage = lazy(() => import("./pages/PrivacyPolicyPage"));

export default function App() {
  return (
    <>
      <Suspense fallback={<PageSkeleton />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/privacy" element={<PrivacyPolicyPage />} />
          <Route path="/terms" element={<TermsPage />} />
          <Route path="/me/privacy" element={<PrivacyPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/builder/:guildId" element={<BuilderPage />} />
          <Route path="/settings/:guildId" element={<AdminSettingsPage />} />
          <Route path="/settings/:guildId/audit-log" element={<AdminAuditLogPage />} />
          {/* Back-compat: old Admin/Mod routes now fold into Settings. */}
          <Route path="/admin" element={<Navigate to="/settings" replace />} />
          <Route path="/mod" element={<Navigate to="/settings" replace />} />
          <Route path="/admin/guilds/:guildId/audit-log" element={<RedirectAuditLog />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </Suspense>
      <footer className="site-footer">
        <span className="site-footer__brand">Empire of Shadows &middot; TheCodex Dashboard</span>
        <nav className="site-footer__links" aria-label="Legal">
          <Link to="/terms">Terms of Service</Link>
          <Link to="/privacy">Privacy Policy</Link>
        </nav>
      </footer>
    </>
  );
}

function RedirectAuditLog() {
  const { guildId } = useParams();
  return <Navigate to={`/settings/${guildId}/audit-log`} replace />;
}
