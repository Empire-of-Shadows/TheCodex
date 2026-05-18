import type { ReactNode } from "react";
import type { User } from "../api/types";

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
        {left}
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