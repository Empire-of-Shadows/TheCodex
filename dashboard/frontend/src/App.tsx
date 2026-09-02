import { lazy, Suspense } from "react";
import {
  Routes,
  Route,
  Navigate,
  useLocation,
  useParams,
  useSearchParams,
} from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import PageSkeleton from "./components/PageSkeleton";
import { AppFooter } from "./_engine/components/AppFooter";

const OverviewPage = lazy(() => import("./pages/OverviewPage"));
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
          {/* Public legal pages - no auth; canonical URLs for Discord review. */}
          <Route path="/privacy" element={<PrivacyPolicyPage />} />
          <Route path="/terms" element={<TermsPage />} />

          {/* Member self-service lives under /me, as it does fleet-wide. */}
          <Route path="/me" element={<MeOrRedirect />} />
          {/* One server's own page. Everything the home used to draw inline for
              a picked server lives here, beside that server's other pages. */}
          <Route path="/me/guilds/:guildId/overview" element={<OverviewPage />} />
          <Route path="/me/privacy" element={<PrivacyPage />} />

          {/* Admin config lives under /settings: the hub, then one server's
              three management pages as siblings beneath it. These are declared
              before the legacy two-segment forms below, and they are also four
              segments deep where the legacy forms are two and three, so the
              parameterised redirects cannot swallow them. */}
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/settings/guilds/:guildId/settings" element={<AdminSettingsPage />} />
          <Route path="/settings/guilds/:guildId/audit-log" element={<AdminAuditLogPage />} />
          <Route path="/settings/guilds/:guildId/builder" element={<BuilderPage />} />

          {/* Back-compat. The home page was /dashboard and one server's admin
              pages were /settings/<id> and /builder/<id>, so all of those are
              out there in bookmarks and in Discord messages. They redirect
              rather than 404. Old Admin/Mod routes fold into Settings. */}
          <Route path="/dashboard" element={<LegacyHomeRedirect />} />
          <Route path="/settings/:guildId" element={<LegacyAdminRedirect page="settings" />} />
          <Route
            path="/settings/:guildId/audit-log"
            element={<LegacyAdminRedirect page="audit-log" />}
          />
          <Route path="/builder/:guildId" element={<LegacyBuilderRedirect />} />
          <Route path="/admin" element={<Navigate to="/settings" replace />} />
          <Route path="/mod" element={<Navigate to="/settings" replace />} />
          <Route path="/admin/guilds/:guildId/audit-log" element={<RedirectAuditLog />} />

          <Route path="*" element={<Navigate to="/me" replace />} />
        </Routes>
      </Suspense>
      <AppFooter brand="Empire of Shadows · TheCodex Dashboard" />
    </>
  );
}

/**
 * What /me renders, and where an old shareable link goes.
 *
 * A single server's view used to be `?guild=<id>` on the home page, so those
 * links are out there in Discord messages and bookmarks. They now land on that
 * server's overview instead of on a picker that no longer reads the parameter.
 * Without the search parameter this is just the dashboard home.
 */
function MeOrRedirect() {
  const [searchParams] = useSearchParams();
  const guildId = searchParams.get("guild");
  if (guildId) return <Navigate to={`/me/guilds/${guildId}/overview`} replace />;
  return <DashboardPage />;
}

/** The old home address. `?guild=` on it meant the same thing it means on /me. */
function LegacyHomeRedirect() {
  const [searchParams] = useSearchParams();
  const guildId = searchParams.get("guild");
  return <Navigate to={guildId ? `/me/guilds/${guildId}/overview` : "/me"} replace />;
}

/**
 * The old per-server admin addresses.
 *
 * The query string is carried over deliberately: the settings page picks its
 * open section out of `?s=`, so dropping it would turn a link to one setting
 * into a link to the top of the page.
 */
function LegacyAdminRedirect({ page }: { page: "settings" | "audit-log" }) {
  const { guildId } = useParams();
  const { search } = useLocation();
  return <Navigate to={`/settings/guilds/${guildId}/${page}${search}`} replace />;
}

/**
 * The old builder address.
 *
 * Same reasoning as the admin redirect above, for a different parameter: the
 * builder reads `?mode=` to decide whether it opens on the guide, the info
 * board or the greeting, so a link to one of those must not land on the guide.
 */
function LegacyBuilderRedirect() {
  const { guildId } = useParams();
  const { search } = useLocation();
  return <Navigate to={`/settings/guilds/${guildId}/builder${search}`} replace />;
}

function RedirectAuditLog() {
  const { guildId } = useParams();
  return <Navigate to={`/settings/guilds/${guildId}/audit-log`} replace />;
}
