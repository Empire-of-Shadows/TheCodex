import { NavLink, useSearchParams } from "react-router-dom";

function navClass({ isActive }: { isActive: boolean }) {
  return "nav-button" + (isActive ? " active" : "");
}

/** Marks an admin link as opened from a server's overview, so the admin tree's
 *  back link returns there instead of to the settings hub.
 *
 *  A query parameter rather than router state on purpose: the settings and audit
 *  log pages rewrite their own query string (`?s=`, `?section=`), which would
 *  drop router state but merges into existing parameters, and the vendored
 *  FeatureStrip only takes a plain href string. */
export function fromOverview(path: string): string {
  return path + (path.includes("?") ? "&" : "?") + "from=overview";
}

/** For a link from one admin page to another: keeps the from-overview marker
 *  when the current page carries it, so the way back survives the move. */
export function useAdminHref(): (path: string) => string {
  const [searchParams] = useSearchParams();
  const cameFromOverview = searchParams.get("from") === "overview";
  return (path) => (cameFromOverview ? fromOverview(path) : path);
}

/**
 * The tab bar for one server's management pages.
 *
 * The back link follows where the admin came in. Opened from the server's
 * overview (the member side), it returns to that overview and every tab keeps
 * the marker so the way back survives moving between tabs. Opened from the
 * settings hub, or from a bare link, it returns to the hub.
 *
 * The admin tree navigates within itself instead of dropping back into the
 * member pages: from settings you could only reach the change history through
 * a link buried in the settings rail, and the builder could only be reached by
 * going back to the web of servers and picking the same node again.
 *
 * Every tab is always shown. Hiding a link was never the gate - the server
 * re-checks panel access on every read and every write, so a link an admin
 * should not have leads to a refusal rather than to data.
 *
 * All three pages are siblings under one server's Manage path
 * (`/settings/guilds/<id>/...`) rather than nested inside each other, so no tab
 * is a prefix of another and none of them can stay lit on a neighbour's page.
 * The Settings tab keeps its `end` so that stays true if a page is ever added
 * beneath it.
 *
 * Builder opens the component builder in its guide mode; the greeting and
 * board modes are switches inside that page rather than routes of their own,
 * so they are not tabs here.
 */
export default function AdminNav({ guildId }: { guildId: string }) {
  const [searchParams] = useSearchParams();
  const cameFromOverview = searchParams.get("from") === "overview";
  const tab = useAdminHref();
  return (
    <nav className="nav-links" style={{ marginBottom: 20 }}>
      {cameFromOverview ? (
        <NavLink to={`/me/guilds/${guildId}/overview`} end className="nav-button">
          &larr; Overview
        </NavLink>
      ) : (
        <NavLink to="/settings" end className="nav-button">&larr; Your servers</NavLink>
      )}
      <NavLink to={tab(`/settings/guilds/${guildId}/settings`)} end className={navClass}>
        Settings
      </NavLink>
      <NavLink to={tab(`/settings/guilds/${guildId}/audit-log`)} className={navClass}>
        Change history
      </NavLink>
      <NavLink to={tab(`/settings/guilds/${guildId}/builder`)} className={navClass}>
        Builder
      </NavLink>
    </nav>
  );
}
