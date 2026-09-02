import { NavLink } from "react-router-dom";

function navClass({ isActive }: { isActive: boolean }) {
  return "nav-button" + (isActive ? " active" : "");
}

/**
 * The tab bar for one server's management pages.
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
  return (
    <nav className="nav-links" style={{ marginBottom: 20 }}>
      <NavLink to="/settings" end className="nav-button">&larr; Your servers</NavLink>
      <NavLink to={`/settings/guilds/${guildId}/settings`} end className={navClass}>
        Settings
      </NavLink>
      <NavLink to={`/settings/guilds/${guildId}/audit-log`} className={navClass}>
        Change history
      </NavLink>
      <NavLink to={`/settings/guilds/${guildId}/builder`} className={navClass}>
        Builder
      </NavLink>
    </nav>
  );
}
