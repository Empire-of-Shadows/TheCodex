import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import type { User } from "../api/types";
import { EcosystemNav } from "./EcosystemNav";

function navClass({ isActive }: { isActive: boolean }) {
  return "nav-button" + (isActive ? " active" : "");
}

interface AppHeaderProps {
  user?: User | null;
  /** Optional override for the title text. Defaults to "TheCodex Dashboard". */
  title?: string;
  /** Slot rendered between the title and the user-info (e.g. builder-page back button + guild badge). */
  left?: ReactNode;
  /** Slot rendered to the right of the user-info (e.g. builder-page mode switch). Replaces user-info if `user` is null. */
  right?: ReactNode;
  /** Hide the user-info block entirely (logo + title only). */
  hideUser?: boolean;
}

export default function AppHeader({
  user,
  title = "TheCodex Dashboard",
  left,
  right,
  hideUser = false,
}: AppHeaderProps) {
  const avatarUrl =
    user?.avatar && user?.id
      ? `https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.png?size=64`
      : null;
  const displayName = user?.global_name || user?.username;

  return (
    <header className="app-header">
      <div style={{ display: "flex", alignItems: "center", gap: 16, minWidth: 0 }}>
        <h1>
          <img src="/brand/logo-mark.png" alt="" />
          <span className="app-header__title-text">{title}</span>
        </h1>
        {/* Builder passes its own `left` (back button + guild badge); elsewhere
            show the primary nav. */}
        {left ?? (user && (
          <nav className="nav-links" style={{ marginLeft: 8 }}>
            <NavLink to="/dashboard" className={navClass}>Stats</NavLink>
            <NavLink to="/me/privacy" className={navClass}>Privacy</NavLink>
            {user.can_access_admin_any && (
              <NavLink to="/admin" className={navClass}>Admin</NavLink>
            )}
            {user.can_access_mod_any && (
              <NavLink to="/mod" className={navClass}>Mod</NavLink>
            )}
          </nav>
        ))}
      </div>
      <div style={{ marginLeft: "auto", marginRight: 12 }}>
        <EcosystemNav />
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        {right}
        {!hideUser && user && (
          <div className="user-info">
            {avatarUrl && <img src={avatarUrl} alt="" />}
            <span>{displayName}</span>
            <a
              href="/auth/logout"
              className="btn btn-secondary"
              style={{ fontSize: 12, padding: "4px 10px" }}
            >
              Logout
            </a>
          </div>
        )}
      </div>
    </header>
  );
}