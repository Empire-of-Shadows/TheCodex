import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import type {
  Guild,
  GuildOverview,
  User,
  UserActivity,
  UserEntitlements,
} from "../api/types";
import AppHeader from "../components/AppHeader";
import GuildNav from "../components/GuildNav";
import AdminOverview from "../components/overview/AdminOverview";
import MemberOverview from "../components/overview/MemberOverview";
import MemberEntitlements from "../components/overview/MemberEntitlements";
import { adminSignals, memberSignals } from "../components/overview/signals";
import SignalStrip, { type Signal } from "../_engine/components/overview/SignalStrip";
import { formatError } from "../_engine/api/formatError";

/**
 * One server, from where the member stands in it.
 *
 * This is everything the dashboard home used to render inline once you picked
 * a server with `?guild=`: your activity here, what this server lets you use,
 * and - for someone who manages it - the server overview underneath. The home
 * kept it behind a query parameter while every other page of the dashboard is
 * addressed by a path, so a shared link was the odd one out and the server had
 * no page of its own to link to. It has one now, and the home is the picker
 * plus your activity across all of your servers.
 *
 * Nothing was dropped in the move. The invite card for a server the bot has
 * not been added to came with it, and so did the rule that an admin is a
 * member first: their own activity sits above the server sections.
 */

/** What the page is showing for this server. */
type Pane =
  | {
      kind: "admin";
      overview: GuildOverview;
      activity: UserActivity | null;
      entitlements: UserEntitlements | null;
    }
  | { kind: "member"; activity: UserActivity; entitlements: UserEntitlements | null }
  | { kind: "none" };

export default function OverviewPage() {
  const { guildId = "" } = useParams();

  const [user, setUser] = useState<User | null>(null);
  const [guilds, setGuilds] = useState<Guild[]>([]);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [pane, setPane] = useState<Pane>({ kind: "none" });
  const [paneLoading, setPaneLoading] = useState(true);
  const [paneError, setPaneError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.me(), api.guilds(), api.botInviteUrl()])
      .then(([me, guildList, invite]) => {
        if (cancelled) return;
        setUser(me);
        setGuilds(guildList);
        setInviteUrl(invite.url);
      })
      .catch((e) => {
        console.error("Overview load failed", e);
        if (cancelled) return;
        if ((e as Error).message === "Unauthorized") return;
        setLoadError(formatError(e, "Failed to load this server."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const guild = useMemo(
    () => guilds.find((g) => g.id === guildId) ?? null,
    [guilds, guildId],
  );

  // The server overview is the admin half of the page. A guild the member only
  // belongs to, or one the bot is not in yet, has none to read.
  const isAdminPane =
    guild !== null &&
    guild.panel_role === "admin" &&
    guild.bot_in_guild &&
    !guild.setup_required;

  useEffect(() => {
    if (loading) return;
    let cancelled = false;
    setPaneLoading(true);
    setPaneError(null);

    // Entitlements are additive: a server the bot is not in has none, and a
    // failed fetch never takes the rest of the page down with it.
    const entitlementsRequest: Promise<UserEntitlements | null> =
      guild && guild.bot_in_guild && !guild.setup_required
        ? api.getUserEntitlements(guild.id).then(
            (entitlements) => entitlements,
            (e) => {
              console.error("Entitlements fetch failed", e);
              return null;
            },
          )
        : Promise.resolve(null);

    const request: Promise<Pane> = isAdminPane
      ? Promise.all([
          api.getGuildOverview(guildId),
          // Admins get their personal section too. It is additive: if it
          // fails, the server overview still renders alone rather than
          // taking the page down with it.
          api.getUserActivity(guildId).then(
            (activity) => activity,
            (e) => {
              console.error("Personal activity fetch failed", e);
              return null;
            },
          ),
          entitlementsRequest,
        ]).then(([overview, activity, entitlements]) => ({
          kind: "admin" as const,
          overview,
          activity,
          entitlements,
        }))
      : Promise.all([api.getUserActivity(guildId), entitlementsRequest]).then(
          ([activity, entitlements]) => ({
            kind: "member" as const,
            activity,
            entitlements,
          }),
        );

    request
      .then((next) => {
        if (!cancelled) setPane(next);
      })
      .catch((e) => {
        console.error("Overview pane fetch failed", e);
        if (cancelled) return;
        setPane({ kind: "none" });
        if ((e as Error).message === "Unauthorized") return;
        setPaneError(formatError(e, "Could not load this server."));
      })
      .finally(() => {
        if (!cancelled) setPaneLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [loading, isAdminPane, guild, guildId]);

  if (loading) {
    return (
      <div className="app-layout">
        <div className="page-skeleton" role="status" aria-busy="true">
          <div className="skeleton-bar skeleton-bar--lg" />
          <div className="skeleton-grid">
            <div className="skeleton-card" />
            <div className="skeleton-card" />
            <div className="skeleton-card" />
            <div className="skeleton-card" />
          </div>
          <span className="visually-hidden">Loading this server</span>
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="app-layout">
        <div className="loading" role="alert">
          {loadError}
        </div>
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="app-layout">
      <AppHeader user={user} />

      <div className="page">
        <GuildNav
          guildId={guildId}
          panelRole={guild?.panel_role}
          setupRequired={guild?.setup_required ?? false}
        />

        <section className="dash-hero" style={{ padding: "4px 0 8px" }}>
          <div className="dash-hero__copy">
            <span className="dash-hero__eyebrow">{guild?.name ?? "Server"}</span>
            <h1 className="dash-hero__title">Overview</h1>
            <p className="dash-hero__sub">
              Where you stand in this server, and what it lets you use.
            </p>
          </div>
        </section>

        <div className="ov-command">
          <SignalStrip signals={signalsFor(pane)} />
        </div>

        {guild?.setup_required && (
          <div className="ov-grid">
            <section className="ov-card ov-card--quiet s12">
              <div className="ov-card__head">
                <span className="ov-card__title">Not added yet</span>
                <span className="ov-chip ov-chip--warn">Bot missing</span>
              </div>
              <p className="ov-body">
                Bot not in this server yet. Use the link below to add it, then return here.
              </p>
              <div className="admin-actions">
                {inviteUrl ? (
                  <a
                    className="btn btn-primary"
                    href={`${inviteUrl}&guild_id=${guild.id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Invite TheCodex
                  </a>
                ) : (
                  <span className="guild-invite-hint">Bot not in this server yet.</span>
                )}
              </div>
            </section>
          </div>
        )}

        {paneLoading ? (
          <div className="ov-grid" role="status" aria-busy="true">
            <div className="skeleton-card s12" />
            <div className="skeleton-card s7" />
            <div className="skeleton-card s5" />
            <div className="skeleton-card s4" />
            <span className="visually-hidden">Loading activity</span>
          </div>
        ) : paneError ? (
          <div className="ov-grid">
            <section className="ov-card ov-card--quiet s12">
              <div className="ov-card__head">
                <span className="ov-card__title">Not loaded</span>
              </div>
              <p className="ov-body" role="alert">
                {paneError}
              </p>
            </section>
          </div>
        ) : pane.kind === "admin" ? (
          <>
            {/* Owner ruling 2026-08-13: an admin is a member first - their own
                stats sit above the server sections. */}
            {pane.activity && (
              <>
                <h2 className="section-title" style={{ margin: "4px 0 12px" }}>
                  Your activity
                </h2>
                <MemberOverview activity={pane.activity} />
              </>
            )}
            <h2 className="section-title" style={{ margin: "28px 0 12px" }}>
              Server overview
            </h2>
            <AdminOverview overview={pane.overview} />
            {pane.entitlements && (
              <>
                <h2 className="section-title" style={{ margin: "28px 0 12px" }}>
                  What you can use
                </h2>
                <MemberEntitlements entitlements={pane.entitlements} />
              </>
            )}
          </>
        ) : pane.kind === "member" ? (
          <>
            <MemberOverview activity={pane.activity} />
            {pane.entitlements && (
              <>
                <h2 className="section-title" style={{ margin: "28px 0 12px" }}>
                  What you can use
                </h2>
                <MemberEntitlements entitlements={pane.entitlements} />
              </>
            )}
          </>
        ) : (
          <div className="empty-state" role="status" style={{ padding: "32px 24px" }}>
            No activity yet - once you use Codex features (WYR, suggestions, tag tracker, boosts),
            they'll show up here.
          </div>
        )}
      </div>
    </div>
  );
}

function signalsFor(pane: Pane): Signal[] {
  if (pane.kind === "admin") return adminSignals(pane.overview);
  if (pane.kind === "member") return memberSignals(pane.activity);
  return [];
}
