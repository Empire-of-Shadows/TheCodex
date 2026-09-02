import { NavLink } from "react-router-dom";
import type { PanelRole } from "../api/types";

function navClass({ isActive }: { isActive: boolean }) {
  return "nav-button" + (isActive ? " active" : "");
}

/**
 * The per-guild tab bar every member page for one server carries.
 *
 * It exists because a server used to be a selection on the dashboard home
 * rather than a place you go, so there was nothing on screen telling you which
 * pages a server has. Now every per-guild page is a path, and this bar is how
 * you move between them and back out to the server list.
 *
 * Codex has exactly one member page per server today - the overview - so the
 * bar is short on purpose. It is still worth rendering: it names where you are,
 * and it is the way back to the picker. New member pages for a server become
 * tabs here; nothing else should grow its own back link.
 *
 * "Servers" goes to /me because that is codex's member home, the page holding
 * the server picker and your activity across all of them.
 *
 * The Settings tab is HIDDEN for a non-admin, not enforced here - every admin
 * route re-checks the tier server-side, so a link is never what grants access.
 * A server the bot has not been added to (`setupRequired`) has nothing to
 * manage yet, so it does not get the tab at all: a dead end sitting next to an
 * invite card reads as broken rather than as empty.
 */
export default function GuildNav({
  guildId,
  panelRole,
  setupRequired = false,
}: {
  guildId: string;
  panelRole?: PanelRole;
  setupRequired?: boolean;
}) {
  const canSeeSettings = panelRole === "admin" && !setupRequired;
  return (
    <nav className="nav-links" style={{ marginBottom: 20 }}>
      <NavLink to="/me" end className="nav-button">&larr; Servers</NavLink>
      <NavLink to={`/me/guilds/${guildId}/overview`} className={navClass}>Overview</NavLink>
      {canSeeSettings && (
        <NavLink to={`/settings/guilds/${guildId}/settings`} end className={navClass}>
          Settings
        </NavLink>
      )}
    </nav>
  );
}
