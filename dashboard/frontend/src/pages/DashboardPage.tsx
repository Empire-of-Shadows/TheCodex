import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type {
  Guild,
  GuildOverview,
  User,
  UserActivity,
  UserEntitlements,
} from "../api/types";
import AppHeader from "../components/AppHeader";
import AdminOverview from "../components/overview/AdminOverview";
import MemberOverview from "../components/overview/MemberOverview";
import MemberEntitlements from "../components/overview/MemberEntitlements";
import ServerPicker, { pickerMeta } from "../_engine/components/overview/ServerPicker";
import SignalStrip, { type Signal } from "../_engine/components/overview/SignalStrip";
import { formatCount } from "../_engine/format";
import { formatError } from "../_engine/api/formatError";

/** What the page is showing for the current selection. */
type Pane =
  | {
      kind: "admin";
      overview: GuildOverview;
      activity: UserActivity | null;
      entitlements: UserEntitlements | null;
    }
  | { kind: "member"; activity: UserActivity; entitlements: UserEntitlements | null }
  | { kind: "none" };

export default function DashboardPage() {
  const [user, setUser] = useState<User | null>(null);
  const [guilds, setGuilds] = useState<Guild[]>([]);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [searchParams, setSearchParams] = useSearchParams();
  const selectedGuildId = searchParams.get("guild");

  const [pane, setPane] = useState<Pane>({ kind: "none" });
  const [paneLoading, setPaneLoading] = useState(true);
  const [paneError, setPaneError] = useState<string | null>(null);

  // The ?guild= value the page was opened with. A link someone shared always
  // wins over the default-to-your-own-server behaviour below.
  const openedWith = useRef<string | null>(searchParams.get("guild"));

  const selectGuild = (guildId: string | null, replace: boolean) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (guildId) next.set("guild", guildId);
        else next.delete("guild");
        return next;
      },
      { replace },
    );
  };

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.me(), api.guilds(), api.botInviteUrl()])
      .then(([me, guildList, invite]) => {
        if (cancelled) return;
        setUser(me);
        setGuilds(guildList);
        setInviteUrl(invite.url);
        if (!openedWith.current) {
          // Land an admin on the server they actually run. Written with
          // replace, so the URL stays shareable and reload-safe either way.
          const own = guildList.find(
            (g) => g.panel_role === "admin" && g.bot_in_guild && !g.setup_required,
          );
          if (own) selectGuild(own.id, true);
        }
      })
      .catch((e) => {
        console.error("Dashboard load failed", e);
        if (cancelled) return;
        if ((e as Error).message === "Unauthorized") return;
        setLoadError(formatError(e, "Failed to load dashboard."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // Runs once: the initial guild comes from the URL, captured above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedGuild = useMemo(
    () => guilds.find((g) => g.id === selectedGuildId) ?? null,
    [guilds, selectedGuildId],
  );

  const isAdminPane =
    selectedGuild !== null &&
    selectedGuild.panel_role === "admin" &&
    selectedGuild.bot_in_guild &&
    !selectedGuild.setup_required;

  useEffect(() => {
    if (loading) return;
    let cancelled = false;
    setPaneLoading(true);
    setPaneError(null);

    // Entitlements are guild-scoped and additive: no guild selected (or the
    // bot missing) means no section, and a failed fetch never takes the rest
    // of the page down with it.
    const entitlementsRequest: Promise<UserEntitlements | null> =
      selectedGuild && selectedGuild.bot_in_guild && !selectedGuild.setup_required
        ? api.getUserEntitlements(selectedGuild.id).then(
            (entitlements) => entitlements,
            (e) => {
              console.error("Entitlements fetch failed", e);
              return null;
            },
          )
        : Promise.resolve(null);

    const request: Promise<Pane> =
      isAdminPane && selectedGuild
        ? Promise.all([
            api.getGuildOverview(selectedGuild.id),
            // Admins get their personal section too. It is additive: if it
            // fails, the server overview still renders alone rather than
            // taking the page down with it.
            api.getUserActivity(selectedGuild.id).then(
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
        : Promise.all([
            api.getUserActivity(selectedGuildId ?? undefined),
            entitlementsRequest,
          ]).then(([activity, entitlements]) => ({
            kind: "member" as const,
            activity,
            entitlements,
          }));

    request
      .then((next) => {
        if (!cancelled) setPane(next);
      })
      .catch((e) => {
        console.error("Dashboard pane fetch failed", e);
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
  }, [loading, isAdminPane, selectedGuild, selectedGuildId]);

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
          <span className="visually-hidden">Loading dashboard…</span>
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

  if (guilds.length === 0) {
    return (
      <div className="app-layout">
        <AppHeader user={user} />
        <div className="page">
          <div className="ov-grid">
            <section className="ov-card ov-card--quiet s12">
              <div className="ov-card__head">
                <span className="ov-card__title">No servers</span>
              </div>
              <p className="ov-body">
                No servers to show yet. Servers appear here when you share one
                with the bot, or when you have Manage Server permission.
              </p>
            </section>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-layout">
      <AppHeader user={user} />

      <div className="page">
        <div className="ov-command">
          <ServerPicker
            guilds={guilds}
            selectedGuildId={selectedGuildId}
            onSelect={(id) => selectGuild(id, true)}
            meta={pickerMeta(selectedGuild, guilds.length, "TheCodex")}
          />
          <SignalStrip signals={signalsFor(pane)} />
        </div>

        {selectedGuild?.setup_required && (
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
                    href={`${inviteUrl}&guild_id=${selectedGuild.id}`}
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
            <span className="visually-hidden">Loading activity…</span>
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
            <AdminOverview overview={pane.overview} />
            {pane.activity && (
              <>
                <h2 className="section-title" style={{ margin: "28px 0 12px" }}>
                  Your activity
                </h2>
                <MemberOverview activity={pane.activity} />
              </>
            )}
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

/* ── The command-row numbers ───────────────────────────────────────── */

function signalsFor(pane: Pane): Signal[] {
  if (pane.kind === "admin") return adminSignals(pane.overview);
  if (pane.kind === "member") return memberSignals(pane.activity);
  return [];
}

function adminSignals(overview: GuildOverview): Signal[] {
  const signals: Signal[] = [];
  const members = overview.members;
  const wyr = overview.wyr;
  const trackers = overview.trackers;

  // null means "never snapshotted", which has to read differently from a real 0.
  signals.push({
    key: "members",
    value: members && members.total !== null ? formatCount(members.total) : "-",
    label: members && members.total !== null ? "Members" : "Members · not counted yet",
  });

  signals.push({
    key: "active",
    value: wyr ? formatCount(wyr.voters_30d) : "-",
    label: "Voted · 30 days",
  });

  const wearing = trackers?.tag.wearing ?? null;
  signals.push({
    key: "tag",
    value: wearing === null ? "-" : formatCount(wearing),
    label:
      !trackers || !trackers.tag.enabled
        ? "Wearing the tag · off"
        : wearing === null
          ? "Wearing the tag · not known"
          : "Wearing the tag",
  });

  signals.push({
    key: "boost",
    value: trackers ? formatCount(trackers.boost.count) : "-",
    label:
      trackers && trackers.boost.tier !== null
        ? `Boosting · level ${trackers.boost.tier}`
        : "Boosting",
  });

  return signals;
}

function memberSignals(activity: UserActivity): Signal[] {
  return [
    { key: "votes", value: formatCount(activity.wyr.total_votes), label: "Votes cast" },
    { key: "streak", value: formatCount(activity.wyr.streak_days), label: "Day streak" },
    {
      key: "suggestions",
      value: formatCount(activity.suggestions.submitted),
      label: "Suggestions sent",
    },
  ];
}
