import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { User, Guild, UserActivity } from "../api/types";

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

// ── Activity Cards ──────────────────────────────────────────────────────────

function WyrCard({ wyr }: { wyr: UserActivity["wyr"] }) {
  const { option1, option2, option3 } = wyr.option_breakdown;
  const total = option1 + option2 + option3 || 1;

  return (
    <div className="activity-card">
      <div className="activity-card__header">
        <span className="activity-card__icon">🎲</span>
        <span className="activity-card__title">Would You Rather</span>
      </div>
      <div className="activity-card__row">
        <div>
          <div className="activity-card__stat">{wyr.total_votes}</div>
          <div className="activity-card__stat-label">Total Votes</div>
        </div>
        <div style={{ display: "flex", alignItems: "center" }}>
          <span className={`streak-badge ${wyr.streak_active ? "streak-badge--active" : "streak-badge--inactive"}`}>
            🔥 {wyr.streak_active ? "Active" : "Inactive"}
          </span>
        </div>
      </div>
      <div className="wyr-bar">
        <div className="wyr-bar__segment wyr-bar__segment--1" style={{ width: `${(option1 / total) * 100}%` }} />
        <div className="wyr-bar__segment wyr-bar__segment--2" style={{ width: `${(option2 / total) * 100}%` }} />
        <div className="wyr-bar__segment wyr-bar__segment--3" style={{ width: `${(option3 / total) * 100}%` }} />
      </div>
      <div className="activity-card__detail">
        {wyr.first_vote ? `Voting since ${formatDate(wyr.first_vote)}` : "No votes yet"}
      </div>
    </div>
  );
}

function SuggestionsCard({ suggestions }: { suggestions: UserActivity["suggestions"] }) {
  const statusColors: Record<string, string> = {
    Pending: "pending",
    Approved: "approved",
    Implemented: "implemented",
    Rejected: "rejected",
  };

  return (
    <div className="activity-card">
      <div className="activity-card__header">
        <span className="activity-card__icon">💡</span>
        <span className="activity-card__title">Suggestions</span>
      </div>
      <div className="activity-card__row">
        <div>
          <div className="activity-card__stat">{suggestions.submitted}</div>
          <div className="activity-card__stat-label">Submitted</div>
        </div>
        <div>
          <div className="activity-card__stat">{suggestions.votes_cast}</div>
          <div className="activity-card__stat-label">Votes Cast</div>
        </div>
      </div>
      <div className="status-badges">
        {Object.entries(suggestions.by_status).map(([status, count]) => (
          <span key={status} className={`status-badge status-badge--${statusColors[status] || "pending"}`}>
            {status} {count}
          </span>
        ))}
      </div>
      <div className="activity-card__detail">
        {suggestions.last_activity ? `Last active ${formatDate(suggestions.last_activity)}` : "No activity yet"}
      </div>
    </div>
  );
}

function TagTrackerCard({ tags }: { tags: UserActivity["tag_tracker"] }) {
  const anyHasRole = tags.some((t) => t.has_role === true);
  const cardClass = tags.length === 0
    ? "activity-card activity-card--dimmed"
    : anyHasRole
      ? "activity-card activity-card--glowing"
      : "activity-card activity-card--dimmed";

  return (
    <div className={cardClass}>
      <div className="activity-card__header">
        <span className="activity-card__icon">🏷️</span>
        <span className="activity-card__title">Tag Tracker</span>
      </div>
      {tags.length === 0 ? (
        <div className="activity-card__detail">No guilds with tag tracking enabled</div>
      ) : (
        tags.map((t) => (
          <div key={t.guild_id} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span className="tag-display">{t.server_tag}</span>
            <span style={{ color: "var(--text-muted)", fontSize: 13 }}>{t.guild_name}</span>
            <span style={{ marginLeft: "auto", fontSize: 16 }}>
              {t.has_role === true ? "✅" : t.has_role === false ? "❌" : "❓"}
            </span>
          </div>
        ))
      )}
      {tags.length > 0 && !anyHasRole && (
        <div className="activity-card__detail">Not representing</div>
      )}
    </div>
  );
}

function BoostCard({ boost }: { boost: UserActivity["boost"] }) {
  const cardClass = boost.is_boosting ? "activity-card activity-card--glowing" : "activity-card activity-card--dimmed";

  return (
    <div className={cardClass} style={boost.is_boosting ? { borderColor: "rgba(155, 89, 182, 0.5)" } : undefined}>
      <div className="activity-card__header">
        <span className="activity-card__icon">💎</span>
        <span className="activity-card__title">Boost Tracker</span>
      </div>
      {boost.is_boosting ? (
        boost.boosts.map((b) => (
          <div key={b.guild_id} style={{ marginBottom: 8 }}>
            <div style={{ color: "var(--text-1)", fontWeight: 600, fontSize: 14 }}>{b.guild_name}</div>
            <div className="activity-card__detail" style={{ marginTop: 2 }}>
              Boosting since {formatDate(b.boost_start)}
            </div>
          </div>
        ))
      ) : (
        <div className="activity-card__detail">Not boosting any servers</div>
      )}
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [user, setUser] = useState<User | null>(null);
  const [guilds, setGuilds] = useState<Guild[]>([]);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedGuildId, setSelectedGuildId] = useState<string | null>(null);
  const [activity, setActivity] = useState<UserActivity | null>(null);
  const [activityLoading, setActivityLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([api.me(), api.guilds(), api.botInviteUrl(), api.getUserActivity()])
      .then(([u, g, invite, act]) => {
        setUser(u);
        setGuilds(g);
        setInviteUrl(invite.url);
        setActivity(act);
      })
      .catch(() => navigate("/login"))
      .finally(() => setLoading(false));
  }, [navigate]);

  const fetchActivity = (guildId?: string) => {
    setActivityLoading(true);
    api.getUserActivity(guildId)
      .then(setActivity)
      .catch(() => setActivity(null))
      .finally(() => setActivityLoading(false));
  };

  const handleGuildFilter = (guildId: string | null) => {
    setSelectedGuildId(guildId);
    fetchActivity(guildId ?? undefined);
  };

  if (loading) return <div className="loading">Loading...</div>;

  const avatarUrl = user?.avatar
    ? `https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.png?size=64`
    : null;

  const botGuilds = guilds.filter((g) => g.bot_in_guild);

  const handleGuildClick = (guild: Guild) => {
    if (guild.setup_required && inviteUrl) {
      window.open(`${inviteUrl}&guild_id=${guild.id}`, "_blank");
    } else {
      navigate(`/builder/${guild.id}`);
    }
  };

  return (
    <div className="app-layout">
      <header className="app-header">
        <h1>ImperialCodex Dashboard</h1>
        <div className="user-info">
          {avatarUrl && <img src={avatarUrl} alt="" />}
          <span>{user?.global_name || user?.username}</span>
          <a href="/auth/logout" className="btn btn-secondary" style={{ fontSize: 12, padding: "4px 10px" }}>
            Logout
          </a>
        </div>
      </header>

      {/* Guild Filter Bar */}
      <div className="guild-filter-bar">
        <button
          className={`guild-pill${selectedGuildId === null ? " active" : ""}`}
          onClick={() => handleGuildFilter(null)}
        >
          All Guilds
        </button>
        {botGuilds.map((g) => (
          <button
            key={g.id}
            className={`guild-pill${selectedGuildId === g.id ? " active" : ""}`}
            onClick={() => handleGuildFilter(g.id)}
          >
            {g.icon ? (
              <img src={`https://cdn.discordapp.com/icons/${g.id}/${g.icon}.png?size=32`} alt="" />
            ) : null}
            {g.name}
          </button>
        ))}
      </div>

      {/* Activity Cards */}
      {activityLoading ? (
        <div className="loading" style={{ padding: "32px 24px" }}>Loading activity...</div>
      ) : activity ? (
        <div className="activity-grid">
          <WyrCard wyr={activity.wyr} />
          <SuggestionsCard suggestions={activity.suggestions} />
          <TagTrackerCard tags={activity.tag_tracker} />
          <BoostCard boost={activity.boost} />
        </div>
      ) : null}

      {/* Admin Section */}
      {selectedGuildId && (
        <div className="admin-section">
          <h3>Admin</h3>
          <div className="admin-actions">
            <button className="btn btn-primary" onClick={() => navigate(`/builder/${selectedGuildId}`)}>
              Edit Guide
            </button>
            <button className="btn btn-secondary" onClick={() => navigate(`/builder/${selectedGuildId}`)}>
              Edit Welcome
            </button>
          </div>
        </div>
      )}

      {/* Guild Grid (all guilds view) */}
      {selectedGuildId === null && (
        <div style={{ padding: "0 24px 24px" }}>
          <h2 style={{ color: "var(--text-1)", marginBottom: 16 }}>Your Servers</h2>
          {guilds.length === 0 ? (
            <p style={{ color: "var(--text-muted)" }}>
              No servers found where you have Manage Server permission.
            </p>
          ) : (
            <div className="guild-grid">
              {guilds.map((g) => (
                <div
                  key={g.id}
                  className={`card guild-card${g.setup_required ? " guild-card--setup" : ""}`}
                  onClick={() => handleGuildClick(g)}
                >
                  <div className="guild-icon">
                    {g.icon ? (
                      <img
                        src={`https://cdn.discordapp.com/icons/${g.id}/${g.icon}.png?size=96`}
                        alt=""
                      />
                    ) : (
                      g.name[0]
                    )}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="guild-name">{g.name}</div>
                    {g.setup_required && (
                      <div className="guild-invite-hint">Bot not installed — click to invite</div>
                    )}
                  </div>
                  {g.setup_required && (
                    <div className="guild-invite-badge">Invite</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
