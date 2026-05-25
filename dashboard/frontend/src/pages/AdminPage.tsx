import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Guild, User } from "../api/types";
import AppHeader from "../components/AppHeader";
import { GuildWeb } from "../components/GuildWeb";

export default function AdminPage() {
  const [user, setUser] = useState<User | null>(null);
  const [guilds, setGuilds] = useState<Guild[] | null>(null);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.me().then(setUser).catch(() => {});
    api.guilds().then(setGuilds).catch((e) => setError(String(e)));
    api.botInviteUrl().then((r) => setInviteUrl(r.url)).catch(() => {});
  }, []);

  // Client guard: admins reach this page; pure-mod users have no Admin nav link.
  useEffect(() => {
    if (user && !user.can_access_admin_any) navigate("/dashboard", { replace: true });
  }, [user, navigate]);

  const webGuilds = useMemo(
    () => (guilds ?? []).filter((g) => g.panel_role !== "none"),
    [guilds],
  );
  const counts = useMemo(() => ({
    total: webGuilds.length,
    admin: webGuilds.filter((g) => g.panel_role === "admin").length,
    mod: webGuilds.filter((g) => g.panel_role === "mod").length,
  }), [webGuilds]);
  const selected = webGuilds.find((g) => g.id === selectedId) ?? null;

  return (
    <div className="app-layout">
      <AppHeader user={user} />

      <section className="dash-hero">
        <div className="dash-hero__orb" />
        <img className="dash-hero__sigil" src="/brand/logo-mark.png" alt="" />
        <div className="dash-hero__copy">
          <span className="dash-hero__eyebrow">Configuration</span>
          <h1 className="dash-hero__title">The Web of Servers</h1>
          <p className="dash-hero__sub">
            Every server you steward, woven together. Pluck a node to manage it.
          </p>
        </div>
        <div className="dash-hero__strip">
          <div className="empire-stat">
            <div className="empire-stat__value">{counts.total}</div>
            <div className="empire-stat__label">Servers</div>
          </div>
          <div className="empire-stat">
            <div className="empire-stat__value">{counts.admin}</div>
            <div className="empire-stat__label">Admin</div>
          </div>
          <div className="empire-stat">
            <div className="empire-stat__value">{counts.mod}</div>
            <div className="empire-stat__label">Mod</div>
          </div>
        </div>
      </section>

      <div style={{ padding: "0 24px 24px" }}>
        {error ? (
          <div className="alert danger">{error}</div>
        ) : !guilds ? (
          <p className="muted">Loading servers...</p>
        ) : webGuilds.length === 0 ? (
          <div className="card">
            <h3>No manageable servers</h3>
            <p className="muted">
              You need MANAGE_SERVER permission (or a configured panel role) in a Discord
              server to manage TheCodex.
              {inviteUrl && (
                <>
                  {" "}
                  <a href={inviteUrl} target="_blank" rel="noreferrer">Invite TheCodex to a server</a>.
                </>
              )}
            </p>
          </div>
        ) : (
          <div className="guild-web-layout">
            <GuildWeb guilds={webGuilds} selectedId={selectedId} onSelect={setSelectedId} />
            <AdminActionPanel
              guild={selected}
              inviteUrl={inviteUrl}
              onNavigate={(path) => navigate(path)}
              onInvite={(gid) => inviteUrl && window.open(`${inviteUrl}&guild_id=${gid}`, "_blank")}
            />
          </div>
        )}
      </div>
    </div>
  );
}

function AdminActionPanel({
  guild,
  inviteUrl,
  onNavigate,
  onInvite,
}: {
  guild: Guild | null;
  inviteUrl: string | null;
  onNavigate: (path: string) => void;
  onInvite: (gid: string) => void;
}) {
  if (!guild) {
    return (
      <aside className="card guild-web__panel guild-web__panel--empty">
        <p className="muted" style={{ margin: 0 }}>Select a server node to manage it.</p>
      </aside>
    );
  }

  const iconUrl = guild.icon
    ? `https://cdn.discordapp.com/icons/${guild.id}/${guild.icon}.png?size=64`
    : null;
  const isAdmin = guild.panel_role === "admin";

  return (
    <aside className="card guild-web__panel">
      <div className="guild-web__panel-head">
        <div className="guild-icon" style={{ width: 44, height: 44 }}>
          {iconUrl ? <img src={iconUrl} alt="" /> : (guild.name ?? "?")[0]}
        </div>
        <div style={{ minWidth: 0 }}>
          <div className="guild-name" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {guild.name}
          </div>
          <span className={`status-badge ${isAdmin ? "status-badge--approved" : "status-badge--pending"}`}>
            {isAdmin ? "Admin" : "Mod"}
          </span>
        </div>
      </div>

      <div className="guild-web__panel-actions">
        {!guild.bot_in_guild ? (
          inviteUrl && (
            <button className="btn btn-primary" onClick={() => onInvite(guild.id)}>
              Invite TheCodex
            </button>
          )
        ) : isAdmin ? (
          <>
            <button className="btn btn-primary" onClick={() => onNavigate(`/builder/${guild.id}`)}>
              Edit Guide
            </button>
            <button className="btn btn-secondary" onClick={() => onNavigate(`/builder/${guild.id}`)}>
              Edit Welcome
            </button>
            <button className="btn btn-secondary" onClick={() => onNavigate(`/settings/${guild.id}`)}>
              Settings
            </button>
            <button className="btn btn-secondary" onClick={() => onNavigate(`/admin/guilds/${guild.id}/audit-log`)}>
              Audit Log
            </button>
          </>
        ) : (
          <p className="guild-invite-hint" style={{ margin: 0 }}>
            Moderator access. Management tools are coming soon.
          </p>
        )}
      </div>

      {!guild.bot_in_guild && (
        <p className="guild-invite-hint" style={{ marginTop: 0 }}>Bot not in this server yet.</p>
      )}
    </aside>
  );
}
