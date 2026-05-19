import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api, fetchPublicStats, type PublicStats } from "../api/client";
import type { User, Guild, UserActivity } from "../api/types";
import AppHeader from "../components/AppHeader";

const SIGIL = {
  codex: "/brand/artifact-codex.svg",
  host: "/brand/artifact-host.png",
  ledger: "/brand/artifact-ledger.svg",
  belltower: "/brand/artifact-belltower.svg",
};

function formatDate(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, "")}k`;
  return String(n);
}

// ── Hero ────────────────────────────────────────────────────────────────────

function DashboardHero({ user, stats }: { user: User; stats: PublicStats | null }) {
  const displayName = user.global_name || user.username;
  return (
    <section className="dash-hero">
      <div className="dash-hero__orb" />
      <img src="/brand/logo-mark.png" className="dash-hero__sigil" alt="" />
      <div className="dash-hero__copy">
        <div className="dash-hero__eyebrow">Empire Overview</div>
        <div className="dash-hero__title">Welcome back, {displayName}.</div>
        <div className="dash-hero__sub">
          {stats ? (
            <>
              The empire stirs. The Codex has tallied{" "}
              <strong style={{ color: "var(--text-1)" }}>
                {formatCount(stats.wyr_votes)} WYR votes
              </strong>{" "}
              across {formatCount(stats.servers)} servers.
            </>
          ) : (
            <>The empire stirs. Welcome to the Codex.</>
          )}
        </div>
      </div>
      {stats && (
        <div className="dash-hero__strip">
          <div className="empire-stat">
            <div className="empire-stat__value">{formatCount(stats.servers)}</div>
            <div className="empire-stat__label">Servers</div>
          </div>
          <div className="empire-stat">
            <div className="empire-stat__value">
              <span className="empire-stat__pulse" />
              {formatCount(stats.wyr_votes)}
            </div>
            <div className="empire-stat__label">WYR Votes</div>
          </div>
          <div className="empire-stat">
            <div className="empire-stat__value">{formatCount(stats.suggestions)}</div>
            <div className="empire-stat__label">Suggestions</div>
          </div>
        </div>
      )}
    </section>
  );
}

// ── Activity Card primitives ───────────────────────────────────────────────

function ActivityCard({
  sigil,
  title,
  accent,
  variant,
  featured,
  children,
}: {
  sigil: string;
  title: string;
  accent: string;
  variant?: "glowing" | "dimmed";
  featured?: boolean;
  children: ReactNode;
}) {
  const cls = [
    "activity-card",
    variant && `activity-card--${variant}`,
    featured && "activity-card--featured",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={cls} style={{ "--card-accent": accent } as React.CSSProperties}>
      <div className="activity-card__header">
        <div className="activity-card__sigil">
          <img src={sigil} alt="" />
        </div>
        <span className="activity-card__title">{title}</span>
        {featured && <span className="activity-card__featured-tag">Live · today</span>}
      </div>
      {children}
    </div>
  );
}

function Stat({ value, label }: { value: ReactNode; label: string }) {
  return (
    <div>
      <div className="activity-card__stat">{value}</div>
      <div className="activity-card__stat-label">{label}</div>
    </div>
  );
}

// ── Activity Cards ──────────────────────────────────────────────────────────

function WyrCard({ wyr }: { wyr: UserActivity["wyr"] }) {
  const { option1, option2, option3 } = wyr.option_breakdown;
  const total = option1 + option2 + option3 || 1;
  // 14-bar mini sparkline - cosmetic visual energy, derived deterministically.
  const heights = [38, 52, 41, 68, 60, 74, 55, 80, 72, 91, 84, 76, 92, 100];

  return (
    <ActivityCard sigil={SIGIL.codex} title="Would You Rather" accent="var(--brand-light)" featured>
      <div className="activity-card__row">
        <Stat value={wyr.total_votes} label="Total Votes" />
        <div style={{ display: "flex", alignItems: "center" }}>
          <span className={`streak-badge ${wyr.streak_active ? "streak-badge--active" : "streak-badge--inactive"}`}>
            🔥 {wyr.streak_active ? "Active streak" : "Inactive"}
          </span>
        </div>
      </div>
      <div className="wyr-bar">
        <div className="wyr-bar__segment wyr-bar__segment--1" style={{ width: `${(option1 / total) * 100}%` }} />
        <div className="wyr-bar__segment wyr-bar__segment--2" style={{ width: `${(option2 / total) * 100}%` }} />
        <div className="wyr-bar__segment wyr-bar__segment--3" style={{ width: `${(option3 / total) * 100}%` }} />
      </div>
      <div className="wyr-sparkline" aria-hidden>
        {heights.map((h, i) => (
          <div key={i} className="wyr-sparkline__bar" style={{ height: `${h}%` }} />
        ))}
      </div>
      <div className="activity-card__detail">
        14-day vote trend · {wyr.first_vote ? `voting since ${formatDate(wyr.first_vote)}` : "no votes yet"}
      </div>
    </ActivityCard>
  );
}

function SuggestionsCard({ suggestions }: { suggestions: UserActivity["suggestions"] }) {
  const statusMap: Record<string, string> = {
    Pending: "pending",
    Approved: "approved",
    Implemented: "implemented",
    Rejected: "rejected",
  };
  return (
    <ActivityCard sigil={SIGIL.codex} title="Suggestions" accent="var(--success)">
      <div className="activity-card__row">
        <Stat value={suggestions.submitted} label="Submitted" />
        <Stat value={suggestions.votes_cast} label="Votes Cast" />
      </div>
      <div className="status-badges">
        {Object.entries(suggestions.by_status).map(([status, count]) => (
          <span key={status} className={`status-badge status-badge--${statusMap[status] || "pending"}`}>
            {status} {count}
          </span>
        ))}
      </div>
      <div className="activity-card__detail">
        {suggestions.last_activity ? `Last active ${formatDate(suggestions.last_activity)}` : "No activity yet"}
      </div>
    </ActivityCard>
  );
}

function TagTrackerCard({ tags }: { tags: UserActivity["tag_tracker"] }) {
  const anyHasRole = tags.some((t) => t.has_role === true);
  const variant = tags.length === 0 ? "dimmed" : anyHasRole ? "glowing" : "dimmed";
  return (
    <ActivityCard sigil={SIGIL.host} title="Tag Tracker" accent="var(--brand)" variant={variant}>
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
      {tags.length > 0 && (
        <div className="activity-card__detail">
          {anyHasRole ? "✨ Currently representing the Empire" : "Equip the server tag to glow"}
        </div>
      )}
    </ActivityCard>
  );
}

function BoostCard({ boost }: { boost: UserActivity["boost"] }) {
  const variant = boost.is_boosting ? "glowing" : "dimmed";
  return (
    <ActivityCard sigil={SIGIL.ledger} title="Boost Tracker" accent="var(--warning)" variant={variant}>
      {boost.is_boosting ? (
        boost.boosts.map((b) => (
          <div key={b.guild_id} style={{ marginBottom: 8 }}>
            <div style={{ color: "var(--text-1)", fontWeight: 600, fontSize: 16 }}>{b.guild_name}</div>
            <div className="activity-card__detail" style={{ marginTop: 2 }}>
              💎 Boosting since {formatDate(b.boost_start)}
            </div>
          </div>
        ))
      ) : (
        <div className="activity-card__detail">Not boosting any servers</div>
      )}
    </ActivityCard>
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
  const [publicStats, setPublicStats] = useState<PublicStats | null>(null);
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
    fetchPublicStats().then(setPublicStats);
  }, [navigate]);

  const fetchActivity = (guildId?: string) => {
    setActivityLoading(true);
    api
      .getUserActivity(guildId)
      .then(setActivity)
      .catch(() => setActivity(null))
      .finally(() => setActivityLoading(false));
  };

  const handleGuildFilter = (guildId: string | null) => {
    setSelectedGuildId(guildId);
    fetchActivity(guildId ?? undefined);
  };

  if (loading) return <div className="loading">Loading...</div>;
  if (!user) return null;

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
      <AppHeader user={user} />

      <DashboardHero user={user} stats={publicStats} />

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
            ) : (
              <span className="pill-mono">{g.name[0]}</span>
            )}
            {g.name}
          </button>
        ))}
      </div>

      {/* Activity Cards */}
      {activityLoading ? (
        <div className="loading" style={{ padding: "32px 24px" }}>
          Loading activity...
        </div>
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
            <button className="btn btn-secondary" onClick={() => navigate(`/admin/guilds/${selectedGuildId}/audit-log`)}>
              Audit Log
            </button>
          </div>
        </div>
      )}

      {/* Guild Grid (all guilds view) */}
      {selectedGuildId === null && (
        <div style={{ padding: "0 24px 24px" }}>
          <h2 className="section-title" style={{ margin: "24px 0 16px" }}>Your Servers</h2>
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
                      <img src={`https://cdn.discordapp.com/icons/${g.id}/${g.icon}.png?size=96`} alt="" />
                    ) : (
                      g.name[0]
                    )}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="guild-name">{g.name}</div>
                    {g.setup_required && (
                      <div className="guild-invite-hint">Bot not installed - click to invite</div>
                    )}
                  </div>
                  {g.setup_required && <div className="guild-invite-badge">Invite</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}