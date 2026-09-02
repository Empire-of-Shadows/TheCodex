import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Guild, User, UserActivity } from "../api/types";
import AppHeader from "../components/AppHeader";
import MemberOverview from "../components/overview/MemberOverview";
import { memberSignals } from "../components/overview/signals";
import ServerPicker, { pickerMeta } from "../_engine/components/overview/ServerPicker";
import SignalStrip from "../_engine/components/overview/SignalStrip";
import { formatError } from "../_engine/api/formatError";

/**
 * The dashboard home.
 *
 * Two things, and only these two: the server picker, and your own activity
 * added up across every server you share with Codex.
 *
 * One server's view is not here any more. It lives at
 * `/me/guilds/:id/overview`, and picking a server in the picker goes there.
 * This page used to render that view inline under a `?guild=` parameter, which
 * left one per-guild view addressed by a query string while every other page
 * of the dashboard uses a path, and hid the fact that a server has pages of
 * its own. Links carrying `?guild=` still work - the route redirects them to
 * that server's overview (see `DashboardOrRedirect` in App).
 *
 * The page no longer picks a server for you either. It used to jump an admin
 * straight to the server they run, which meant an admin could not see their
 * combined activity at all; an admin is a member first (the owner ruling of
 * 2026-08-13), so everybody lands on the same home and goes to a server from
 * there.
 */
export default function DashboardPage() {
  const navigate = useNavigate();

  const [user, setUser] = useState<User | null>(null);
  const [guilds, setGuilds] = useState<Guild[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [activity, setActivity] = useState<UserActivity | null>(null);
  const [activityLoading, setActivityLoading] = useState(true);
  const [activityError, setActivityError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.me(), api.guilds()])
      .then(([me, guildList]) => {
        if (cancelled) return;
        setUser(me);
        setGuilds(guildList);
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
  }, []);

  // Loaded on its own rather than with the identity above: it covers every
  // server at once, so it does not need the server list, and losing one of the
  // two must not blank the other.
  useEffect(() => {
    let cancelled = false;
    api
      .getUserActivity()
      .then((next) => {
        if (!cancelled) setActivity(next);
      })
      .catch((e) => {
        console.error("Dashboard activity fetch failed", e);
        if (cancelled) return;
        setActivity(null);
        if ((e as Error).message === "Unauthorized") return;
        setActivityError(formatError(e, "Could not load your activity."));
      })
      .finally(() => {
        if (!cancelled) setActivityLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
            // Nothing is ever selected here: this page IS the across-servers
            // view, and choosing a server leaves it for that server's overview.
            selectedGuildId={null}
            onSelect={(id) => {
              if (id) navigate(`/me/guilds/${id}/overview`);
            }}
            meta={pickerMeta(null, guilds.length, "TheCodex")}
          />
          <SignalStrip signals={activity ? memberSignals(activity) : []} />
        </div>

        {activityLoading ? (
          <div className="ov-grid" role="status" aria-busy="true">
            <div className="skeleton-card s12" />
            <div className="skeleton-card s7" />
            <div className="skeleton-card s5" />
            <div className="skeleton-card s4" />
            <span className="visually-hidden">Loading activity…</span>
          </div>
        ) : activityError ? (
          <div className="ov-grid">
            <section className="ov-card ov-card--quiet s12">
              <div className="ov-card__head">
                <span className="ov-card__title">Not loaded</span>
              </div>
              <p className="ov-body" role="alert">
                {activityError}
              </p>
            </section>
          </div>
        ) : activity ? (
          <>
            <h2 className="section-title" style={{ margin: "4px 0 12px" }}>
              Your activity
            </h2>
            <MemberOverview activity={activity} />
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
